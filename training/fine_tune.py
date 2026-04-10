"""
Fine-tune a model on Dylan's extracted training data using unsloth + LoRA.

Run this AFTER extract_training_data.py has generated the JSONL file.
Designed for H100 (80GB VRAM) — uses 4-bit quantized base + LoRA.

Usage:
    python training/fine_tune.py [--base-model qwen2.5-coder:14b] [--epochs 3]
"""
import argparse
import json
from pathlib import Path


def format_for_training(example: dict) -> dict:
    """Convert our JSONL format to the chat format unsloth expects."""
    messages = []

    # System message — Dylan's preferences baked in
    messages.append({
        "role": "system",
        "content": (
            "You are Dylan's personal coding assistant. You work across multiple projects: "
            "CabMan (WPF/.NET 8), QuantTrader (Python), Kalshi Bot (Python), Sports Betting (Python), "
            "KC PowerWash (full-stack), CallPilot (Python/Vapi), MAC Estimator (WPF/.NET 8). "
            "Be terse. No emojis. No trailing summaries. Lead with action. "
            "Implement full plans without prompting. Verify before saying done."
        ),
    })

    if example.get("input"):
        messages.append({"role": "user", "content": f"{example['instruction']}\n\n{example['input']}"})
    else:
        messages.append({"role": "user", "content": example["instruction"]})

    messages.append({"role": "assistant", "content": example["output"]})

    return {"messages": messages}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="unsloth/Qwen2.5-Coder-14B-Instruct-bnb-4bit",
                        help="Base model for fine-tuning")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--output-dir", default="/root/ollama-team/training/output")
    parser.add_argument("--data-file", default="/root/ollama-team/training/data/training_data.jsonl")
    args = parser.parse_args()

    data_path = Path(args.data_file)
    if not data_path.exists():
        print(f"Training data not found at {data_path}")
        print("Run extract_training_data.py first!")
        return

    # Load and format data
    print(f"Loading training data from {data_path}...")
    examples = []
    with open(data_path) as f:
        for line in f:
            ex = json.loads(line)
            examples.append(format_for_training(ex))

    print(f"Loaded {len(examples)} examples")

    # Save formatted data for unsloth
    formatted_path = Path(args.output_dir) / "formatted_data.jsonl"
    formatted_path.parent.mkdir(parents=True, exist_ok=True)
    with open(formatted_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    print(f"Formatted data saved to {formatted_path}")

    # Import unsloth (only available on GPU machine)
    try:
        from unsloth import FastLanguageModel
        from unsloth.chat_templates import get_chat_template
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
    except ImportError:
        print("\nunsloth not installed. On the GPU machine, run:")
        print("  pip install unsloth trl datasets")
        print(f"\nFormatted data is ready at: {formatted_path}")
        print("You can also fine-tune manually with any tool that accepts JSONL chat format.")
        return

    # Load model
    print(f"\nLoading base model: {args.base_model}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        dtype=None,  # Auto-detect
        load_in_4bit=True,
    )

    tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")

    # Add LoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                         "gate_proj", "up_proj", "down_proj"],
        lora_alpha=32,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    # Load dataset
    dataset = load_dataset("json", data_files=str(formatted_path), split="train")

    def format_prompts(examples):
        texts = []
        for msgs in examples["messages"]:
            text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
            texts.append(text)
        return {"text": texts}

    dataset = dataset.map(format_prompts, batched=True)

    # Train
    print(f"\nStarting fine-tuning: {args.epochs} epochs, lr={args.lr}, batch={args.batch_size}")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        args=TrainingArguments(
            output_dir=args.output_dir,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=4,
            warmup_steps=10,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            fp16=True,
            logging_steps=10,
            save_strategy="epoch",
            optim="adamw_8bit",
        ),
    )

    print("Training...")
    trainer.train()
    print("Training complete!")

    # Save LoRA adapter
    lora_path = Path(args.output_dir) / "lora_adapter"
    model.save_pretrained(str(lora_path))
    tokenizer.save_pretrained(str(lora_path))
    print(f"LoRA adapter saved to {lora_path}")

    # Export to GGUF for Ollama
    print("\nExporting to GGUF (Q4_K_M) for Ollama...")
    gguf_path = Path(args.output_dir) / "dylan-coder.gguf"
    model.save_pretrained_gguf(
        str(gguf_path.parent / "gguf_export"),
        tokenizer,
        quantization_method="q4_k_m",
    )
    print(f"GGUF exported!")

    # Create Ollama Modelfile
    modelfile_path = Path(args.output_dir) / "Modelfile"
    gguf_files = list((gguf_path.parent / "gguf_export").glob("*.gguf"))
    if gguf_files:
        modelfile_path.write_text(f"""FROM {gguf_files[0]}

SYSTEM \"\"\"You are Dylan's personal coding assistant. You work across multiple projects:
CabMan (WPF/.NET 8), QuantTrader (Python), Kalshi Bot (Python), Sports Betting (Python),
KC PowerWash (full-stack), CallPilot (Python/Vapi), MAC Estimator (WPF/.NET 8), Ollama Team.
Be terse. No emojis. No trailing summaries. Lead with action. Implement full plans without prompting.
Verify before saying done. Use BLC not BBC for blind corners in CabMan.\"\"\"

PARAMETER temperature 0.3
PARAMETER num_ctx 8192
""")
        print(f"\nTo load into Ollama:")
        print(f"  ollama create dylan-coder -f {modelfile_path}")
        print(f"  ollama run dylan-coder")

    print("\n=== DONE ===")
    print(f"To use locally, copy the .gguf file to your home machine and create with Ollama.")


if __name__ == "__main__":
    main()
