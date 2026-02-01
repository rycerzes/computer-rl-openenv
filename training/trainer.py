import argparse

from computer_rl_env.tasks.loader import TaskLoader
from datasets import Dataset
from transformers import AutoProcessor, AutoTokenizer
from trl import GRPOConfig, GRPOTrainer

from .config import TrainingConfig
from .rewards import reward_action_diversity, reward_efficiency, reward_task_success
from .rollout import create_rollout_func


def load_config(config_path: str) -> TrainingConfig:
    """Load configuration from YAML file."""
    return TrainingConfig.from_yaml(config_path)


def main(config_path: str):
    """Main training entry point."""
    print(f"Loading config from {config_path}...")
    config = load_config(config_path)

    # Load Tasks & Create Dataset
    print(f"Loading tasks from {config.task_catalog_path}...")
    task_loader = TaskLoader()
    # Load tasks from registry file (e.g., test_small.json)
    try:
        tasks = task_loader.load_from_registry(config.task_catalog_path)
        print(f"Loaded {len(tasks)} tasks.")
    except Exception as e:
        print(f"Error loading tasks: {e}")
        # Fallback to dummy data only for testing/debugging if loading fails
        print("Falling back to dummy dataset...")
        tasks = []
        dataset = Dataset.from_list(
            [
                {"prompt": "Open the calculator application."},
                {"prompt": "Launch Google Chrome and go to github.com."},
            ]
        )

    if tasks:
        # Create dataset from actual tasks
        # Each item is just the instruction prompt
        dataset = Dataset.from_list([{"prompt": t.instruction, "task_id": t.id} for t in tasks])

    # Model & Tokenizer Loading
    print(f"Loading model {config.model_name_or_path}...")
    peft_config = None

    if config.use_unsloth:
        print("Using Unsloth FastVisionModel...")
        from unsloth import FastVisionModel

        # Load model using Unsloth (returns model and tokenizer)
        model, tokenizer = FastVisionModel.from_pretrained(
            model_name=config.model_name_or_path,
            max_seq_length=config.max_prompt_length,
            load_in_4bit=config.load_in_4bit,
            fast_inference=False,
            gpu_memory_utilization=config.vllm_gpu_memory_utilization,
        )
        processor = (
            tokenizer  # FastVisionModel returns a wrapped tokenizer that often acts as processor
        )

        # Configure LoRA/PEFT via Unsloth
        model = FastVisionModel.get_peft_model(
            model,
            finetune_vision_layers=False,
            finetune_language_layers=True,
            finetune_attention_modules=True,
            finetune_mlp_modules=True,
            r=config.lora_rank,
            lora_alpha=config.lora_rank,
            lora_dropout=0,
            bias="none",
            random_state=3407,
            use_gradient_checkpointing="unsloth",
        )
    else:
        # Standard generic loading
        # Prepare Processor/Tokenizer
        print(f"Loading processor for {config.model_name_or_path}...")
        try:
            processor = AutoProcessor.from_pretrained(
                config.model_name_or_path, trust_remote_code=True
            )
            tokenizer = processor.tokenizer
        except Exception:
            # Fallback for text-only models
            tokenizer = AutoTokenizer.from_pretrained(
                config.model_name_or_name, trust_remote_code=True
            )
            processor = None

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = config.model_name_or_path
        if config.load_in_4bit:
            try:
                from transformers import BitsAndBytesConfig
            except ImportError:
                raise ImportError("BitsAndBytes is required for 4-bit training.")

            print(f"Loading model {config.model_name_or_path} in 4-bit...")
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype="float16",
                bnb_4bit_quant_type="nf4",
            )
            model_kwargs = {
                "quantization_config": quantization_config,
                "low_cpu_mem_usage": True,
            }
            from transformers import AutoModelForImageTextToText

            model = AutoModelForImageTextToText.from_pretrained(
                config.model_name_or_path, **model_kwargs
            )

        if config.load_in_4bit or config.lora_rank > 0:
            from peft import LoraConfig, TaskType

            peft_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=config.lora_rank,
                lora_alpha=config.lora_rank * 2,
                target_modules=[
                    "q_proj",
                    "k_proj",
                    "v_proj",
                    "o_proj",
                    "up_proj",
                    "gate_proj",
                    "down_proj",
                ],
                lora_dropout=0.05,
                bias="none",
            )

    # Configure GRPOTrainer
    print("Configuring GRPOTrainer...")
    grpo_config = GRPOConfig(
        output_dir=config.output_dir,
        num_train_epochs=config.num_train_epochs,
        learning_rate=config.learning_rate,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        max_grad_norm=config.max_grad_norm,
        warmup_ratio=config.warmup_ratio,
        logging_steps=config.save_steps,  # Map save_steps to logging as well for now
        save_steps=config.save_steps,
        report_to=["trackio"],  # Fallback/default logic or from config if added
        # Generation
        max_completion_length=config.max_completion_length,  # Note: variable name change in config.py vs original
        temperature=config.temperature,
        num_generations=config.num_generations,
        # vLLM
        use_vllm=config.use_vllm,
        vllm_mode=config.vllm_mode,
        vllm_server_base_url=config.vllm_server_url,  # name change in config.py
        vllm_gpu_memory_utilization=config.vllm_gpu_memory_utilization,
        vllm_tensor_parallel_size=config.vllm_tensor_parallel_size,
        # GRPO / GSPO Specifics
        optim=config.optim,
        lr_scheduler_type=config.lr_scheduler_type,
        adam_beta1=config.adam_beta1,
        adam_beta2=config.adam_beta2,
        weight_decay=config.weight_decay,
        # loss_type=config.loss_type, # Might need to verify if supported in current trl version
        max_prompt_length=config.max_prompt_length,
        # Memory Optimization
        gradient_checkpointing=True,  # Always force true for VLM
        fp16=True,  # Default for unsloth
        bf16=False,
    )

    # Create custom rollout function with bound arguments
    # We use the factory method to inject the server URL and other settings
    rollout_fn = create_rollout_func(
        openenv_server_url=config.openenv_server_url,
        max_steps=50,  # Default max steps, could be configurable
        use_vision=True,
    )

    # Initialize Trainer
    trainer = GRPOTrainer(
        model=model,
        # peft_config=peft_config, # Pass PEFT config if defined -- GRPOTrainer supports it
        processing_class=tokenizer,
        reward_funcs=[
            reward_task_success,
            reward_efficiency,
            reward_action_diversity,
        ],
        train_dataset=dataset,
        args=grpo_config,
        rollout_func=rollout_fn,
        peft_config=peft_config,
    )

    print("Starting training...")
    trainer.train()

    print(f"Saving model to {config.output_dir}...")
    trainer.save_model(config.output_dir)
    if config.push_to_hub and config.hf_repo_id:
        trainer.push_to_hub(config.hf_repo_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to YAML training config")
    args = parser.parse_args()
    main(args.config)
