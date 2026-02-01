"""Reward functions for TRL GRPO training."""


def reward_task_success(completions: list[str], **kwargs) -> list[float]:
    """
    Reward based on final task success.
    Extracted from rollout_func's 'task_reward' field.

    Args:
        completions: List of model completions (unused)
        **kwargs: Must contain 'task_reward' list from rollout_func

    Returns:
        List of rewards (1.0 for success, 0.0 for failure)
    """
    task_rewards = kwargs.get("task_reward", [])
    if not task_rewards:
        return [0.0] * len(completions)
    return [float(r) for r in task_rewards]


def reward_efficiency(completions: list[str], **kwargs) -> list[float]:
    """
    Reward for efficiency (fewer steps = better).
    Extracted from rollout_func's 'num_steps' field.

    Logic: -0.01 per step, capped at -1.0 (100 steps).

    Args:
        completions: List of model completions (unused)
        **kwargs: Must contain 'num_steps' list from rollout_func

    Returns:
        List of efficiency penalties (negative values)
    """
    num_steps = kwargs.get("num_steps", [])
    if not num_steps:
        return [0.0] * len(completions)

    rewards = []
    for steps in num_steps:
        # Fewer steps = higher reward (less penalty)
        # Max penalty -1.0 corresponding to 100 steps
        reward = -0.01 * min(steps, 100)
        rewards.append(reward)
    return rewards


def reward_action_diversity(completions: list[str], **kwargs) -> list[float]:
    """
    Reward for diverse actions (penalize repeated consecutive actions).
    Extracted from rollout_func's 'actions' field.

    Logic: -0.05 per consecutive repetition.

    Args:
        completions: List of model completions (unused)
        **kwargs: Must contain 'actions' list from rollout_func

    Returns:
        List of diversity penalties (negative values)
    """
    all_actions = kwargs.get("actions", [])
    if not all_actions:
        return [0.0] * len(completions)

    rewards = []
    for actions in all_actions:
        if not actions or len(actions) < 2:
            rewards.append(0.0)
            continue

        # Count repeated consecutive actions
        repeated = 0
        for i in range(1, len(actions)):
            # Check for identical consecutive actions
            if actions[i] == actions[i - 1]:
                repeated += 1

        # Penalty for spamming same action
        spam_penalty = repeated * -0.05
        # Cap penalty at -1.0
        spam_penalty = max(spam_penalty, -1.0)
        rewards.append(spam_penalty)

    return rewards
