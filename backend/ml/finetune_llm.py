"""
DisasterGPT — Fine-tuning Pipeline
====================================
Fine-tune Mistral-7B on disaster situation reports using Unsloth + LoRA.
Exports the model as GGUF for CPU inference via llama.cpp.

Usage:
    python -m ml.finetune_llm                                     # defaults
    python -m ml.finetune_llm --data training_data/disaster_instructions.jsonl
    python -m ml.finetune_llm --epochs 5 --no-gguf                # skip GGUF export
    python -m ml.finetune_llm --resume checkpoints/disaster-gpt   # resume from checkpoint
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "unsloth/mistral-7b-bnb-4bit"
DEFAULT_DATA = "training_data/disaster_instructions.jsonl"
DEFAULT_OUTPUT = "models/disaster-gpt"
DEFAULT_GGUF_OUTPUT = "models/disaster-gpt-gguf"
MAX_SEQ_LEN = 4096

# Alpaca-style prompt template for instruction tuning
PROMPT_TEMPLATE = """Below is an instruction that describes a disaster management task. Write a response that appropriately addresses the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""

PROMPT_TEMPLATE_NO_INPUT = """Below is an instruction that describes a disaster management task. Write a response that appropriately addresses the request.

### Instruction:
{instruction}

### Response:
{output}"""

# Inference-time template (no output — the model generates it)
INFERENCE_TEMPLATE = """Below is an instruction that describes a disaster management task. Write a response that appropriately addresses the request.

### Instruction:
{instruction}

### Response:
"""


# ── Data loading ────────────────────────────────────────────────────────────────
def load_dataset_from_jsonl(path: str | Path) -> list[dict[str, str]]:
    """Load JSONL instruction-tuning file."""
    records: list[dict[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                records.append(obj)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping line %d: %s", lineno, exc)
    logger.info("Loaded %d training examples from %s", len(records), path)
    return records


def format_prompts(examples: dict[str, list]) -> dict[str, list[str]]:
    """
    Format batch of examples into Alpaca-style prompts.
    Used as a map function with HuggingFace datasets.
    """
    texts = []
    instructions = examples["instruction"]
    inputs = examples.get("input", [""] * len(instructions))
    outputs = examples["output"]

    for inst, inp, out in zip(instructions, inputs, outputs):
        if inp and inp.strip():
            text = PROMPT_TEMPLATE.format(instruction=inst, input=inp, output=out)
        else:
            text = PROMPT_TEMPLATE_NO_INPUT.format(instruction=inst, output=out)
        texts.append(text)
    return {"text": texts}


# ── Fine-tuning ─────────────────────────────────────────────────────────────────
def run_finetune(
    model_name: str = DEFAULT_MODEL,
    data_path: str = DEFAULT_DATA,
    output_dir: str = DEFAULT_OUTPUT,
    epochs: int = 3,
    batch_size: int = 2,
    grad_accum: int = 4,
    learning_rate: float = 2e-4,
    warmup_steps: int = 50,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.0,
    target_modules: list[str] | None = None,
    max_seq_length: int = MAX_SEQ_LEN,
    export_gguf: bool = True,
    gguf_output: str = DEFAULT_GGUF_OUTPUT,
    resume_from: str | None = None,
) -> Path:
    """
    Full fine-tuning pipeline:
      1. Load base model with Unsloth 4-bit quantisation
      2. Attach LoRA adapters
      3. Train on disaster instruction dataset
      4. Save adapter weights + merged model
      5. (Optional) Export GGUF for llama.cpp CPU inference
    """
    if target_modules is None:
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

    # ── 1. Load model ────────────────────────────────────────────────────
    logger.info("Loading base model: %s", model_name)
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        logger.error(
            "Unsloth not installed. Install with:\n"
            "  pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'\n"
            "  pip install --no-deps trl peft accelerate bitsandbytes"
        )
        raise

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=resume_from or model_name,
        max_seq_length=max_seq_length,
        dtype=None,  # auto-detect
        load_in_4bit=True,
    )

    # ── 2. LoRA adapters ─────────────────────────────────────────────────
    logger.info(
        "Attaching LoRA: r=%d, alpha=%d, targets=%s",
        lora_r,
        lora_alpha,
        target_modules,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_r,
        target_modules=target_modules,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias="none",
        use_gradient_checkpointing="unsloth",  # 30% less VRAM
        random_state=42,
        use_rslora=False,
        loftq_config=None,
    )

    # ── 3. Dataset ───────────────────────────────────────────────────────
    from datasets import Dataset

    raw_records = load_dataset_from_jsonl(data_path)
    dataset = Dataset.from_list(raw_records)
    dataset = dataset.map(format_prompts, batched=True)

    logger.info("Dataset: %d examples, columns: %s", len(dataset), dataset.column_names)

    # ── 4. Trainer ───────────────────────────────────────────────────────
    from transformers import TrainingArguments
    from trl import SFTTrainer

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        dataset_num_proc=2,
        packing=True,  # pack short examples for efficiency
        args=TrainingArguments(
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            warmup_steps=warmup_steps,
            num_train_epochs=epochs,
            learning_rate=learning_rate,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=10,
            save_steps=200,
            save_total_limit=3,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            seed=42,
            output_dir=output_dir,
            report_to="none",
        ),
    )

    # ── 5. Train ─────────────────────────────────────────────────────────
    gpu_stats = torch.cuda.get_device_properties(0) if torch.cuda.is_available() else None
    if gpu_stats:
        logger.info(
            "GPU: %s  |  VRAM: %.1f GB  |  Capability: %d.%d",
            gpu_stats.name,
            gpu_stats.total_mem / 1e9,
            gpu_stats.major,
            gpu_stats.minor,
        )
    else:
        logger.warning("No CUDA GPU detected — training will be very slow on CPU.")

    logger.info("Starting training: %d epochs, effective batch %d ...", epochs, batch_size * grad_accum)
    trainer_stats = trainer.train(resume_from_checkpoint=bool(resume_from))
    logger.info("Training complete. Loss: %.4f", trainer_stats.training_loss)

    # ── 6. Save ──────────────────────────────────────────────────────────
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Save LoRA adapter
    adapter_path = out_path / "lora-adapter"
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    logger.info("LoRA adapter saved → %s", adapter_path)

    # Save merged 16-bit model
    merged_path = out_path / "merged-16bit"
    model.save_pretrained_merged(str(merged_path), tokenizer, save_method="merged_16bit")
    logger.info("Merged 16-bit model saved → %s", merged_path)

    # ── 7. GGUF export ───────────────────────────────────────────────────
    if export_gguf:
        logger.info("Exporting GGUF for llama.cpp ...")
        gguf_path = Path(gguf_output)
        gguf_path.mkdir(parents=True, exist_ok=True)
        try:
            model.save_pretrained_gguf(
                str(gguf_path),
                tokenizer,
                quantization_method="q4_k_m",  # good quality / size balance
            )
            logger.info("GGUF model saved → %s", gguf_path)
        except Exception as exc:
            logger.error("GGUF export failed (non-fatal): %s", exc)
            logger.info("You can convert manually with: python llama.cpp/convert.py %s", merged_path)

    # Save training config for reproducibility
    config = {
        "base_model": model_name,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "lora_dropout": lora_dropout,
        "target_modules": target_modules,
        "epochs": epochs,
        "batch_size": batch_size,
        "grad_accum": grad_accum,
        "learning_rate": learning_rate,
        "max_seq_length": max_seq_length,
        "training_loss": trainer_stats.training_loss,
        "data_path": data_path,
        "num_examples": len(dataset),
    }
    config_path = out_path / "training_config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    logger.info("Training config saved → %s", config_path)

    return out_path


