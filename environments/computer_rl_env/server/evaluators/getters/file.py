"""File getters for evaluation."""

import logging
import os
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


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
