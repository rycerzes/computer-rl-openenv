"""File getters for evaluation."""

import logging
import os
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def get_content_from_vm_file(env: Any, config: Dict[str, Any]) -> Any:
    """Read file content directly from VM.

    Downloads the file via get_vm_file, then extracts content based on
    file_type and file_content parameters.

    Args:
        env: Environment instance with docker_provider and cache_dir
        config: Contains:
            - path (str): absolute path on the VM
            - file_type (str): 'xlsx' or 'text'
            - file_content (str): e.g. 'last_row' for xlsx

    Returns:
        Extracted content (list for xlsx last_row, string for text), or None if failed
    """
    path = config["path"]
    file_path = get_vm_file(env, {"path": path, "dest": os.path.basename(path)})
    if file_path is None:
        logger.error(f"Failed to get file from VM: {path}")
        return None

    file_type = config.get("file_type", "text")
    file_content = config.get("file_content", "")

    if file_type == "xlsx":
        import pandas as pd

        if file_content == "last_row":
            df = pd.read_excel(file_path)
            last_row = df.iloc[-1]
            return last_row.astype(str).tolist()
        else:
            raise NotImplementedError(f"xlsx content type '{file_content}' not supported")
    elif file_type == "text":
        with open(file_path, "r") as f:
            return f.read()
    else:
        raise NotImplementedError(f"File type '{file_type}' not supported")


def get_vm_file(env: Any, config: Dict[str, Any]) -> Optional[str]:
    """Download file from VM and return local path.

    Args:
        env: Environment instance with docker_provider and cache_dir
        config: Contains:
            - path: Absolute path on the VM to fetch
            - dest: Filename for the downloaded file

    Returns:
        Local path to downloaded file, or None if failed
    """
    vm_path = config.get("path", "")
    dest_name = config.get("dest", os.path.basename(vm_path))

    # Get cache directory
    cache_dir = getattr(env, "cache_dir", "/tmp/osworld_cache")
    os.makedirs(cache_dir, exist_ok=True)
    local_path = os.path.join(cache_dir, dest_name)

    # Try to get file from VM via docker
    if hasattr(env, "docker_provider") and env.docker_provider:
        try:
            # Use docker cp or cat command
            container = env.docker_provider.container
            if container:
                # Read file content
                result = container.exec_run(f"cat {vm_path}")
                if result.exit_code == 0:
                    with open(local_path, "wb") as f:
                        f.write(result.output)
                    logger.info(f"Downloaded {vm_path} to {local_path}")
                    return local_path
                else:
                    logger.error(f"Failed to read {vm_path}: {result.output.decode()}")
                    return None
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None

    # Fallback: check if local path exists (for local testing)
    if os.path.exists(vm_path):
        return vm_path

    logger.warning(f"File not found: {vm_path}")
    return None


def get_cache_file(env: Any, config: Dict[str, Any]) -> str:
    """Get path to a file in the cache directory.

    Args:
        env: Environment instance with cache_dir
        config: Contains "path" - relative path in cache dir

    Returns:
        Absolute path to the cached file
    """
    cache_dir = getattr(env, "cache_dir", "/tmp/osworld_cache")
    relative_path = config.get("path", "")
    return os.path.join(cache_dir, relative_path)


def get_cloud_file(env: Any, config: Dict[str, Any]) -> Union[str, List[str]]:
    """Download file from cloud URL.

    Args:
        env: Environment instance with cache_dir
        config: Contains:
            - path: URL to download from
            - dest: Filename for the downloaded file

    Returns:
        Local path to downloaded file
    """
    import requests

    url = config.get("path", "")
    dest_name = config.get("dest", "downloaded_file")
    cache_dir = getattr(env, "cache_dir", "/tmp/osworld_cache")
    os.makedirs(cache_dir, exist_ok=True)
    local_path = os.path.join(cache_dir, dest_name)

    if os.path.exists(local_path):
        return local_path

    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logger.info(f"Downloaded {url} to {local_path}")
        return local_path
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return None
