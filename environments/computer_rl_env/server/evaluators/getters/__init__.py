"""OSWorld-compatible getters for evaluation."""

import logging
import sys
from typing import Any, Callable, Dict

from .calc import get_conference_city_in_order
from .file import get_cache_file, get_cloud_file, get_content_from_vm_file, get_vm_file
from .general import get_rule, get_vm_command_error, get_vm_command_line, get_vm_terminal_output
from .gimp import get_gimp_config_file
from .impress import get_audio_in_slide, get_background_image_in_slide

# Import ported getters
from .info import get_list_directory, get_vm_screen_size, get_vm_wallpaper, get_vm_window_size
from .misc import get_accessibility_tree, get_rule_relativetime, get_time_diff_range
from .replay import get_replay
from .vlc import get_default_video_player, get_vlc_config, get_vlc_playing_info
from .vscode import get_vscode_config

logger = logging.getLogger(__name__)

# Getter function type
Getter = Callable[[Any, Dict[str, Any]], Any]

# Registry of getters
GETTER_REGISTRY: Dict[str, Getter] = {
    "rule": get_rule,
    "vm_command_line": get_vm_command_line,
    "vm_command_error": get_vm_command_error,
    "vm_terminal_output": get_vm_terminal_output,
    "vm_file": get_vm_file,
    "content_from_vm_file": get_content_from_vm_file,
    "cache_file": get_cache_file,
    "cloud_file": get_cloud_file,
    # Info
    "vm_screen_size": get_vm_screen_size,
    "vm_window_size": get_vm_window_size,
    "vm_wallpaper": get_vm_wallpaper,
    "list_directory": get_list_directory,
    # Replay
    "replay": get_replay,
    # App specific
    "vlc_playing_info": get_vlc_playing_info,
    "vlc_config": get_vlc_config,
    "default_video_player": get_default_video_player,
    "vscode_config": get_vscode_config,
    "gimp_config_file": get_gimp_config_file,
    "conference_city_in_order": get_conference_city_in_order,
    "background_image_in_slide": get_background_image_in_slide,
    "audio_in_slide": get_audio_in_slide,
    # Misc
    "accessibility_tree": get_accessibility_tree,
    "rule_relativeTime": get_rule_relativetime,
    "time_diff_range": get_time_diff_range,
}


def register_getter(name: str, func: Getter) -> None:
    """Register a getter function."""
    GETTER_REGISTRY[name] = func


def get_result(getter_type: str, env: Any, config: Dict[str, Any]) -> Any:
    """Fetch result using the specified getter.

    Uses explicit registry first, then falls back to OSWorld-style
    auto-discovery via getattr(module, "get_{type}").
    """
    getter_func = GETTER_REGISTRY.get(getter_type)
    if getter_func is None:
        # Fallback: try OSWorld-style auto-discovery
        module = sys.modules[__name__]
        getter_func = getattr(module, f"get_{getter_type}", None)
        if getter_func is not None:
            # Auto-register for future lookups
            GETTER_REGISTRY[getter_type] = getter_func
            logger.info(f"Auto-discovered getter: get_{getter_type}")
        else:
            raise ValueError(f"Unknown getter type: {getter_type}")
    return getter_func(env, config)


__all__ = [
    "GETTER_REGISTRY",
    "register_getter",
    "get_result",
]
