"""Chrome getters for evaluation.

Adapted from OSWorld/ComputerRL Chrome getters for in-container execution.
Instead of using env.controller.get_file() / execute_python_command() (remote),
these getters read local files directly and connect to Chrome CDP on localhost.

Chrome DevTools Protocol (CDP) runs on port 1337, configured in supervisord.conf
with flags: --no-sandbox --disable-dev-shm-usage --disable-gpu
           --remote-debugging-port=1337 --remote-debugging-address=0.0.0.0
"""

import json
import logging
import os
import sqlite3
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import lxml.etree
from lxml.cssselect import CSSSelector

logger = logging.getLogger(__name__)

# Accessibility tree namespace map (for URL extraction from Chrome address bar)
_accessibility_ns_map = {
    "st": "uri:deskat:state.at-spi.gnome.org",
    "attr": "uri:deskat:attributes.at-spi.gnome.org",
    "cp": "uri:deskat:component.at-spi.gnome.org",
    "doc": "uri:deskat:document.at-spi.gnome.org",
    "docattr": "uri:deskat:attributes.document.at-spi.gnome.org",
    "txt": "uri:deskat:text.at-spi.gnome.org",
    "val": "uri:deskat:value.at-spi.gnome.org",
    "act": "uri:deskat:action.at-spi.gnome.org",
}

# Chrome user-data-dir – MUST be non-default for --remote-debugging-port to
# work on Chrome 145+.  See supervisord.conf [program:chrome] for the matching
# --user-data-dir flag.
_CHROME_USER_DATA_DIR = "/root/chrome-profile"
_CHROME_PREFS = os.path.join(_CHROME_USER_DATA_DIR, "Default", "Preferences")
_CHROME_LOCAL_STATE = os.path.join(_CHROME_USER_DATA_DIR, "Local State")
_CHROME_BOOKMARKS = os.path.join(_CHROME_USER_DATA_DIR, "Default", "Bookmarks")
_CHROME_COOKIES = os.path.join(_CHROME_USER_DATA_DIR, "Default", "Cookies")
_CHROME_HISTORY = os.path.join(_CHROME_USER_DATA_DIR, "Default", "History")
_CHROME_EXTENSIONS = os.path.join(_CHROME_USER_DATA_DIR, "Default", "Extensions")

# CDP connection settings
# Use 127.0.0.1 not "localhost" – Chrome binds 0.0.0.0 (IPv4 only) and many
# containers resolve localhost → ::1 (IPv6) first, causing ECONNREFUSED.
_CDP_HOST = "127.0.0.1"
_CDP_PORT = 1337
_CDP_URL = f"http://{_CDP_HOST}:{_CDP_PORT}"


def _read_json_file(path: str) -> Optional[dict]:
    """Read and parse a JSON file, returning None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read JSON file {path}: {e}")
        return None


def _read_file_bytes(path: str) -> Optional[bytes]:
    """Read file as bytes, returning None on failure."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read file {path}: {e}")
        return None


def _connect_cdp(p):
    """Connect to Chrome CDP, restarting Chrome if needed. Returns browser or raises."""
    try:
        return p.chromium.connect_over_cdp(_CDP_URL)
    except Exception as e:
        logger.warning(f"Failed to connect to Chrome CDP: {e}, attempting restart...")
        subprocess.Popen(
            [
                "chrome",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                f"--user-data-dir={_CHROME_USER_DATA_DIR}",
                "--remote-debugging-port=1337",
                "--remote-debugging-address=0.0.0.0",
            ],
            env={**os.environ, "DISPLAY": ":99"},
        )
        time.sleep(5)
        return p.chromium.connect_over_cdp(_CDP_URL)


