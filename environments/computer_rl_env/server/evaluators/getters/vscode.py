import logging
import time
from typing import Any, Dict

from .file import get_vm_file
from .replay import get_replay

logger = logging.getLogger(__name__)


def get_vscode_config(env: Any, config: Dict[str, Any]) -> str:
    """Get VSCode configuration file after triggering generation via hotkeys."""

    # OSWorld logic: invoke extension command via palette to dump config to file
    vscode_extension_command = config.get("vscode_extension_command", "")

    # We assume standard Linux hotkeys for VSCode as per Dockerfile
    trajectory = [
        {"type": "hotkey", "param": ["ctrl", "shift", "p"]},
        {"type": "typewrite", "param": vscode_extension_command},
        {"type": "press", "param": "enter"},
    ]

    get_replay(env, trajectory)
    time.sleep(1.0)

    # Now fetch the file
    return get_vm_file(env, {"path": config.get("path"), "dest": config.get("dest")})