# ── Quick inference test ────────────────────────────────────────────────────────
def test_inference(model_dir: str = DEFAULT_OUTPUT):
    """Quick smoke test with the fine-tuned model."""
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(Path(model_dir) / "lora-adapter"),
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)

    prompt = INFERENCE_TEMPLATE.format(
        instruction="Generate a situation report for flood, severity: critical, location: Bangladesh"
    )
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    outputs = model.generate(**inputs, max_new_tokens=512, temperature=0.7, top_p=0.9)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    print("\n=== Test Inference ===")
    print(response.split("### Response:")[-1].strip())


# ── CLI ─────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fine-tune DisasterGPT on situation reports")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Base model name or path")
    parser.add_argument("--data", default=DEFAULT_DATA, help="Training data JSONL file")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha")
    parser.add_argument("--max-seq-len", type=int, default=MAX_SEQ_LEN, help="Max sequence length")
    parser.add_argument("--no-gguf", action="store_true", help="Skip GGUF export")
    parser.add_argument("--gguf-output", default=DEFAULT_GGUF_OUTPUT, help="GGUF output dir")
    parser.add_argument("--resume", default=None, help="Resume from checkpoint dir")
    parser.add_argument("--test", action="store_true", help="Run test inference after training")
    args = parser.parse_args()

    logger.info("=== DisasterGPT Fine-tuning Pipeline ===")

    output_path = run_finetune(
        model_name=args.model,
        data_path=args.data,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        max_seq_length=args.max_seq_len,
        export_gguf=not args.no_gguf,
        gguf_output=args.gguf_output,
        resume_from=args.resume,
    )

    logger.info("=== Fine-tuning complete! Output: %s ===", output_path)

    if args.test:
        test_inference(str(output_path))


if __name__ == "__main__":
    main()
