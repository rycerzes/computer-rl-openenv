"""OSWorld-compatible getters for evaluation."""

import logging
import sys
from typing import Any, Callable, Dict

from .calc import get_conference_city_in_order
from .chrome import (
    get_active_tab_html_parse,
    get_active_tab_info,
    get_active_tab_url_parse,
    get_active_url_from_accessTree,
    get_bookmarks,
    get_chrome_font_size,
    get_chrome_language,
    get_chrome_saved_address,
    get_cookie_data,
    get_data_delete_automacally,
    get_default_search_engine,
    get_enable_do_not_track,
    get_enable_safe_browsing,
    get_enable_enhanced_safety_browsing,
    get_enabled_experiments,
    get_extensions_installed_from_shop,
    get_find_installed_extension_name,
    get_find_unpacked_extension_path,
    get_gotoRecreationPage_and_get_html_content,
    get_googledrive_file,
    get_history,
    get_info_from_website,
    get_macys_product_url_parse,
    get_new_startup_page,
    get_number_of_search_results,
    get_open_tabs_info,
    get_page_info,
    get_pdf_from_url,
    get_profile_name,
    get_shortcuts_on_desktop,
    get_url_dashPart,
    get_url_path_parse,
)
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
    # Chrome - file-based
    "default_search_engine": get_default_search_engine,
    "cookie_data": get_cookie_data,
    "history": get_history,
    "enabled_experiments": get_enabled_experiments,
    "profile_name": get_profile_name,
    "chrome_language": get_chrome_language,
    "chrome_font_size": get_chrome_font_size,
    "bookmarks": get_bookmarks,
    "extensions_installed_from_shop": get_extensions_installed_from_shop,
    "enable_do_not_track": get_enable_do_not_track,
    "enable_safe_browsing": get_enable_safe_browsing,
    "enable_enhanced_safety_browsing": get_enable_enhanced_safety_browsing,
    "new_startup_page": get_new_startup_page,
    "find_unpacked_extension_path": get_find_unpacked_extension_path,
    "find_installed_extension_name": get_find_installed_extension_name,
    "data_delete_automacally": get_data_delete_automacally,
    # Chrome - CDP / Playwright based
    "info_from_website": get_info_from_website,
    "page_info": get_page_info,
    "open_tabs_info": get_open_tabs_info,
    "active_tab_info": get_active_tab_info,
    "pdf_from_url": get_pdf_from_url,
    "chrome_saved_address": get_chrome_saved_address,
    "number_of_search_results": get_number_of_search_results,
    "active_tab_html_parse": get_active_tab_html_parse,
    "gotoRecreationPage_and_get_html_content": get_gotoRecreationPage_and_get_html_content,
    "googledrive_file": get_googledrive_file,
    # Chrome - accessibility tree / URL parsing
    "active_url_from_accessTree": get_active_url_from_accessTree,
    "active_tab_url_parse": get_active_tab_url_parse,
    "url_dashPart": get_url_dashPart,
    "macys_product_url_parse": get_macys_product_url_parse,
    "url_path_parse": get_url_path_parse,
    # Chrome - desktop shortcuts
    "shortcuts_on_desktop": get_shortcuts_on_desktop,
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
