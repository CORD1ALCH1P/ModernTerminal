#!/usr/bin/env python3
"""Merge a trained LoRA adapter into the base model and export to quantized GGUF.

Usage:
    python3 export_gguf.py --adapter ../models/savr-netops-lora --output ../models/gguf
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True, type=Path, help="LoRA adapter dir from train_lora.py")
    ap.add_argument("--output", required=True, type=Path, help="Output dir for the GGUF file")
    ap.add_argument(
        "--quant",
        default="q4_k_m",
        help="GGUF quantization (q4_k_m is the usual balance; q5_k_m/q8_0 for higher quality at more VRAM/disk)",
    )
    args = ap.parse_args()

    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(model_name=str(args.adapter))
    args.output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained_gguf(str(args.output), tokenizer, quantization_method=args.quant)
    print(f"GGUF written to {args.output} (quant={args.quant})")


if __name__ == "__main__":
    main()
