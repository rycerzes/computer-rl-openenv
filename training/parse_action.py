"""Action parsing from model output.

This module parses model text output into ComputerAction objects.
The model output is expected to be a pyautogui-style Python string
(e.g. 'pyautogui.click(x=500, y=300)') or a sentinel ('WAIT', 'DONE', 'FAIL').
"""

from __future__ import annotations

import re

from computer_rl_env.models import ComputerAction

# Sentinel strings that indicate special actions
_SENTINELS = {"WAIT", "DONE", "FAIL"}


def parse_action_from_response(response: str) -> ComputerAction:
    """Parse model response into ComputerAction.

    Extracts pyautogui-style action string from model output.
    Handles code blocks, sentinel strings, and raw pyautogui calls.
    If all parsing fails, returns a WAIT action.

    Args:
        response: Model text output containing action description

    Returns:
        ComputerAction with pyautogui string or sentinel
    """
    action_str = response.strip()

    # Check for sentinel strings first
    if action_str.upper() in _SENTINELS:
        return ComputerAction(action=action_str.upper())

    # Extract from markdown code blocks (```python ... ``` or ``` ... ```)
    code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", action_str, re.DOTALL)
    if code_match:
        action_str = code_match.group(1).strip()

    # Check for sentinels in text content
    lower = action_str.lower()
    if any(s in lower for s in ("done()", "finish", "complete", "task complete")):
        return ComputerAction(action="DONE")
    if any(s in lower for s in ("fail()", "impossible", "infeasible", "cannot")):
        return ComputerAction(action="FAIL")

    # Filter to only non-empty, non-comment lines
    lines = [
        line.strip()
        for line in action_str.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not lines:
        return ComputerAction(action="WAIT")

    # If lines contain pyautogui calls, join them
    pyautogui_lines = [
        line for line in lines if line.startswith("pyautogui.") or line.startswith("time.")
    ]
    if pyautogui_lines:
        action_str = "; ".join(pyautogui_lines)
    else:
        # Try to use the last non-empty line as the action
        action_str = lines[-1]

    # If it doesn't look like a pyautogui call, default to WAIT
    if not (
        action_str.startswith("pyautogui.")
        or action_str.startswith("time.")
        or action_str.upper() in _SENTINELS
    ):
        return ComputerAction(action="WAIT")

    return ComputerAction(action=action_str)


def action_to_string(action: ComputerAction) -> str:
    """Convert ComputerAction to human-readable string.

    Used for action history in prompts.
    Since action.action is already a string, this is a simple passthrough.
    """
    return action.action
