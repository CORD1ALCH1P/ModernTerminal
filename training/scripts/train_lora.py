#!/usr/bin/env python3
"""QLoRA fine-tune Qwen3-8B on the Savr network-ops tool-calling dataset.

Run this inside the WSL2 Unsloth environment (needs a GPU). Always run with
--dry-run first and eyeball the printed examples -- this checks the rendered
chat template actually matches what Ollama expects for tool calls, *before*
spending GPU hours on a run trained against a wrong format.

Usage:
    python3 train_lora.py --dataset ../dataset/train.jsonl --dry-run
    python3 train_lora.py --dataset ../dataset/train.jsonl --eval ../dataset/eval.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Mirrors backend/app/ai/tools.py exactly -- keep these two in sync with that
# file if the tools ever change, so training data matches production tools.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_terminal_scrollback",
            "description": (
                "Return the most recent terminal output (prompts, command results, errors). "
                "Call this before acting if you're unsure of the device's current state."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_bytes": {"type": "integer", "description": "Max bytes to return (default 4000)."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_command",
            "description": (
                "Type one command + Enter into the live terminal and report what happened. "
                "Dangerous commands, or the session being in 'confirm' mode, always pause for "
                "human approval first -- that pause is not an error, just wait for the outcome."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Exact command text, no trailing newline."}
                },
                "required": ["command"],
            },
        },
    },
]


def load_episodes(path: Path) -> list[dict]:
    episodes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            episodes.append(json.loads(line))
    return episodes


def to_template_messages(episode: dict) -> list[dict]:
    """Convert our SCHEMA.md shape into the OpenAI-ish shape most HF chat
    templates (including Qwen's) expect for apply_chat_template(tools=...)."""
    out = []
    for msg in episode["messages"]:
        role = msg["role"]
        if role == "assistant" and msg.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": msg["content"],
                    "tool_calls": [
                        {"type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                        for c in msg["tool_calls"]
                    ],
                }
            )
        elif role == "tool":
            out.append({"role": "tool", "name": msg["tool_name"], "content": msg["content"]})
        else:
            out.append({"role": role, "content": msg["content"]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--eval", type=Path, default=None)
    ap.add_argument("--base-model", default="unsloth/Qwen3-8B-unsloth-bnb-4bit")
    ap.add_argument("--output-dir", default="../models/savr-netops-lora")
    ap.add_argument("--max-seq-length", type=int, default=4096)
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=16)
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument(
        "--dry-run",
        type=int,
        nargs="?",
        const=3,
        default=None,
        metavar="N",
        help="Print N rendered chat-template examples and exit -- no model load, no training.",
    )
    args = ap.parse_args()

    episodes = load_episodes(args.dataset)
    print(f"Loaded {len(episodes)} episodes from {args.dataset}")

    if args.dry_run is not None:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(args.base_model)
        for ep in episodes[: args.dry_run]:
            rendered = tokenizer.apply_chat_template(
                to_template_messages(ep), tools=TOOLS, tokenize=False, add_generation_prompt=False
            )
            print(f"\n{'=' * 80}\n# episode: {ep['id']}\n{'=' * 80}\n{rendered}")
        return

    # Everything below needs the actual GPU environment (unsloth, torch, trl, peft).
    # Unsloth must be imported before trl/transformers/peft -- otherwise its
    # patches don't fully apply (observed concretely: SFTConfig's eos_token
    # ends up stuck on an internal placeholder sentinel that isn't in the
    # tokenizer's vocab, so SFTTrainer's vocab-membership check throws).
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import train_on_responses_only
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )
    # Captured immediately after from_pretrained, before get_peft_model --
    # something downstream mutates tokenizer.eos_token to a placeholder
    # sentinel ('<EOS_TOKEN>') that isn't in the vocab, so read the real value
    # now rather than at SFTConfig-construction time.
    real_eos_token = tokenizer.eos_token
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.r,
        lora_alpha=args.alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
    )

    def render(ep: dict) -> dict:
        text = tokenizer.apply_chat_template(
            to_template_messages(ep), tools=TOOLS, tokenize=False, add_generation_prompt=False
        )
        return {"text": text}

    train_ds = Dataset.from_list([render(ep) for ep in episodes])
    eval_ds = Dataset.from_list([render(ep) for ep in load_episodes(args.eval)]) if args.eval else None

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=args.max_seq_length,
            # See real_eos_token comment above -- must be the value captured
            # right after from_pretrained, not tokenizer.eos_token read here.
            eos_token=real_eos_token,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_ratio=0.03,
            logging_steps=5,
            output_dir=args.output_dir,
            eval_strategy="steps" if eval_ds is not None else "no",
            eval_steps=20 if eval_ds is not None else None,
            save_strategy="epoch",
            report_to="none",
        ),
    )

    # Mask loss to assistant turns only. Verified via --dry-run against the real
    # Qwen3 tokenizer: its template renders role="tool" messages as role="user"
    # wrapped in <tool_response>...</tool_response>, not a separate turn kind --
    # so masking everything between "<|im_start|>user" and "<|im_start|>assistant"
    # correctly excludes both real user turns and tool-result turns from the loss.
    # Also note: Qwen3's template inserts an empty <think></think> block before
    # every final assistant answer (no reasoning_content was supplied in this
    # dataset) -- the model will learn to always emit empty thinking on these
    # turns, which is intentional here (fast interactive tool-calling), not a bug.
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )

    trainer.train()
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"Saved LoRA adapter to {args.output_dir}")


if __name__ == "__main__":
    main()
