import os
import subprocess


def evaluate_text_present(text: str, location: str = "screen") -> bool:
    if location == "clipboard":
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and text in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            return False
    elif location == "screen":
        try:
            accessibility_tree = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return accessibility_tree.returncode == 0 and text in accessibility_tree.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            return False
    elif location == "terminal":
        try:
            history_file = os.path.expanduser("~/.bash_history")
            with open(history_file, "r") as f:
                content = f.read()
            return text in content
        except (OSError, IOError):
            return False

    return False
