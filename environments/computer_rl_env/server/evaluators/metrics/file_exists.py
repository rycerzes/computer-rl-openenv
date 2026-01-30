import os


def evaluate_file_exists(filepath: str, must_contain: str | None = None) -> bool:
    if not os.path.exists(filepath):
        return False

    if must_contain is None:
        return True

    try:
        with open(filepath, "r") as f:
            content = f.read()
        return must_contain in content
    except (OSError, IOError, UnicodeDecodeError):
        return False
