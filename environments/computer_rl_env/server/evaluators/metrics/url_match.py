import re
import subprocess


def evaluate_url_match(expected_url: str, tolerance: str = "exact") -> bool:
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        window_title = result.stdout.strip()

        if tolerance == "exact":
            return expected_url == window_title
        elif tolerance == "contains":
            return expected_url in window_title
        elif tolerance == "prefix":
            return window_title.startswith(expected_url)
        elif tolerance == "regex":
            return bool(re.search(expected_url, window_title))

        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False