def _get_accessibility_tree_xml() -> Optional[str]:
    """Get accessibility tree XML from the AT-SPI server."""
    try:
        result = subprocess.run(
            [
                "python3",
                "-c",
                """
import pyatspi
import xml.etree.ElementTree as ET

def walk(obj, parent_el):
    try:
        role_name = obj.getRoleName()
    except Exception:
        return
    el = ET.SubElement(parent_el, role_name.replace(' ', '_'))
    try:
        name = obj.name
        if name:
            el.set('name', name)
    except Exception:
        pass
    try:
        text_iface = obj.queryText()
        if text_iface:
            t = text_iface.getText(0, -1)
            if t:
                el.text = t
    except Exception:
        pass
    try:
        for i in range(obj.childCount):
            child = obj.getChildAtIndex(i)
            if child:
                walk(child, el)
    except Exception:
        pass

desktop = pyatspi.Registry.getDesktop(0)
root = ET.Element('desktop')
for app_idx in range(desktop.childCount):
    app = desktop.getChildAtIndex(app_idx)
    if app:
        walk(app, root)
print(ET.tostring(root, encoding='unicode'))
""",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env={
                **os.environ,
                "DISPLAY": ":99",
                "DBUS_SESSION_BUS_ADDRESS": os.environ.get(
                    "DBUS_SESSION_BUS_ADDRESS", "unix:path=/dev/shm/dbus_session_socket"
                ),
            },
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            logger.error(f"AT-SPI tree extraction failed: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Failed to get accessibility tree: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# FILE-BASED GETTERS  (read Chrome config files directly)
# ──────────────────────────────────────────────────────────────


def get_default_search_engine(env: Any, config: Dict[str, Any]) -> str:
    """Get the default search engine from Chrome Preferences."""
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return "Google"
    return (
        data.get("default_search_provider_data", {})
        .get("template_url_data", {})
        .get("short_name", "Google")
    )


def get_cookie_data(env: Any, config: Dict[str, Any]) -> Optional[list]:
    """Get cookies from Chrome's SQLite database.

    Chrome locks the DB while running, so we copy it first.
    """
    if not os.path.exists(_CHROME_COOKIES):
        logger.error(f"Cookies file not found: {_CHROME_COOKIES}")
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        # Copy to avoid WAL lock issues
        subprocess.run(["cp", _CHROME_COOKIES, tmp_path], check=True)
        # Also copy WAL/SHM if they exist
        for ext in ["-wal", "-shm"]:
            src = _CHROME_COOKIES + ext
            if os.path.exists(src):
                subprocess.run(["cp", src, tmp_path + ext], check=False)
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cookies")
        cookies = cursor.fetchall()
        conn.close()
        os.unlink(tmp_path)
        for ext in ["-wal", "-shm"]:
            p = tmp_path + ext
            if os.path.exists(p):
                os.unlink(p)
        return cookies
    except Exception as e:
        logger.error(f"Error reading cookies: {e}")
        return None


def get_history(env: Any, config: Dict[str, Any]) -> Optional[list]:
    """Get browsing history from Chrome's SQLite database."""
    if not os.path.exists(_CHROME_HISTORY):
        logger.error(f"History file not found: {_CHROME_HISTORY}")
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        subprocess.run(["cp", _CHROME_HISTORY, tmp_path], check=True)
        for ext in ["-wal", "-shm"]:
            src = _CHROME_HISTORY + ext
            if os.path.exists(src):
                subprocess.run(["cp", src, tmp_path + ext], check=False)
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, last_visit_time FROM urls")
        history_items = cursor.fetchall()
        conn.close()
        os.unlink(tmp_path)
        for ext in ["-wal", "-shm"]:
            p = tmp_path + ext
            if os.path.exists(p):
                os.unlink(p)
        return history_items
    except Exception as e:
        logger.error(f"Error reading history: {e}")
        return None


def get_enabled_experiments(env: Any, config: Dict[str, Any]) -> list:
    """Get enabled Chrome flags/experiments from Local State."""
    data = _read_json_file(_CHROME_LOCAL_STATE)
    if data is None:
        return []
    return data.get("browser", {}).get("enabled_labs_experiments", [])


def get_profile_name(env: Any, config: Dict[str, Any]) -> Optional[str]:
    """Get the Chrome profile name."""
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return None
    return data.get("profile", {}).get("name", None)


def get_chrome_language(env: Any, config: Dict[str, Any]) -> str:
    """Get Chrome's UI language from Local State."""
    data = _read_json_file(_CHROME_LOCAL_STATE)
    if data is None:
        return "en-US"
    return data.get("intl", {}).get("app_locale", "en-US")


def get_chrome_font_size(env: Any, config: Dict[str, Any]) -> dict:
    """Get Chrome font size settings from Preferences."""
    default = {"default_fixed_font_size": 13, "default_font_size": 16, "minimum_font_size": 13}
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return default
    return data.get("webkit", {}).get("webprefs", default)


def get_bookmarks(env: Any, config: Dict[str, Any]) -> Any:
    """Get Chrome bookmarks."""
    data = _read_json_file(_CHROME_BOOKMARKS)
    if data is None:
        return []
    return data.get("roots", {})


def get_extensions_installed_from_shop(env: Any, config: Dict[str, Any]) -> list:
    """Get installed Chrome extensions by reading their manifest files."""
    if not os.path.exists(_CHROME_EXTENSIONS):
        return []
    manifests = []
    try:
        for extension_id in os.listdir(_CHROME_EXTENSIONS):
            ext_path = os.path.join(_CHROME_EXTENSIONS, extension_id)
            if not os.path.isdir(ext_path):
                continue
            for version_dir in os.listdir(ext_path):
                manifest_path = os.path.join(ext_path, version_dir, "manifest.json")
                if os.path.isfile(manifest_path):
                    try:
                        with open(manifest_path, "r") as f:
                            manifests.append(json.load(f))
                    except json.JSONDecodeError:
                        logger.error(f"Error reading {manifest_path}")
    except Exception as e:
        logger.error(f"Error listing extensions: {e}")
    return manifests


def get_enable_do_not_track(env: Any, config: Dict[str, Any]) -> str:
    """Check if Do Not Track is enabled."""
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return "false"
    return "true" if data.get("enable_do_not_track", False) else "false"


def get_enable_enhanced_safety_browsing(env: Any, config: Dict[str, Any]) -> str:
    """Check if Enhanced Safe Browsing is enabled."""
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return "false"
    return "true" if data.get("safebrowsing", {}).get("enhanced", False) else "false"


def get_new_startup_page(env: Any, config: Dict[str, Any]) -> str:
    """Check if Chrome is configured to open a new startup page."""
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return "false"
    if "session" not in data:
        return "true"
    return "true" if data.get("session", {}).get("restore_on_startup", 0) == 5 else "false"


def get_find_unpacked_extension_path(env: Any, config: Dict[str, Any]) -> list:
    """Get paths of all installed extensions from Preferences."""
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return []
    all_extensions = data.get("extensions", {}).get("settings", {})
    return [ext.get("path", "") for ext in all_extensions.values() if "path" in ext]


def get_find_installed_extension_name(env: Any, config: Dict[str, Any]) -> list:
    """Get names of all installed extensions from Preferences."""
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return []
    all_extensions = data.get("extensions", {}).get("settings", {})
    names = []
    for ext in all_extensions.values():
        try:
            names.append(ext["manifest"]["name"])
        except (KeyError, TypeError):
            pass
    return names


def get_data_delete_automacally(env: Any, config: Dict[str, Any]) -> str:
    """Check if auto-delete data is configured."""
    data = _read_json_file(_CHROME_PREFS)
    if data is None:
        return "false"
    state = data.get("profile", {}).get("default_content_setting_values", None)
    return "true" if state is not None else "false"


# ──────────────────────────────────────────────────────────────
# CDP-BASED GETTERS  (use Playwright to connect to Chrome)
# ──────────────────────────────────────────────────────────────


def get_info_from_website(env: Any, config: Dict[str, Any]) -> Any:
    """Get information from a website using Playwright CDP connection.

    Navigates to a URL and extracts data via CSS selectors.
    Supports actions: inner_text, attribute, click_and_inner_text, click_and_attribute.
    """
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = _connect_cdp(p)
            page = browser.contexts[0].new_page()
            page.goto(config["url"])
            page.wait_for_load_state("load")

            infos = []
            for info_dict in config.get("infos", []):
                if page.url != config["url"]:
                    page.goto(config["url"])
                    page.wait_for_load_state("load")

                action = info_dict.get("action", "inner_text")
                if action == "inner_text":
                    ele = page.wait_for_selector(
                        info_dict["selector"], state="attached", timeout=10000
                    )
                    infos.append(ele.inner_text())
                elif action == "attribute":
                    ele = page.wait_for_selector(
                        info_dict["selector"], state="attached", timeout=10000
                    )
                    infos.append(ele.get_attribute(info_dict["attribute"]))
                elif action == "click_and_inner_text":
                    for idx, sel in enumerate(info_dict["selector"]):
                        if idx != len(info_dict["selector"]) - 1:
                            link = page.wait_for_selector(sel, state="attached", timeout=10000)
                            link.click()
                            page.wait_for_load_state("load")
                        else:
                            ele = page.wait_for_selector(sel, state="attached", timeout=10000)
                            infos.append(ele.inner_text())
                elif action == "click_and_attribute":
                    for idx, sel in enumerate(info_dict["selector"]):
                        if idx != len(info_dict["selector"]) - 1:
                            link = page.wait_for_selector(sel, state="attached", timeout=10000)
                            link.click()
                            page.wait_for_load_state("load")
                        else:
                            ele = page.wait_for_selector(sel, state="attached", timeout=10000)
                            infos.append(ele.get_attribute(info_dict["attribute"]))
                else:
                    raise NotImplementedError(f"Unsupported action: {action}")

            return infos
    except Exception as e:
        logger.error(f"Failed to get info from website {config.get('url')}: {e}")
        return config.get("backups", None)


def get_page_info(env: Any, config: Dict[str, Any]) -> dict:
    """Navigate to a URL and get page info (title, url, content)."""
    from playwright.sync_api import sync_playwright

    url = config["url"]
    max_retries = 2
    timeout_ms = 60000

    for attempt in range(max_retries):
        try:
            with sync_playwright() as p:
                browser = _connect_cdp(p)
                page = browser.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                    page_info = {"title": page.title(), "url": page.url, "content": page.content()}
                except Exception:
                    page_info = {
                        "title": "Load timeout",
                        "url": page.url,
                        "content": page.content(),
                    }
                browser.close()
                return page_info
        except Exception as e:
            logger.error(f"get_page_info attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)

    return {"title": "Connection failed", "url": url, "content": ""}


def get_open_tabs_info(env: Any, config: Dict[str, Any]) -> List[dict]:
    """Get info about all open Chrome tabs via CDP."""
    from playwright.sync_api import sync_playwright

    max_retries = 2
    timeout_ms = 30000

    for attempt in range(max_retries):
        try:
            with sync_playwright() as p:
                browser = _connect_cdp(p)
                tabs_info = []
                for context in browser.contexts:
                    for page in context.pages:
                        try:
                            page.set_default_timeout(timeout_ms)
                            page.wait_for_load_state("networkidle", timeout=timeout_ms)
                            tabs_info.append({"title": page.title(), "url": page.url})
                        except Exception:
                            tabs_info.append({"title": "Error", "url": page.url})
                browser.close()
                return tabs_info
        except Exception as e:
            logger.error(f"get_open_tabs_info attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)

    return []


def get_active_url_from_accessTree(env: Any, config: Dict[str, Any]) -> Optional[str]:
    """Get the active tab URL from the accessibility tree (Chrome address bar)."""
    tree_xml = _get_accessibility_tree_xml()
    if tree_xml is None:
        return None

    try:
        at = lxml.etree.fromstring(
            tree_xml.encode("utf-8") if isinstance(tree_xml, str) else tree_xml
        )
    except Exception as e:
        logger.error(f"Error parsing accessibility tree: {e}")
        return None

    selector_string = "application[name=Google\\ Chrome] entry[name=Address\\ and\\ search\\ bar]"
    try:
        selector = CSSSelector(selector_string, namespaces=_accessibility_ns_map)
    except Exception as e:
        logger.error(f"Failed to parse CSS selector: {e}")
        return None

    elements = selector(at) if selector else []
    if not elements or not elements[-1].text:
        logger.warning("No address bar text found in accessibility tree")
        return None

    goto_prefix = config.get("goto_prefix", "https://")
    return f"{goto_prefix}{elements[0].text}"


def get_active_tab_info(env: Any, config: Dict[str, Any]) -> Optional[dict]:
    """Get full info about the active tab (navigates to the URL found in address bar)."""
    from playwright.sync_api import sync_playwright

    active_tab_url = get_active_url_from_accessTree(env, config)
    if active_tab_url is None:
        logger.error("Failed to get active tab URL")
        return None

    max_retries = 2
    timeout_ms = 60000

    for attempt in range(max_retries):
        try:
            with sync_playwright() as p:
                browser = _connect_cdp(p)
                page = browser.new_page()
                page.set_default_timeout(timeout_ms)
                try:
                    page.goto(active_tab_url, wait_until="networkidle", timeout=timeout_ms)
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                    info = {"title": page.title(), "url": page.url, "content": page.content()}
                except Exception:
                    info = {"title": "Load timeout", "url": page.url, "content": page.content()}
                browser.close()
                return info
        except Exception as e:
            logger.error(f"get_active_tab_info attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)

    return None


def get_pdf_from_url(env: Any, config: Dict[str, Any]) -> str:
    """Download a PDF from a URL using Chrome's PDF generation."""
    from playwright.sync_api import sync_playwright

    url = config["path"]
    dest = config.get("dest", "/tmp/downloaded.pdf")
    max_retries = 3
    timeout_ms = 60000

    for attempt in range(max_retries):
        try:
            with sync_playwright() as p:
                browser = _connect_cdp(p)
                page = browser.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
                time.sleep(3)
                page.pdf(path=dest)
                browser.close()
                return dest
        except Exception as e:
            logger.error(f"get_pdf_from_url attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    # Create placeholder on total failure
    try:
        with open(dest, "w") as f:
            f.write("%PDF-1.4\n%EOF\n")
    except Exception:
        pass
    return dest


def get_chrome_saved_address(env: Any, config: Dict[str, Any]) -> str:
    """Get Chrome's saved addresses page content."""
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = _connect_cdp(p)
            page = browser.new_page()
            page.set_default_timeout(30000)
            page.goto("chrome://settings/addresses", wait_until="networkidle", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        logger.error(f"get_chrome_saved_address failed: {e}")
        return ""


def get_shortcuts_on_desktop(env: Any, config: Dict[str, Any]) -> Dict[str, str]:
    """Get .desktop shortcut files from the Desktop."""
    desktop_path = os.path.expanduser("~/Desktop")
    shortcuts = {}
    if not os.path.exists(desktop_path):
        return shortcuts
    for fname in os.listdir(desktop_path):
        if fname.endswith(".desktop"):
            fpath = os.path.join(desktop_path, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    shortcuts[fname] = f.read()
            except Exception as e:
                logger.error(f"Error reading shortcut {fpath}: {e}")
    return shortcuts


def get_number_of_search_results(env: Any, config: Dict[str, Any]) -> int:
    """Get the number of search results on a Google search page."""
    from playwright.sync_api import sync_playwright

    url = config.get("url", "https://google.com/search?q=query")
    result_selector = config.get("result_selector", ".search-result")

    try:
        with sync_playwright() as p:
            browser = _connect_cdp(p)
            page = browser.new_page()
            page.set_default_timeout(45000)
            page.goto(url, wait_until="networkidle", timeout=45000)
            page.wait_for_load_state("networkidle", timeout=45000)
            results = page.query_selector_all(result_selector)
            count = len(results)
            browser.close()
            return count
    except Exception as e:
        logger.error(f"get_number_of_search_results failed: {e}")
        return 0


def get_active_tab_html_parse(env: Any, config: Dict[str, Any]) -> dict:
    """Parse HTML elements from the active tab based on config selectors.

    Supports categories: class, label, xpath, input, class&url.
    """
    from playwright.sync_api import sync_playwright

    active_tab_url = get_active_url_from_accessTree(env, config)
    if not isinstance(active_tab_url, str):
        logger.error(f"active_tab_url is not a string: {type(active_tab_url)}")
        return {}

    try:
        with sync_playwright() as p:
            browser = _connect_cdp(p)
            # Find the matching tab
            target_page = None
            for context in browser.contexts:
                for page in context.pages:
                    try:
                        page.wait_for_load_state("networkidle", timeout=60000)
                        if page.is_closed():
                            continue
                        if unquote(page.url).rstrip("/") == unquote(active_tab_url).rstrip("/"):
                            target_page = page
                            break
                    except Exception:
                        continue
                if target_page:
                    break

            if target_page is None:
                logger.error(f"Could not find tab matching URL: {active_tab_url}")
                browser.close()
                return {}

            return_json = _extract_from_page(target_page, config)
            browser.close()
            return return_json
    except Exception as e:
        logger.error(f"get_active_tab_html_parse failed: {e}")
        return {}


def _extract_from_page(page, config: Dict[str, Any]) -> dict:
    """Extract data from a Playwright page based on config category."""
    return_json = {}

    def safe_text(selector: str) -> List[str]:
        try:
            if page.is_closed():
                return []
            elements = page.query_selector_all(selector)
            return [el.text_content().strip() for el in elements if el]
        except Exception:
            return []

    def safe_direct_text(selector: str) -> list:
        try:
            if page.is_closed():
                return []
            elements = page.query_selector_all(selector)
            results = []
            for el in elements:
                texts = el.evaluate(
                    """(node) => Array.from(node.childNodes)
                        .filter(n => n.nodeType === Node.TEXT_NODE)
                        .map(n => n.textContent.trim())
                        .filter(Boolean)"""
                )
                results.append(texts)
            return results[0] if results else []
        except Exception:
            return []

    category = config.get("category", "class")

    if category == "class":
        # Multi-object class extraction
        for class_name, obj_dict in config.get("class_multiObject", {}).items():
            texts = safe_text("." + class_name)
            for order_key, key in obj_dict.items():
                idx = int(order_key)
                return_json[key] = texts[idx] if idx < len(texts) else ""

        for class_name, obj_dict in config.get("class_multiObject_child", {}).items():
            texts = safe_direct_text("." + class_name)
            for order_key, key in obj_dict.items():
                idx = int(order_key)
                return_json[key] = texts[idx] if idx < len(texts) else ""

        for class_name, obj_dict in config.get("class_multiObject_only_child", {}).items():
            try:
                elements = page.query_selector_all("." + class_name)
                texts = [
                    el.query_selector("h3").text_content().strip()
                    for el in elements
                    if el.query_selector("h3")
                ]
            except Exception:
                texts = []
            for order_key, key in obj_dict.items():
                idx = int(order_key)
                return_json[key] = texts[idx] if idx < len(texts) else ""

        for class_name, obj_list in config.get("class_multiObject_search_exist", {}).items():
            texts = safe_text("." + class_name)
            for item in obj_list:
                if item == "is_other_exist":
                    continue
                return_json[item] = item in texts
            if "is_other_exist" in obj_list:
                return_json["is_other_exist"] = any(t not in obj_list for t in texts)

        for class_name, key in config.get("class_singleObject", {}).items():
            texts = safe_text("." + class_name)
            return_json[key] = texts[0] if texts else ""

    elif category == "label":
        for label_sel, key in config.get("labelObject", {}).items():
            try:
                text = page.locator(f"text={label_sel}").first.text_content()
                return_json[key] = text.strip() if text else ""
            except Exception:
                return_json[key] = ""

    elif category == "xpath":
        for xpath, key in config.get("xpathObject", {}).items():
            try:
                elements = page.locator(f"xpath={xpath}")
                if elements.count() > 0:
                    text = elements.first.text_content()
                    return_json[key] = text.strip() if text else ""
                else:
                    return_json[key] = ""
            except Exception:
                return_json[key] = ""

    elif category == "input":
        for xpath, key in config.get("inputObject", {}).items():
            try:
                inputs = page.locator(f"xpath={xpath}")
                if inputs.count() > 0:
                    val = inputs.first.input_value()
                    return_json[key] = val.strip() if val else ""
                else:
                    return_json[key] = ""
            except Exception:
                return_json[key] = ""

    elif category == "class&url":
        for class_name, obj_list in config.get("class_multiObject", {}).items():
            texts = safe_text("." + class_name)
            for item in obj_list:
                if any(item.lower() == t.lower() for t in texts):
                    return_json[item.lower()] = True
            for t in texts:
                if all(t.lower() not in item.lower() for item in obj_list):
                    return_json["is_other_exist"] = True
                    break
            if "is_other_exist" not in return_json:
                return_json["is_other_exist"] = False

        for class_name, obj_list in config.get("class_multiObject_li", {}).items():
            try:
                elements = page.query_selector_all("." + class_name + " li.catAllProducts")
                texts = [
                    el.query_selector("span").inner_text().strip()
                    for el in elements
                    if el.query_selector("span")
                ]
            except Exception:
                texts = []
            for item in obj_list:
                if any(item.lower() == t.lower() for t in texts):
                    return_json[item.lower()] = True
            for t in texts:
                if all(t.lower() not in item.lower() for item in obj_list):
                    return_json["is_other_exist"] = True
                    break
            if "is_other_exist" not in return_json:
                return_json["is_other_exist"] = False

        for key in config.get("url_include_expected", []):
            try:
                page_url = page.url.lower()
                if key.lower() not in return_json:
                    return_json[key.lower()] = key.lower() in page_url
            except Exception:
                if key.lower() not in return_json:
                    return_json[key.lower()] = False

        for key, value in config.get("url_include_expected_multichoice", {}).items():
            try:
                page_url = page.url.lower()
                if value.lower() not in return_json:
                    return_json[value.lower()] = key.lower() in page_url
            except Exception:
                if value.lower() not in return_json:
                    return_json[value.lower()] = False

    return return_json


def get_active_tab_url_parse(env: Any, config: Dict[str, Any]) -> Optional[dict]:
    """Parse query parameters from the active tab URL."""
    active_tab_url = get_active_url_from_accessTree(env, config)
    if active_tab_url is None:
        return None

    parsed_url = urlparse(active_tab_url)
    query_params = parse_qs(parsed_url.query)
    keys_of_interest = config.get("parse_keys", [])
    extracted = {key: query_params.get(key, [""])[0] for key in keys_of_interest}

    if "replace" in config:
        for old_key, new_key in config["replace"].items():
            if old_key in extracted:
                extracted[new_key] = extracted.pop(old_key)

    if config.get("split_list", False):
        extracted = {k: v.split(",") for k, v in extracted.items()}

    return extracted


def get_url_dashPart(env: Any, config: Dict[str, Any]) -> Optional[Any]:
    """Extract a dash-separated part of the active tab URL."""
    active_tab_url = get_active_url_from_accessTree(env, config)
    if active_tab_url is None:
        return None

    try:
        part_index = int(config["partIndex"])
    except (ValueError, TypeError):
        logger.error(f"Invalid partIndex: {config.get('partIndex')}")
        return None

    url_parts = active_tab_url.split("/")
    if part_index >= len(url_parts):
        logger.error(f"partIndex {part_index} out of range for URL with {len(url_parts)} parts")
        return None

    dash_part = url_parts[part_index]
    if config.get("needDeleteId", False):
        dash_part = dash_part.split("?")[0]

    if config.get("returnType") == "string":
        return dash_part
    elif config.get("returnType") == "json":
        return {config["key"]: dash_part}
    return dash_part


def get_gotoRecreationPage_and_get_html_content(env: Any, config: Dict[str, Any]) -> dict:
    """Navigate recreation.gov, perform search and extract content.

    This is a highly specific getter for recreation.gov evaluation tasks.
    """
    from playwright.sync_api import sync_playwright

    max_retries = 3
    timeout_ms = 60000

    for attempt in range(max_retries):
        try:
            with sync_playwright() as p:
                browser = _connect_cdp(p)
                page = browser.new_page()
                page.set_default_timeout(timeout_ms)

                # Navigate to recreation.gov
                page.goto(
                    "https://www.recreation.gov/", wait_until="domcontentloaded", timeout=timeout_ms
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass

                # Fill search and click
                page.wait_for_selector(
                    "input#hero-search-input", state="visible", timeout=timeout_ms
                )
                page.fill("input#hero-search-input", "Diamond")
                page.wait_for_selector(
                    "button.nav-search-button", state="visible", timeout=timeout_ms
                )
                page.click("button.nav-search-button")
                time.sleep(10)

                # Click search result
                page.wait_for_selector(
                    ".search-result-highlight--success", state="visible", timeout=timeout_ms
                )
                with page.expect_popup() as popup_info:
                    page.click(".search-result-highlight--success")
                time.sleep(30)

                newpage = popup_info.value
                newpage.set_default_timeout(timeout_ms)
                newpage.wait_for_load_state("networkidle", timeout=timeout_ms)
                time.sleep(2)

                # Try to click next-available button
                for sel in [
                    "button.next-available",
                    "button[class*='next-available']",
                    ".next-available",
                ]:
                    try:
                        newpage.wait_for_selector(sel, state="visible", timeout=30000)
                        newpage.click(sel, timeout=30000)
                        break
                    except Exception:
                        continue

                # Extract content
                return_json = {"expected": {}}
                if config.get("selector") == "class":
                    class_name = config["class"]
                    order = config.get("order")
                    try:
                        if order is not None:
                            elements = newpage.query_selector_all("." + class_name)
                            idx = int(order)
                            if idx < len(elements):
                                text = elements[idx].text_content()
                                return_json["expected"][class_name] = text.strip() if text else ""
                            else:
                                return_json["expected"][class_name] = "__EVALUATION_FAILED__"
                        else:
                            el = newpage.query_selector("." + class_name)
                            if el:
                                text = el.text_content()
                                return_json["expected"][class_name] = text.strip() if text else ""
                            else:
                                return_json["expected"][class_name] = "__EVALUATION_FAILED__"
                    except Exception:
                        return_json["expected"][class_name] = "__EVALUATION_FAILED__"

                browser.close()
                return return_json
        except Exception as e:
            logger.error(f"get_gotoRecreationPage attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    return {"expected": {"error": "__EVALUATION_FAILED__"}}


def get_macys_product_url_parse(env: Any, config: Dict[str, Any]) -> Optional[dict]:
    """Parse Macy's product URL path for evaluation."""
    active_tab_url = get_active_url_from_accessTree(env, config)
    if active_tab_url is None:
        return None

    parsed = urlparse(active_tab_url)
    path = unquote(parsed.path)
    result: Dict[str, Any] = {}

    result["mens_clothing"] = True if "mens-clothing" in path else None

    path_parts = path.strip("/").split("/")
    key_value_json: Dict[str, Any] = {}
    shirts_flag = "shirts" in path
    short_sleeve_flag = "short-sleeve" in path

    for i in range(len(path_parts) - 1):
        if "," in path_parts[i] and "," in path_parts[i + 1]:
            keys = [k.strip() for k in path_parts[i].split(",")]
            values = [v.strip() for v in path_parts[i + 1].split(",")]
            for k, v in zip(keys, values):
                if k == "Price_discount_range":
                    key_value_json[k] = [item.strip() for item in v.split("|")] if v else None
                else:
                    key_value_json[k] = v if v else None
                if k == "Product_department" and v and v.lower() in ("shirts", "shirt"):
                    shirts_flag = True
                if k == "Sleeve_length" and v and v.lower() in ("short-sleeve", "short sleeve"):
                    short_sleeve_flag = True
            break

    for field in ["Men_regular_size_t", "Price_discount_range"]:
        if field not in key_value_json:
            key_value_json[field] = None

    result["shirts"] = shirts_flag or None
    result["short_sleeve"] = short_sleeve_flag or None

    for key in config.get("parse_keys", []):
        if key in key_value_json:
            if key == "Price_discount_range":
                val = key_value_json[key]
                if (
                    val is not None
                    and "50_PERCENT_ off & more" in val
                    and "30_PERCENT_ off & more" not in val
                    and "20_PERCENT_ off & more" not in val
                ):
                    result[key] = "50_PERCENT_ off & more"
                else:
                    result[key] = "not_50_PERCENT_ off & more"
            else:
                result[key] = key_value_json[key]

    return result


# Backward compatibility alias
get_url_path_parse = get_macys_product_url_parse
