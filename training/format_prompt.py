"""Observation formatting for model prompts.

This module formats ComputerObservation into prompts for the VLM.
Supports both text-only (accessibility tree) and multimodal (image + tree) modes.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

    from computer_rl_env.models import ComputerObservation


def truncate_text(text: str, max_chars: int = 4000) -> str:
    """Truncate text to max_chars, adding ellipsis if truncated."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def base64_to_pil(base64_string: str) -> "Image.Image":
    """Convert base64 string to PIL Image."""
    from PIL import Image

    image_data = base64.b64decode(base64_string)
    return Image.open(BytesIO(image_data))


def format_observation_prompt(
    obs: "ComputerObservation",
    use_vision: bool = False,
    action_history: list[str] | None = None,
    max_tree_chars: int = 4000,
) -> str | tuple[str, "Image.Image"]:
    """Format observation into model prompt.

    Args:
        obs: ComputerObservation from environment
        use_vision: Whether to include screenshot as image
        action_history: Optional list of previous actions taken
        max_tree_chars: Maximum characters for accessibility tree

    Returns:
        If use_vision=False: prompt string
        If use_vision=True: tuple of (prompt string, PIL Image)
    """
    # Format accessibility tree
    acc_tree = obs.accessibility_tree or "[No accessibility tree available]"
    acc_tree = truncate_text(acc_tree, max_tree_chars)

    # Format action history if provided
    history_section = ""
    if action_history:
        recent_actions = action_history[-5:]  # Last 5 actions
        history_section = "\nRecent Actions:\n" + "\n".join(
            f"  {i + 1}. {action}" for i, action in enumerate(recent_actions)
        )

    # Format active window info
    window_info = ""
    if obs.active_window:
        window_info = f"\nActive Window: {obs.active_window}"
    if obs.active_app:
        window_info += f" ({obs.active_app})"

    # Build the prompt
    prompt = f"""=== Computer Task ===
Instruction: {obs.instruction or "No instruction provided"}

Step: {obs.step_count}
{window_info}

Accessibility Tree:
{acc_tree}
{history_section}

What action should I take next?
Respond with a JSON action in the format:
{{"action": {{"action_type": "TYPE", ...}}}}

Supported action types:
- click: {{"action_type": "click", "x": X, "y": Y, "button": "left"|"right", "num_clicks": 1|2}}
- type: {{"action_type": "type", "text": "TEXT"}}
- press: {{"action_type": "press", "key": "KEY"}}
- hotkey: {{"action_type": "hotkey", "keys": ["KEY1", "KEY2"]}}
- scroll: {{"action_type": "scroll", "x": X, "y": Y, "direction": "up"|"down", "amount": N}}
- wait: {{"action_type": "wait", "seconds": N}}
- done: {{"action_type": "done"}}

Action:"""

    if use_vision:
        image = base64_to_pil(obs.screenshot_base64)
        return (prompt, image)

    return prompt


def format_chat_messages(
    obs: "ComputerObservation",
    use_vision: bool = False,
    action_history: list[str] | None = None,
    system_prompt: str | None = None,
) -> list[dict]:
    """Format observation as chat messages for apply_chat_template.

    Args:
        obs: ComputerObservation from environment
        use_vision: Whether to include screenshot in message
        action_history: Optional list of previous actions taken
        system_prompt: Optional system prompt to prepend

    Returns:
        List of message dicts for tokenizer.apply_chat_template
    """
    if system_prompt is None:
        system_prompt = """You are a computer control agent. You can interact with a desktop environment by executing actions.
Respond with a single JSON action. Be precise with coordinates and action types."""

    user_content = format_observation_prompt(
        obs, use_vision=False, action_history=action_history
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    return messages
