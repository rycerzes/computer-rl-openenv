import importlib.util
import site
import sys
from pathlib import Path


def _ensure_system_dist_packages() -> None:
    """Add Debian system dist-packages paths for pyatspi in venv runtime."""
    candidates = [
        Path("/usr/lib/python3/dist-packages"),
        Path(f"/usr/lib/python{sys.version_info.major}/dist-packages"),
        Path(f"/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/dist-packages"),
    ]
    for path in candidates:
        if path.exists():
            site.addsitedir(str(path))


def is_pyatspi_available() -> bool:
    _ensure_system_dist_packages()
    if importlib.util.find_spec("pyatspi") is None:
        return False
    try:
        import pyatspi  # noqa: F401
    except Exception:
        return False
    return True


def import_pyatspi():
    _ensure_system_dist_packages()
    import pyatspi

    return pyatspi
