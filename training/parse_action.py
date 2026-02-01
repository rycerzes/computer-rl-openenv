"""Action parsing from model output.

This module parses model text output into ComputerAction objects.
Supports JSON format and text-based fallback parsing.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from computer_rl_env.models import (
    Click,
    ComputerAction,
    Done,
    HotKey,
    PressKey,
    Scroll,
    TypeText,
    Wait,
)

if TYPE_CHECKING:
    pass


def parse_action_from_response(response: str) -> ComputerAction:
    """Parse model response into ComputerAction.

    Attempts JSON parsing first, then falls back to regex-based parsing.
    If all parsing fails, returns a wait action.

    Args:
        response: Model text output containing action description

    Returns:
        ComputerAction object
    """
    response = response.strip()

    # Try JSON parsing first
    try:
        return _parse_json_action(response)
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    # Try to extract JSON from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if json_match:
        try:
            return _parse_json_action(json_match.group(1))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Try to find any JSON object in the response
    json_match = re.search(r"\{[^{}]*\}", response)
    if json_match:
        try:
            return _parse_json_action(json_match.group(0))
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Fallback to text-based parsing
    try:
        return _parse_text_action(response)
    except ValueError:
        pass

    # Default: wait action
    return ComputerAction(action=Wait(seconds=1.0))


def _parse_json_action(json_str: str) -> ComputerAction:
    """Parse JSON string into ComputerAction.

    Supports both wrapped format {"action": {...}} and direct format {...}.
    """
    data = json.loads(json_str)

    # Handle wrapped format: {"action": {...}}
    if "action" in data and isinstance(data["action"], dict):
        action_data = data["action"]
    else:
        action_data = data

    action_type = action_data.get("action_type")
    if not action_type:
        raise ValueError("Missing action_type in action data")

    return _create_action_from_dict(action_type, action_data)


def _create_action_from_dict(action_type: str, data: dict) -> ComputerAction:
    """Create ComputerAction from action type and data dict."""
    action_type = action_type.lower()

    if action_type == "click":
        action = Click(
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            button=data.get("button", "left"),
            num_clicks=int(data.get("num_clicks", 1)),
        )
    elif action_type == "type":
        action = TypeText(text=str(data.get("text", "")))
    elif action_type == "press":
        action = PressKey(key=str(data.get("key", "enter")))
    elif action_type == "hotkey":
        keys = data.get("keys", [])
        if isinstance(keys, str):
            keys = [keys]
        action = HotKey(keys=list(keys))
    elif action_type == "scroll":
        action = Scroll(
            x=int(data.get("x", 500)),
            y=int(data.get("y", 500)),
            direction=data.get("direction", "down"),
            amount=int(data.get("amount", 1)),
        )
    elif action_type == "wait":
        action = Wait(seconds=float(data.get("seconds", 1.0)))
    elif action_type == "done":
        action = Done()
    else:
        # Unknown action type, default to wait
        action = Wait(seconds=1.0)

    return ComputerAction(action=action)


def _parse_text_action(text: str) -> ComputerAction:
    """Parse text-based action description using regex.

    Supports formats like:
    - "click at (x, y)"
    - "type 'text'"
    - "press Enter"
    - "scroll down"
    """
    text_lower = text.lower()

    # Click pattern: click at (x, y) or click (x, y)
    click_match = re.search(r"click\s*(?:at\s*)?\(?(\d+)\s*,\s*(\d+)\)?", text_lower)
    if click_match:
        x, y = int(click_match.group(1)), int(click_match.group(2))
        return ComputerAction(action=Click(x=x, y=y))

    # Type pattern: type "text" or type 'text'
    type_match = re.search(r"type\s*[\"']([^\"']+)[\"']", text, re.IGNORECASE)
    if type_match:
        return ComputerAction(action=TypeText(text=type_match.group(1)))

    # Press pattern: press KEY
    press_match = re.search(r"press\s+(\w+)", text_lower)
    if press_match:
        key = press_match.group(1)
        return ComputerAction(action=PressKey(key=key))

    # Scroll pattern: scroll up/down
    if "scroll down" in text_lower:
        return ComputerAction(action=Scroll(x=500, y=500, direction="down"))
    if "scroll up" in text_lower:
        return ComputerAction(action=Scroll(x=500, y=500, direction="up"))

    # Done pattern
    if "done" in text_lower or "finish" in text_lower or "complete" in text_lower:
        return ComputerAction(action=Done())

    # Wait pattern
    wait_match = re.search(r"wait\s*(\d+(?:\.\d+)?)?", text_lower)
    if wait_match:
        seconds = float(wait_match.group(1) or 1.0)
        return ComputerAction(action=Wait(seconds=min(seconds, 10.0)))

    raise ValueError(f"Could not parse action from text: {text}")


def action_to_string(action: ComputerAction) -> str:
    """Convert ComputerAction to human-readable string.

    Used for action history in prompts.
    """
    act = action.action
    action_type = act.action_type

    if action_type == "click":
        return f"click({act.x}, {act.y}, button={act.button})"
    elif action_type == "type":
        text_preview = act.text[:30] + "..." if len(act.text) > 30 else act.text
        return f"type('{text_preview}')"
    elif action_type == "press":
        return f"press({act.key})"
    elif action_type == "hotkey":
        return f"hotkey({'+'.join(act.keys)})"
    elif action_type == "scroll":
        return f"scroll({act.direction}, amount={act.amount})"
    elif action_type == "wait":
        return f"wait({act.seconds}s)"
    elif action_type == "done":
        return "done()"
    else:
        return f"unknown({action_type})"
