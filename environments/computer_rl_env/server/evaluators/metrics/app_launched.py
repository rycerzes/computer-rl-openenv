import subprocess


def evaluate_app_launched(app_name: str) -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", app_name],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        return False
