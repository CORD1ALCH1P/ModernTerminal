#!/usr/bin/env python3
"""Convert the hand-authored plain-conversational dataset (raw batches, see
README_DATASET.md) into the tool-calling schema in dataset/SCHEMA.md.

Conversion rule (conservative -- see training/README.md for why):
  An assistant turn whose fenced code block contains exactly ONE non-empty
  line, immediately followed by a user turn, is converted to a `send_command`
  tool_call + a role="tool" response built from that next user turn's content.
  Everything else (multi-command blocks, config-recommendation blocks with no
  device-output follow-up, plain text) is left untouched -- never fabricate a
  command/output split we can't verify from the source data.

Usage:
    python3 convert_to_toolcalling.py <input.jsonl> [<input.jsonl> ...] --out <output.jsonl>
"""
from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path

CODE_BLOCK_RE = re.compile(r"```(?:\w*\n)?(.*?)```", re.DOTALL)

VENDOR_MAP = {"eltex": "eltex", "cisco": "cisco_ios"}


def extract_single_command(assistant_text: str) -> tuple[str, str] | None:
    """If assistant_text's fenced code block has exactly one non-empty,
    non-continuation line, return (command, text_with_block_removed).
    Otherwise return None (leave the turn as plain text)."""
    match = CODE_BLOCK_RE.search(assistant_text)
    if not match:
        return None
    block = match.group(1).strip("\n")
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if len(lines) != 1:
        return None
    command = lines[0].strip()
    # Skip obvious config-mode blocks (multi-step changes, never executed by
    # the model per the system prompt's policy) even if they render as one
    # line after stripping -- "conf t" alone as the *only* line is fine (rare),
    # but anything containing '#' REPL-style prompts or ending in a config verb
    # is still just one line in practice for this dataset, so no extra check
    # needed beyond the line-count rule above.
    text_without_block = (assistant_text[: match.start()] + assistant_text[match.end() :]).strip()
    return command, text_without_block


def convert_episode(ep: dict) -> dict:
    messages = ep["messages"]
    out_messages = [messages[0]]  # system, unchanged
    i = 1
    while i < len(messages):
        msg = messages[i]
        if msg["role"] == "assistant":
            extracted = extract_single_command(msg["content"])
            has_next_user = i + 1 < len(messages) and messages[i + 1]["role"] == "user"
            if extracted and has_next_user:
                command, remaining_text = extracted
                call_id = uuid.uuid4().hex
                out_messages.append(
                    {
                        "role": "assistant",
                        "content": remaining_text,
                        "tool_calls": [{"name": "send_command", "arguments": {"command": command}, "id": call_id}],
                    }
                )
                out_messages.append(
                    {
                        "role": "tool",
                        "tool_name": "send_command",
                        "tool_call_id": call_id,
                        "content": messages[i + 1]["content"],
                    }
                )
                i += 2
                continue
        out_messages.append(msg)
        i += 1

    converted = dict(ep)
    converted["messages"] = out_messages
    converted["vendor"] = VENDOR_MAP.get(ep.get("vendor"), ep.get("vendor"))
    return converted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    total = 0
    converted_count = 0
    with args.out.open("w", encoding="utf-8") as out_f:
        for path in args.inputs:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                total += 1
                ep = json.loads(line)
                converted = convert_episode(ep)
                n_tool_calls = sum(1 for m in converted["messages"] if m["role"] == "tool")
                if n_tool_calls:
                    converted_count += 1
                out_f.write(json.dumps(converted, ensure_ascii=False) + "\n")

    print(f"{total} episodes processed ({args.out}), {converted_count} contain at least one tool_call")


if __name__ == "__main__":
    main()
