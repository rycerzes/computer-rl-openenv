import logging
import os
from typing import Any, Dict

from .file import get_vm_file

logger = logging.getLogger(__name__)


def get_vlc_playing_info(env: Any, config: Dict[str, str]):
    """Get VLC status via HTTP interface (running in VM)."""

    # OSWorld used host/port. We use docker exec curl locally.
    password = "password"  # verify if this is fixed in OSWorld setup or config
    port = 8080  # Default VLC http port

    dest = config.get("dest", "vlc_status.xml")

    # We use curl inside the container to hit localhost
    # -u :password (user is empty string)
    cmd = f"curl -s -u :{password} http://localhost:{port}/requests/status.xml"

    if hasattr(env, "docker_provider") and env.docker_provider:
        content = env.docker_provider.execute(cmd)

        # Check if successful xml
        if "root" in content or "xml" in content:
            # Save to local cache
            cache_dir = getattr(env, "cache_dir", "/tmp/osworld_cache")
            os.makedirs(cache_dir, exist_ok=True)
            local_path = os.path.join(cache_dir, dest)

            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            return local_path

    logger.error("Failed to get VLC status")
    return None


def get_vlc_config(env: Any, config: Dict[str, str]):
    """Get VLC config file."""

    # Linux path
    cmd = "python3 -c \"import os; print(os.path.expanduser('~/.config/vlc/vlcrc'))\""

    config_path = ""
    if hasattr(env, "docker_provider") and env.docker_provider:
        config_path = env.docker_provider.execute(cmd).strip()

    if not config_path:
        return None

    return get_vm_file(env, {"path": config_path, "dest": config.get("dest")})


def get_default_video_player(env: Any, config: Dict[str, str]) -> str:
    """Get the default video player application.

    Queries xdg-mime for each video MIME type and returns the most common
    default application.

    Args:
        env: Environment instance with docker_provider
        config: Unused (kept for getter signature consistency)

    Returns:
        Desktop file name of the default video player (e.g. 'vlc.desktop'),
        or 'unknown' if none found
    """
    from collections import Counter

    from .general import get_vm_command_line

    extensions = [
        "3gp",
        "3gpp",
        "3gpp2",
        "avi",
        "divx",
        "dv",
        "fli",
        "flv",
        "mp2t",
        "mp4",
        "mp4v-es",
        "mpeg",
        "mpeg-system",
        "msvideo",
        "ogg",
        "quicktime",
        "vnd.divx",
        "vnd.mpegurl",
        "vnd.rn-realvideo",
        "webm",
        "x-anim",
        "x-avi",
        "x-flc",
        "x-fli",
        "x-flv",
        "x-m4v",
        "x-matroska",
        "x-mpeg",
        "x-mpeg-system",
        "x-mpeg2",
        "x-ms-asf",
        "x-ms-asf-plugin",
        "x-ms-asx",
        "x-ms-wm",
        "x-ms-wmv",
        "x-ms-wmx",
        "x-ms-wvx",
        "x-msvideo",
        "x-nsv",
        "x-ogm",
        "x-ogm+ogg",
        "x-theora",
        "x-theora+ogg",
    ]

    apps = []
    for ext in extensions:
        app = get_vm_command_line(
            env, {"command": ["xdg-mime", "query", "default", f"video/{ext}"]}
        )
        if app and app.strip():
            apps.append(app.strip())

    if not apps:
        return "unknown"

    return Counter(apps).most_common(1)[0][0]
