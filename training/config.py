"""Training configuration for GRPO with TRL."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class TrainingConfig(BaseModel):
    """Configuration for GRPO training with TRL and OpenEnv."""

    # Model
    model_name_or_path: str = Field(
        description="HuggingFace model ID or local path (e.g., 'Qwen/Qwen2-VL-2B-Instruct')"
    )
    use_vision: bool = Field(
        default=False,
        description="Whether to use vision/multimodal model with screenshots",
    )
    # Unsloth / PEFT
    use_unsloth: bool = Field(
        default=True,
        description="Whether to use Unsloth's FastVisionModel",
    )
    load_in_4bit: bool = Field(
        default=True,
        description="Whether to use 4-bit quantization",
    )
    lora_rank: int = Field(default=16, ge=1, description="LoRA rank (r)")

    # Training hyperparameters
    num_train_epochs: int = Field(default=3, ge=1)
    learning_rate: float = Field(default=5e-6, gt=0)
    batch_size: int = Field(default=1, ge=1, description="Per-device train batch size")
    gradient_accumulation_steps: int = Field(default=8, ge=1)
    warmup_ratio: float = Field(default=0.1, ge=0, le=1)
    max_grad_norm: float = Field(default=1.0, gt=0)

    # Optimizer & Scheduler
    optim: str = Field(default="adamw_8bit", description="Optimizer name")
    lr_scheduler_type: str = Field(default="cosine", description="Learning rate scheduler type")
    adam_beta1: float = Field(default=0.9, ge=0, le=1)
    adam_beta2: float = Field(default=0.99, ge=0, le=1)
    weight_decay: float = Field(default=0.1, ge=0)

    # GRPO / GSPO Specific
    loss_type: str = Field(default="dr_grpo", description="Loss function type (e.g., 'dr_grpo')")
    importance_sampling_level: str = Field(
        default="sequence",
        description="GSPO importance sampling level",
    )
    max_prompt_length: int = Field(default=1024, ge=1)

    # vLLM configuration (CUDA 12+ required)
    use_vllm: bool = Field(default=True, description="Use vLLM for fast inference")
    vllm_mode: Literal["colocate", "server"] = Field(
        default="colocate",
        description="colocate: same process (1 GPU), server: separate process (2+ GPUs)",
    )
    vllm_server_url: str | None = Field(
        default=None,
        description="vLLM server URL for server mode (e.g., 'http://localhost:8080')",
    )
    vllm_gpu_memory_utilization: float = Field(
        default=0.6,
        ge=0.1,
        le=1.0,
        description="vLLM GPU memory utilization",
    )
    vllm_tensor_parallel_size: int = Field(
        default=1,
        ge=1,
        description="Number of GPUs for tensor parallelism in colocate mode (e.g., 2 for dual-GPU)",
    )
    vllm_device: str = Field(
        default="cuda:0",
        description="GPU device for vLLM server in server mode (e.g., 'cuda:0')",
    )
    training_device: str = Field(
        default="cuda:0",
        description="GPU device for training in server mode (e.g., 'cuda:1')",
    )

    # Environment
    openenv_server_url: str = Field(
        default="http://localhost:8000",
        description="URL of the Computer RL environment server",
    )
    task_catalog_path: str | None = Field(
        default=None,
        description="Path to task catalog YAML/JSON for training tasks",
    )
    max_episode_steps: int = Field(
        default=50,
        ge=1,
        description="Maximum steps per episode in rollout",
    )
    num_parallel_envs: int = Field(
        default=1,
        ge=1,
        description="Number of parallel environment instances for rollout",
    )

    # Generation
    max_completion_length: int = Field(
        default=100,
        ge=1,
        description="Maximum tokens for model completion",
    )
    num_generations: int = Field(
        default=4,
        ge=1,
        description="Number of completions to generate per prompt for GRPO",
    )
    temperature: float = Field(default=1.0, gt=0)

    # Reward weights
    reward_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "task_success": 1.0,
            "efficiency": 0.3,
            "diversity": 0.1,
        },
        description="Weights for combining multiple reward signals",
    )

    # Output
    output_dir: str = Field(default="./checkpoints")
    save_steps: int = Field(default=100, ge=1)
    push_to_hub: bool = Field(default=False)
    hf_repo_id: str | None = Field(default=None, description="HuggingFace repo for model upload")

    # Logging (trackio)
    project_name: str = Field(
        default="computer-rl",
        description="Project name for trackio logging",
    )
    trackio_space_id: str | None = Field(
        default=None,
        description="Optional HuggingFace Space ID for remote trackio dashboard",
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TrainingConfig":
        """Load configuration from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(**data)

    def to_yaml(self, path: str | Path) -> None:
        """Save configuration to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, sort_keys=False)
