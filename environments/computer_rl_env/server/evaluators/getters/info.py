import logging
import os
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def get_vm_screen_size(env: Any, config: Dict[str, Any]) -> Dict[str, int]:
    """Get VM screen size using xdpyinfo or pyautogui."""

    # Try using Python/pyautogui first as it's cleaner
    cmd = "python3 -c 'import pyautogui; print(pyautogui.size())'"
    if hasattr(env, "docker_provider") and env.docker_provider:
        output = env.docker_provider.execute(cmd).strip()
        # Output format: Size(width=1920, height=1080)
        match = re.search(r"width=(\d+),\s*height=(\d+)", output)
        if match:
            return {"width": int(match.group(1)), "height": int(match.group(2))}

        # Fallback to xdpyinfo
        cmd = "xdpyinfo | grep dimensions"
        output = env.docker_provider.execute(cmd).strip()
        # Output format: dimensions:    1920x1080 pixels (508x285 millimeters)
        match = re.search(r"(\d+)x(\d+)\s+pixels", output)
        if match:
            return {"width": int(match.group(1)), "height": int(match.group(2))}

    logger.error("Failed to get screen size")
    return {"width": 0, "height": 0}


def get_vm_window_size(env: Any, config: Dict[str, Any]) -> Dict[str, int]:
    """Get window size for a specific app class using xdotool."""
    app_class = config.get("app_class_name", "")
    if not app_class:
        logger.error("No app_class_name provided for get_vm_window_size")
        return {"width": 0, "height": 0}

    if hasattr(env, "docker_provider") and env.docker_provider:
        # Search for window and get geometry
        # %w and %h gives width and height
        cmd = f"xdotool search --onlyvisible --class '{app_class}' getwindowgeometry --shell"
        output = env.docker_provider.execute(cmd).strip()

        # Output format usually:
        # WINDOW=...
        # X=...
        # Y=...
        # WIDTH=...
        # HEIGHT=...

        width = 0
        height = 0
        for line in output.splitlines():
            if line.startswith("WIDTH="):
                width = int(line.split("=")[1])
            elif line.startswith("HEIGHT="):
                height = int(line.split("=")[1])

        if width and height:
            return {"width": width, "height": height}

    logger.warning(f"Failed to get window size for {app_class}")
    return {"width": 0, "height": 0}


def get_vm_wallpaper(env: Any, config: Dict[str, Any]) -> str:
    """Get VM wallpaper.

    In OSWorld this returned the CONTENT of the wallpaper file.
    Here we should probably fetch the file.
    """
    dest = config.get("dest", "wallpaper.png")
    cache_dir = getattr(env, "cache_dir", "/tmp/osworld_cache")
    os.makedirs(cache_dir, exist_ok=True)
    local_path = os.path.join(cache_dir, dest)

    if hasattr(env, "docker_provider") and env.docker_provider:
        # Try to find wallpaper path for XFCE
        cmd = "xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/workspace0/last-image"
        wallpaper_path = env.docker_provider.execute(cmd).strip()

        if wallpaper_path and "not found" not in wallpaper_path.lower():
            # Download it using existing vm_file getter logic or direct cat
            result = env.docker_provider.container.exec_run(f"cat '{wallpaper_path}'")
            if result.exit_code == 0:
                with open(local_path, "wb") as f:
                    f.write(result.output)
                return local_path

    # Fallback or error
    logger.warning("Could not retrieve wallpaper")
    # Create empty file as OSWorld does on failure
    with open(local_path, "wb") as f:
        f.write(b"")
    return local_path


def get_list_directory(env: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """Get directory tree structure."""
    path = config.get("path", ".")

    # Python script to traverse directory and dump JSON
    script_content = r"""
import os
import json
import sys

def get_tree(start_path):
    try:
        name = os.path.basename(start_path)
        if not name: # handling root
            name = start_path

        tree = {"name": name, "type": "directory", "children": []}

        with os.scandir(start_path) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        tree["children"].append(get_tree(entry.path))
                    else:
                        tree["children"].append({"name": entry.name, "type": "file"})
                except OSError:
                    continue
    except OSError as e:
        return {"name": os.path.basename(start_path), "error": str(e)}
    return tree

try:
    print(json.dumps(get_tree("TARGET_PATH")))
except Exception as e:
    print(json.dumps({"error": str(e)}))
"""
    script_content = script_content.replace("TARGET_PATH", path)

    if hasattr(env, "docker_provider") and env.docker_provider:
        # Write script to a file
        temp_script = "/tmp/list_dir_script.py"
        try:
            # We use a simple echo to write the script, identifying newlines might be tricky with echo
            # Safer to use base64
            import base64

            b64_script = base64.b64encode(script_content.encode("utf-8")).decode("utf-8")

            # Write and execute
            cmd = (
                f"bash -c 'echo {b64_script} | base64 -d > {temp_script} && python3 {temp_script}'"
            )
            output = env.docker_provider.execute(cmd).strip()

            import json

            return json.loads(output)
        except Exception as e:
            logger.error(f"Failed to get directory tree: {e}")
            logger.error(f"Output was: {output if 'output' in locals() else 'N/A'}")

    return {}
