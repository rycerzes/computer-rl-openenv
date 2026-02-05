import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def get_replay(env: Any, trajectory: List[Dict[str, Any]]) -> None:
    """Replay a sequence of actions (hotkeys, typing, etc.) in the VM."""

    if not trajectory:
        return

    script_lines = ["import pyautogui", "import time", "pyautogui.FAILSAFE = False"]

    for action in trajectory:
        act_type = action.get("type")
        param = action.get("param")

        if act_type == "hotkey":
            # param is list of keys e.g. ["ctrl", "c"]
            if isinstance(param, list):
                keys = "', '".join(param)
                script_lines.append(f"pyautogui.hotkey('{keys}')")

        elif act_type == "typewrite":
            # param is text string
            # Escape single quotes
            text = str(param).replace("'", "\\'")
            script_lines.append(f"pyautogui.typewrite('{text}')")

        elif act_type == "press":
            # param is key string
            script_lines.append(f"pyautogui.press('{param}')")

        elif act_type == "sleep":
            script_lines.append(f"time.sleep({param})")

    full_script = "; ".join(script_lines)

    if hasattr(env, "docker_provider") and env.docker_provider:
        logger.info(f"Executing replay script: {full_script[:100]}...")
        # Escape double quotes for bash argument
        safe_script = full_script.replace('"', '\\"')
        cmd = f'python3 -c "{safe_script}"'
        env.docker_provider.execute(cmd)
