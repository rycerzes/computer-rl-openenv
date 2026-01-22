"""Rollout functions for TRL GRPO training.

This module provides the rollout functions for collecting experience
from the Computer RL environment during GRPO training.

Key functions:
- rollout_episode: Execute single task episode (synchronous)
- rollout_func: TRL-compatible rollout function for GRPOTrainer
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from computer_rl_env import ComputerEnvClient
from computer_rl_env.models import ComputerAction, Done, Wait

from .format_prompt import format_chat_messages
from .parse_action import action_to_string, parse_action_from_response

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizer
    from trl import GRPOTrainer

    from computer_rl_env.models import ComputerObservation


logger = logging.getLogger(__name__)


def rollout_episode(
    env: ComputerEnvClient,
    trainer: "GRPOTrainer",
    task_instruction: str,
    tokenizer: "PreTrainedTokenizer",
    max_steps: int = 50,
    use_vision: bool = False,
) -> dict[str, Any]:
    """Execute one task episode and collect rollout data (synchronous).

    This function runs a complete episode in the environment:
    1. Reset environment with task instruction
    2. Loop: observe → generate → parse → step
    3. Collect token IDs and log probabilities for each step
    4. Return episode data for training

    Args:
        env: Connected ComputerEnvClient instance
        trainer: GRPOTrainer instance (for generation)
        task_instruction: The task instruction/prompt
        tokenizer: Tokenizer for encoding/decoding
        max_steps: Maximum steps per episode
        use_vision: Whether to use vision model with screenshots

    Returns:
        Dict containing:
        - prompt_ids: List of token IDs for all prompts
        - completion_ids: List of token IDs for all completions
        - logprobs: List of log probabilities for all tokens
        - final_reward: Environment reward at end of episode
        - num_steps: Number of steps taken
        - actions: List of action type strings
        - success: Whether task was completed successfully
    """
    # Import here to avoid circular imports and ensure TRL is available
    from trl.experimental.openenv import generate_rollout_completions

    # Reset environment with task config
    result = env.reset(task_config={"instruction": task_instruction})
    obs: ComputerObservation = result.observation
    done = False
    step = 0

    # Accumulate data across all steps
    all_prompt_ids: list[int] = []
    all_completion_ids: list[int] = []
    all_logprobs: list[float] = []
    actions: list[str] = []
    action_history: list[str] = []

    while not done and step < max_steps:
        # Format observation to chat messages
        messages = format_chat_messages(
            obs,
            use_vision=use_vision,
            action_history=action_history,
        )

        # Apply chat template to get prompt text
        prompt_text = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False,
        )

        # Generate completion using TRL helper
        # Works for both colocate and server vLLM modes
        try:
            outputs = generate_rollout_completions(trainer, [prompt_text])[0]
        except Exception as e:
            logger.warning(f"Generation failed at step {step}: {e}")
            # On generation failure, wait and retry or break
            break

        # Accumulate token data
        all_prompt_ids.extend(outputs["prompt_ids"])
        all_completion_ids.extend(outputs["completion_ids"])
        all_logprobs.extend(outputs["logprobs"])

        # Decode completion text
        completion_text = outputs.get("text") or tokenizer.decode(
            outputs["completion_ids"], skip_special_tokens=True
        )

        # Parse action from model output
        try:
            action = parse_action_from_response(completion_text)
        except Exception as e:
            logger.warning(f"Action parsing failed: {e}, using wait action")
            action = ComputerAction(action=Wait(seconds=1.0))

        action_type = action.action.action_type
        actions.append(action_type)
        action_history.append(action_to_string(action))

        # Check if model signaled done
        if isinstance(action.action, Done):
            done = True
            break

        # Execute action in environment (synchronous call)
        try:
            result = env.step(action)
            obs = result.observation
            done = result.done
        except Exception as e:
            logger.error(f"Environment step failed: {e}")
            break

        step += 1

    # Compute success based on reward
    final_reward = result.reward if result.reward is not None else 0.0
    success = final_reward > 0.0 if done else False

    return {
        "prompt_ids": all_prompt_ids,
        "completion_ids": all_completion_ids,
        "logprobs": all_logprobs,
        "final_reward": final_reward,
        "num_steps": step,
        "actions": actions,
        "success": success,
    }


def rollout_func(
    prompts: list[str],
    trainer: "GRPOTrainer",
) -> dict[str, list]:
    """TRL-compatible rollout function for GRPOTrainer.

    This function is passed to GRPOTrainer.rollout_func and handles:
    1. Connecting to the environment server
    2. Running episodes for each prompt (task instruction)
    3. Collecting and returning rollout data

    Args:
        prompts: List of prompts (task instructions) from dataset
        trainer: GRPOTrainer instance (access tokenizer, config, generation)

    Returns:
        Dict with required fields for GRPO training:
        - prompt_ids: List of token ID lists for each prompt
        - completion_ids: List of token ID lists for each completion
        - logprobs: List of logprob lists for each completion
        Plus custom fields forwarded to reward functions:
        - task_reward: List of final task rewards (1.0 success, 0.0 failure)
        - num_steps: List of step counts per episode
        - actions: List of action sequences per episode
    """
    tokenizer = trainer.processing_class

    # Get configuration from trainer args
    # These are custom fields we add to GRPOConfig
    openenv_server_url = getattr(
        trainer.args, "openenv_server_url", "http://localhost:8000"
    )
    max_steps = getattr(trainer.args, "max_episode_steps", 50)
    use_vision = getattr(trainer.args, "use_vision", False)
    num_parallel_envs = getattr(trainer.args, "num_parallel_envs", 1)

    # Collect results
    all_prompt_ids: list[list[int]] = []
    all_completion_ids: list[list[int]] = []
    all_logprobs: list[list[float]] = []
    task_rewards: list[float] = []
    num_steps: list[int] = []
    all_actions: list[list[str]] = []

    def run_single_episode(prompt: str) -> dict[str, Any]:
        """Run a single episode for one prompt."""
        env = ComputerEnvClient(base_url=openenv_server_url)
        try:
            env.connect()
            episode = rollout_episode(
                env=env,
                trainer=trainer,
                task_instruction=prompt,
                tokenizer=tokenizer,
                max_steps=max_steps,
                use_vision=use_vision,
            )
            return episode
        finally:
            try:
                env.close()
            except Exception:
                pass

    if num_parallel_envs > 1 and len(prompts) > 1:
        # Parallel execution with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=num_parallel_envs) as executor:
            futures = {
                executor.submit(run_single_episode, prompt): i
                for i, prompt in enumerate(prompts)
            }

            # Collect results in order
            results = [None] * len(prompts)
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Episode {idx} failed: {e}")
                    # Return empty episode on failure
                    results[idx] = {
                        "prompt_ids": [],
                        "completion_ids": [],
                        "logprobs": [],
                        "final_reward": 0.0,
                        "num_steps": 0,
                        "actions": [],
                        "success": False,
                    }

            for episode in results:
                all_prompt_ids.append(episode["prompt_ids"])
                all_completion_ids.append(episode["completion_ids"])
                all_logprobs.append(episode["logprobs"])
                task_rewards.append(1.0 if episode["success"] else 0.0)
                num_steps.append(episode["num_steps"])
                all_actions.append(episode["actions"])
    else:
        # Sequential execution
        for prompt in prompts:
            try:
                episode = run_single_episode(prompt)
            except Exception as e:
                logger.error(f"Episode failed: {e}")
                episode = {
                    "prompt_ids": [],
                    "completion_ids": [],
                    "logprobs": [],
                    "final_reward": 0.0,
                    "num_steps": 0,
                    "actions": [],
                    "success": False,
                }

            all_prompt_ids.append(episode["prompt_ids"])
            all_completion_ids.append(episode["completion_ids"])
            all_logprobs.append(episode["logprobs"])
            task_rewards.append(1.0 if episode["success"] else 0.0)
            num_steps.append(episode["num_steps"])
            all_actions.append(episode["actions"])

    # Return required fields + custom fields for reward functions
    return {
        # Required fields for GRPO
        "prompt_ids": all_prompt_ids,
        "completion_ids": all_completion_ids,
        "logprobs": all_logprobs,
        # Custom fields → forwarded to reward_funcs via **kwargs
        "task_reward": task_rewards,
        "num_steps": num_steps,
        "actions": all_actions,
    }


def create_rollout_func(
    openenv_server_url: str = "http://localhost:8000",
    max_steps: int = 50,
    use_vision: bool = False,
    num_parallel_envs: int = 1,
):
    """Factory function to create a rollout_func with custom configuration.

    Use this when you need to customize rollout parameters without
    modifying trainer.args.

    Args:
        openenv_server_url: URL of the Computer RL environment server
        max_steps: Maximum steps per episode
        use_vision: Whether to use vision model with screenshots
        num_parallel_envs: Number of parallel environment instances

    Returns:
        A rollout function compatible with GRPOTrainer.rollout_func
    """

    def custom_rollout_func(
        prompts: list[str],
        trainer: "GRPOTrainer",
    ) -> dict[str, list]:
        tokenizer = trainer.processing_class

        all_prompt_ids: list[list[int]] = []
        all_completion_ids: list[list[int]] = []
        all_logprobs: list[list[float]] = []
        task_rewards: list[float] = []
        step_counts: list[int] = []
        all_actions: list[list[str]] = []

        def run_single_episode(prompt: str) -> dict[str, Any]:
            env = ComputerEnvClient(base_url=openenv_server_url)
            try:
                env.connect()
                return rollout_episode(
                    env=env,
                    trainer=trainer,
                    task_instruction=prompt,
                    tokenizer=tokenizer,
                    max_steps=max_steps,
                    use_vision=use_vision,
                )
            finally:
                try:
                    env.close()
                except Exception:
                    pass

        if num_parallel_envs > 1 and len(prompts) > 1:
            with ThreadPoolExecutor(max_workers=num_parallel_envs) as executor:
                futures = {
                    executor.submit(run_single_episode, prompt): i
                    for i, prompt in enumerate(prompts)
                }
                results = [None] * len(prompts)
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        logger.error(f"Episode {idx} failed: {e}")
                        results[idx] = {
                            "prompt_ids": [],
                            "completion_ids": [],
                            "logprobs": [],
                            "final_reward": 0.0,
                            "num_steps": 0,
                            "actions": [],
                            "success": False,
                        }
                for episode in results:
                    all_prompt_ids.append(episode["prompt_ids"])
                    all_completion_ids.append(episode["completion_ids"])
                    all_logprobs.append(episode["logprobs"])
                    task_rewards.append(1.0 if episode["success"] else 0.0)
                    step_counts.append(episode["num_steps"])
                    all_actions.append(episode["actions"])
        else:
            for prompt in prompts:
                try:
                    episode = run_single_episode(prompt)
                except Exception as e:
                    logger.error(f"Episode failed: {e}")
                    episode = {
                        "prompt_ids": [],
                        "completion_ids": [],
                        "logprobs": [],
                        "final_reward": 0.0,
                        "num_steps": 0,
                        "actions": [],
                        "success": False,
                    }
                all_prompt_ids.append(episode["prompt_ids"])
                all_completion_ids.append(episode["completion_ids"])
                all_logprobs.append(episode["logprobs"])
                task_rewards.append(1.0 if episode["success"] else 0.0)
                step_counts.append(episode["num_steps"])
                all_actions.append(episode["actions"])

        return {
            "prompt_ids": all_prompt_ids,
            "completion_ids": all_completion_ids,
            "logprobs": all_logprobs,
            "task_reward": task_rewards,
            "num_steps": step_counts,
            "actions": all_actions,
        }

    return custom_rollout_func
