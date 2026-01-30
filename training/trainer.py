import os
import sys
import yaml
import argparse
from typing import Optional
from dataclasses import dataclass, field

import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoProcessor

from trl import GRPOTrainer, GRPOConfig

from .rollout import rollout_func, create_rollout_func
from .rewards import (
    reward_task_success,
    reward_efficiency,
    reward_action_diversity
)
# Assuming computer_rl_env is installed in the environment
from computer_rl_env.tasks.loader import TaskLoader


@dataclass
class TrainingConfig:
    """Wrapper for training configuration."""
    model_name_or_path: str
    output_dir: str
    task_catalog_path: str = "tasks/tasks.yaml"
    
    # Training Params
    num_train_epochs: int = 1
    learning_rate: float = 1e-5
    batch_size: int = 1
    gradient_accumulation_steps: int = 8
    max_grad_norm: float = 1.0
    warmup_ratio: float = 0.1
    logging_steps: int = 1
    save_steps: int = 100
    
    # Generation Params
    max_new_tokens: int = 1024
    temperature: float = 1.0
    num_generations: int = 4
    
    # Environment Params
    openenv_server_url: str = "http://localhost:8000"
    
    # vLLM Params
    use_vllm: bool = True
    vllm_gpu_memory_utilization: float = 0.6
    vllm_tensor_parallel_size: int = 1
    
    # Reporting
    report_to: list[str] = field(default_factory=lambda: ["trackio"])
    trackio_space_id: Optional[str] = None
    push_to_hub: bool = False
    hf_repo_id: Optional[str] = None


def load_config(config_path: str) -> TrainingConfig:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        config_dict = yaml.safe_load(f)
    return TrainingConfig(**config_dict)


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
        dataset = Dataset.from_list([
            {"prompt": "Open the calculator application."},
            {"prompt": "Launch Google Chrome and go to github.com."},
        ])

    if tasks:
        # Create dataset from actual tasks
        # Each item is just the instruction prompt
        dataset = Dataset.from_list([
            {"prompt": t.instruction, "task_id": t.id} 
            for t in tasks
        ])
    
    # Prepare Processor/Tokenizer
    print(f"Loading processor for {config.model_name_or_path}...")
    # usage of processor depends on model type
    try:
        processor = AutoProcessor.from_pretrained(config.model_name_or_path, trust_remote_code=True)
        tokenizer = processor.tokenizer
    except Exception:
        # Fallback for text-only models
        tokenizer = AutoTokenizer.from_pretrained(config.model_name_or_path, trust_remote_code=True)
        processor = None

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

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
        logging_steps=config.logging_steps,
        save_steps=config.save_steps,
        report_to=config.report_to,
        trackio_space_id=config.trackio_space_id,
        
        # Generation
        max_completion_length=config.max_new_tokens,
        temperature=config.temperature,
        num_generations=config.num_generations,
        
        # vLLM
        use_vllm=config.use_vllm,
        vllm_gpu_memory_utilization=config.vllm_gpu_memory_utilization,
    )
    
    # Create custom rollout function with bound arguments
    # We use the factory method to inject the server URL and other settings
    rollout_fn = create_rollout_func(
        openenv_server_url=config.openenv_server_url,
        max_steps=50, # Default max steps, could be configurable
        use_vision=True, 
    )

    # Initialize Trainer
    trainer = GRPOTrainer(
        model=config.model_name_or_path,
        processing_class=tokenizer, 
        reward_funcs=[
            reward_task_success,
            reward_efficiency,
            reward_action_diversity,
        ],
        train_dataset=dataset,
        args=grpo_config,
        rollout_func=rollout_fn,
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
