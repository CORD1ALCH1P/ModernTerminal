# LoRA fine-tuning workspace — Savr network-ops copilot

Goal: specialize Qwen3-8B (the model Savr already defaults to) on Cisco IOS/IOS-XE + Eltex
troubleshooting/config episodes, as a drop-in replacement for the base model via `OLLAMA_MODEL` —
no changes needed to `backend/app/ai/`.

## Pipeline (in order)

1. **Environment** (WSL2 Debian, GPU: RTX 3080 10GB)
   - System packages: `python3`, `python3-venv`, `python3-pip`, `python3-dev`, `build-essential`, `git`
   - Python env + Unsloth stack (torch, bitsandbytes, transformers, peft, trl)
2. **Dataset** — see `dataset/SCHEMA.md` and `dataset/example.jsonl`. Validate with
   `scripts/validate_dataset.py` before every training run.
3. **Train** — `scripts/train_lora.py` (QLoRA via Unsloth, loss masked to assistant turns only)
4. **Export** — `scripts/export_gguf.py` (merge LoRA, quantize to GGUF)
5. **Deploy**:
   ```bash
   ollama show qwen3:8b --modelfile > Modelfile   # reuse the base TEMPLATE verbatim
   # edit only the FROM line to point at your exported GGUF, e.g.:
   #   FROM ../models/gguf/savr-netops.Q4_K_M.gguf
   ollama create savr-netops -f Modelfile
   ```
   Then set `OLLAMA_MODEL=savr-netops` (env var, or via Savr's in-app AI Plugin Settings). Do not
   hand-write a new TEMPLATE — Ollama's tool-calling parsing depends on matching the base model's
   exact template.
6. **Evaluate** — manually, in the real Savr AI panel, against a held-out scenario set (see
   `dataset/SCHEMA.md` bottom section) — base vs fine-tuned, side by side.

## Why this shape

- Same base model family as Savr's existing default (`qwen3:8b`) → the fine-tuned model swaps into
  `OLLAMA_MODEL` without touching the tool-calling wire format `backend/app/ai/ollama_provider.py`
  and `loop.py` already handle.
- Dataset schema mirrors `ChatMessage`/`ToolCall`/`ToolSpec` in `backend/app/ai/base.py` and the two
  tools defined in `backend/app/ai/tools.py` (`read_terminal_scrollback`, `send_command`) exactly,
  so training examples are structurally identical to what the model sees in production.
- System prompt in every training example is copied verbatim from `SYSTEM_MESSAGE` in
  `backend/app/ai/loop.py` — training on a different system prompt than production uses would waste
  a chunk of what LoRA is supposed to teach.

## What only you can do here

- Provide/scrub real Cisco & Eltex CLI captures (through Savr itself, ideally) — this is the data
  that actually differentiates the model; a general-purpose LLM already knows generic Cisco syntax
  reasonably well but has thin Eltex coverage.
- Review synthetic examples for domain accuracy (command syntax, realistic output, correct
  diagnosis) — I can draft synthetic episodes, but I have no way to verify they match real device
  behavior on your gear.
- Kick off the actual multi-hour training run and sit through it (or at least be aware it's tying up
  the GPU / desktop for that stretch).
- Judge the final model's quality in the real Savr UI against real equipment.
