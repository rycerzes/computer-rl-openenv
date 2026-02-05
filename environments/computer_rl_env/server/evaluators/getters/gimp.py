import logging
from typing import Any, Dict

from .file import get_vm_file

logger = logging.getLogger(__name__)


def get_gimp_config_file(env: Any, config: Dict[str, Any]):
    """Get GIMP config file."""

    file_name = config.get("file_name", "")

    # We need to find where the config file is.
    # OSWorld used execute_python_command to expand user path.
    # We can do the same via python -c or bash expansion.

    # Assuming Linux (Docker container)
    cmd = f"python3 -c \"import os; print(os.path.expanduser('~/.config/GIMP/2.10/{file_name}'))\""

    config_path = ""
    if hasattr(env, "docker_provider") and env.docker_provider:
        try:
            config_path = env.docker_provider.execute(cmd).strip()
        except Exception as e:
            logger.error(f"Failed to resolve GIMP config path: {e}")
            return None

    if not config_path:
        return None

    return get_vm_file(env, {"path": config_path, "dest": config.get("dest")})
