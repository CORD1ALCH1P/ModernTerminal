#!/usr/bin/env python3
"""Validate a dataset JSONL file against training/dataset/SCHEMA.md.

Usage: python3 validate_dataset.py <path-to-jsonl> [<path-to-jsonl> ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

VALID_VENDORS = {"cisco_ios", "eltex"}
VALID_ROLES = {"system", "user", "assistant", "tool"}
REJECTED_PREFIX = "Command rejected by user, not sent:"


def validate_episode(path: Path, line_no: int, obj: dict) -> list[str]:
    errors: list[str] = []

    def err(msg: str) -> None:
        errors.append(f"{path}:{line_no} [{obj.get('id', '?')}] {msg}")

    if "id" not in obj or not isinstance(obj["id"], str) or not obj["id"]:
        err("missing or empty 'id'")
    if obj.get("vendor") not in VALID_VENDORS:
        err(f"vendor must be one of {VALID_VENDORS}, got {obj.get('vendor')!r}")
    if not isinstance(obj.get("tags"), list):
        err("'tags' must be a list")

    messages = obj.get("messages")
    if not isinstance(messages, list) or not messages:
        err("'messages' must be a non-empty list")
        return errors

    if messages[0].get("role") != "system":
        err("messages[0] must have role 'system'")

    last = messages[-1]
    if last.get("role") != "assistant" or last.get("tool_calls"):
        err("last message must be role 'assistant' with no dangling tool_calls")

    for i, msg in enumerate(messages):
        role = msg.get("role")
        if role not in VALID_ROLES:
            err(f"messages[{i}]: invalid role {role!r}")
            continue
        if "content" not in msg or not isinstance(msg["content"], str):
            err(f"messages[{i}]: missing/non-string 'content'")
        if msg.get("tool_calls") and role != "assistant":
            err(f"messages[{i}]: tool_calls only allowed on role 'assistant', found on {role!r}")
        if role == "tool" and not msg.get("tool_name"):
            err(f"messages[{i}]: role 'tool' message missing 'tool_name'")
        if role == "assistant" and msg.get("tool_calls"):
            for j, call in enumerate(msg["tool_calls"]):
                if "name" not in call or "arguments" not in call:
                    err(f"messages[{i}].tool_calls[{j}]: needs 'name' and 'arguments'")
        # Loose secret-scrub heuristic -- not a substitute for a real scrub pass.
        content = msg.get("content", "")
        if isinstance(content, str) and any(
            marker in content.lower() for marker in ("password ", "secret ", "-----begin")
        ):
            err(f"messages[{i}]: content looks like it may contain an unscrubbed secret")

    return errors


def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__)
        return 1

    total_errors = 0
    total_episodes = 0
    seen_ids: set[str] = set()

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            print(f"ERROR: {path} does not exist")
            total_errors += 1
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            total_episodes += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"{path}:{line_no} invalid JSON: {e}")
                total_errors += 1
                continue
            for e in validate_episode(path, line_no, obj):
                print(e)
                total_errors += 1
            episode_id = obj.get("id")
            if episode_id in seen_ids:
                print(f"{path}:{line_no} duplicate id {episode_id!r}")
                total_errors += 1
            elif episode_id:
                seen_ids.add(episode_id)

    print(f"\n{total_episodes} episode(s) checked, {total_errors} error(s).")
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
