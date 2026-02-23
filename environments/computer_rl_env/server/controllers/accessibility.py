"""Accessibility tree parser with full AT-SPI attribute extraction.

Produces rich XML trees matching ComputerRL's ``_create_atspi_node`` output
(states, component bounds, text, values, actions, image/selection flags,
AT-SPI attributes) with configurable depth/width limits and optional
LibreOffice Calc optimisation.

Two output modes:
  * ``parse()``     → human-readable rich text (for agent prompts / observations)
  * ``parse_xml()`` → lxml XML string (for evaluator getters that need XPath)
"""

from __future__ import annotations

import concurrent.futures
import logging
import shutil
import subprocess
import threading
import time as _time
from typing import Optional

import lxml.etree

from .utils import import_pyatspi, is_pyatspi_available

logger = logging.getLogger(__name__)

NS_MAP = {
    "st": "https://accessibility.ubuntu.example.org/ns/state",
    "attr": "https://accessibility.ubuntu.example.org/ns/attributes",
    "cp": "https://accessibility.ubuntu.example.org/ns/component",
    "doc": "https://accessibility.ubuntu.example.org/ns/document",
    "docattr": "https://accessibility.ubuntu.example.org/ns/document/attributes",
    "txt": "https://accessibility.ubuntu.example.org/ns/text",
    "val": "https://accessibility.ubuntu.example.org/ns/value",
    "act": "https://accessibility.ubuntu.example.org/ns/action",
}

# Short prefixes used when generating the rich-text representation
_ST_URI = NS_MAP["st"]
_ATTR_URI = NS_MAP["attr"]
_CP_URI = NS_MAP["cp"]
_VAL_URI = NS_MAP["val"]
_ACT_URI = NS_MAP["act"]


def _get_libreoffice_version() -> tuple[int, ...] | None:
    """Return the LibreOffice version as a tuple of ints, or *None*."""
    try:
        result = subprocess.run(
            "libreoffice --version",
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        version_str = result.stdout.split()[1]
        return tuple(map(int, version_str.split(".")))
    except Exception:
        return None


# Cache the version so we only call once per process
_lo_version: tuple[int, ...] | None = None
_lo_version_fetched = False


def _cached_lo_version() -> tuple[int, ...] | None:
    global _lo_version, _lo_version_fetched
    if not _lo_version_fetched:
        _lo_version = _get_libreoffice_version()
        _lo_version_fetched = True
    return _lo_version


def _create_atspi_node(
    node,
    depth: int = 0,
    flag: str | None = None,
    *,
    max_depth: int = 50,
    max_width: int = 1024,
) -> lxml.etree._Element:
    """Recursively build an lxml element tree from an AT-SPI accessible node.

    This is a faithful port of ComputerRL's ``_create_atspi_node`` with all
    attribute categories: states, AT-SPI attributes, component bounds, text,
    image, selection, value, and action.
    """
    pyatspi = import_pyatspi()
    from pyatspi import STATE_SHOWING, StateType

    node_name = node.name or ""
    attribute_dict: dict[str, str] = {"name": node_name}

    # States
    try:
        states = node.getState().get_states()
        for st in states:
            state_name: str = StateType._enum_lookup[st]
            state_name = state_name.split("_", maxsplit=1)[1].lower()
            if state_name:
                attribute_dict[f"{{{_ST_URI}}}{state_name}"] = "true"
    except Exception:
        pass

    # AT-SPI attributes
    try:
        attributes = node.get_attributes()
        for k, v in attributes.items():
            if k:
                attribute_dict[f"{{{_ATTR_URI}}}{k}"] = v
    except Exception:
        pass

    # Component (screen coordinates + size, only when visible+showing)
    try:
        is_visible = attribute_dict.get(f"{{{_ST_URI}}}visible", "false") == "true"
        is_showing = attribute_dict.get(f"{{{_ST_URI}}}showing", "false") == "true"
        if is_visible and is_showing:
            try:
                component = node.queryComponent()
                bbox = component.getExtents(pyatspi.XY_SCREEN)
                attribute_dict[f"{{{_CP_URI}}}screencoord"] = str(tuple(bbox[0:2]))
                attribute_dict[f"{{{_CP_URI}}}size"] = str(tuple(bbox[2:]))
            except NotImplementedError:
                pass
    except Exception:
        pass

    # Text
    text = ""
    try:
        text_obj = node.queryText()
        text = text_obj.getText(0, text_obj.characterCount)
        text = text.replace("\ufffc", "").replace("\ufffd", "")
    except NotImplementedError:
        pass

    # Image
    try:
        node.queryImage()
        attribute_dict["image"] = "true"
    except NotImplementedError:
        pass

    # Selection
    try:
        node.querySelection()
        attribute_dict["selection"] = "true"
    except NotImplementedError:
        pass

    # Value
    try:
        value_iface = node.queryValue()
        vk = f"{{{_VAL_URI}}}"
        for attr_name, attr_func in [
            ("value", lambda: value_iface.currentValue),
            ("min", lambda: value_iface.minimumValue),
            ("max", lambda: value_iface.maximumValue),
            ("step", lambda: value_iface.minimumIncrement),
        ]:
            try:
                attribute_dict[f"{vk}{attr_name}"] = str(attr_func())
            except Exception:
                pass
    except NotImplementedError:
        pass

    # Action
    try:
        action_iface = node.queryAction()
        for i in range(action_iface.nActions):
            action_name: str = action_iface.getName(i).replace(" ", "-")
            attribute_dict[f"{{{_ACT_URI}}}{action_name}_desc"] = action_iface.getDescription(i)
            attribute_dict[f"{{{_ACT_URI}}}{action_name}_kb"] = action_iface.getKeyBinding(i)
    except NotImplementedError:
        pass

    raw_role_name: str = node.getRoleName().strip()
    node_role_name = (raw_role_name or "unknown").replace(" ", "-")

    if not flag:
        if raw_role_name == "document spreadsheet":
            flag = "calc"
        if raw_role_name == "application" and node.name == "Thunderbird":
            flag = "thunderbird"

    xml_node = lxml.etree.Element(node_role_name, attrib=attribute_dict, nsmap=NS_MAP)

    if text:
        xml_node.text = text

    if depth >= max_depth:
        return xml_node

    # LibreOffice Calc optimised traversal
    if flag == "calc" and node_role_name == "table":
        lo_ver = _cached_lo_version()
        max_column = 1024 if (lo_ver is not None and lo_ver < (7, 4)) else 16384
        max_row = 1_048_576

        index_base = 0
        first_showing = False
        column_base: int | None = None

        for r in range(max_row):
            for clm in range(column_base or 0, max_column):
                try:
                    child_node = node[index_base + clm]
                except (IndexError, Exception):
                    break
                try:
                    showing: bool = child_node.getState().contains(STATE_SHOWING)
                except Exception:
                    showing = False
                if showing:
                    child_xml = _create_atspi_node(
                        child_node,
                        depth + 1,
                        flag,
                        max_depth=max_depth,
                        max_width=max_width,
                    )
                    if not first_showing:
                        column_base = clm
                        first_showing = True
                    xml_node.append(child_xml)
                elif first_showing and column_base is not None or clm >= 500:
                    break
            if first_showing and clm == (column_base or 0) or not first_showing and r >= 500:
                break
            index_base += max_column

        return xml_node

    try:
        for i, ch in enumerate(node):
            if i >= max_width:
                break
            xml_node.append(
                _create_atspi_node(
                    ch,
                    depth + 1,
                    flag,
                    max_depth=max_depth,
                    max_width=max_width,
                )
            )
    except Exception:
        pass

    return xml_node


def _format_xml_node_text(node: lxml.etree._Element, depth: int = 0) -> list[str]:
    """Convert an lxml element (from ``_create_atspi_node``) to indented text lines.

    Format per line::

        role: name (x, y, w, h) [state1, state2] "text content" {value=…}

    This includes coordinate info so that ``RuleBasedAgent._find_element()``
    can extract ``(x, y)`` with its existing regex.
    """
    lines: list[str] = []
    indent = "  " * depth

    role = node.tag or "unknown"
    name = node.attrib.get("name", "")

    # Collect states
    states: list[str] = []
    for key in node.attrib:
        if key.startswith(f"{{{_ST_URI}}}"):
            state_name = key.split("}", 1)[1]
            if node.attrib[key] == "true":
                states.append(state_name)

    # Collect coordinates
    coord_str = ""
    screencoord = node.attrib.get(f"{{{_CP_URI}}}screencoord", "")
    size = node.attrib.get(f"{{{_CP_URI}}}size", "")
    if screencoord and size:
        coord_str = f" {screencoord} {size}"

    # Collect value
    value_parts: list[str] = []
    for vattr in ("value", "min", "max", "step"):
        val = node.attrib.get(f"{{{_VAL_URI}}}{vattr}", "")
        if val:
            value_parts.append(f"{vattr}={val}")
    value_str = " {" + ", ".join(value_parts) + "}" if value_parts else ""

    # Text content
    text_str = ""
    if node.text and node.text.strip():
        text_content = node.text.strip()
        if len(text_content) > 200:
            text_content = text_content[:197] + "..."
        text_str = f' "{text_content}"'

    # States string
    state_str = ""
    if states:
        state_str = " [" + ", ".join(sorted(states)) + "]"

    # Image / selection flags
    flags: list[str] = []
    if node.attrib.get("image") == "true":
        flags.append("image")
    if node.attrib.get("selection") == "true":
        flags.append("selection")
    flag_str = " (" + ", ".join(flags) + ")" if flags else ""

    line = f"{indent}{role}: {name}{coord_str}{state_str}{text_str}{value_str}{flag_str}"
    lines.append(line)

    for child in node:
        lines.extend(_format_xml_node_text(child, depth + 1))

    return lines


class AccessibilityParser:
    """Parse the desktop accessibility tree via AT-SPI (or x11 fallback).

    Parameters
    ----------
    backend : str
        ``"auto"`` (default), ``"pyatspi"``, ``"x11"``, or ``"empty"``.
    max_depth : int
        Maximum tree traversal depth (default 50, matching ComputerRL).
    max_width : int
        Maximum children per node (default 1024, matching ComputerRL).
    cache_ttl : float
        Seconds to cache the parsed tree (default 1.0).
    """

    def __init__(
        self,
        backend: str = "auto",
        max_depth: int = 50,
        max_width: int = 1024,
        cache_ttl: float = 1.0,
    ):
        self.backend = backend or self._detect_backend()
        self.max_depth = max_depth
        self.max_width = max_width
        self._cache: dict[str, tuple[object, float]] = {}
        self._cache_ttl: float = cache_ttl
        self._lock = threading.Lock()

    def parse(self) -> str:
        """Return a **rich text** representation of the accessibility tree.

        Includes role, name, states, screen coordinates, text content and
        values — suitable for agent observation prompts.
        """
        xml_root = self._get_cached_xml()
        if xml_root is None:
            xml_root = self._build_xml_tree()
            self._set_cache(xml_root)

        lines = _format_xml_node_text(xml_root)
        return "\n".join(lines) if lines else "[No windows detected]"

    def parse_xml(self) -> str:
        """Return the full XML string of the accessibility tree.

        Matches ComputerRL's ``/accessibility`` endpoint output — suitable
        for evaluator getters that need XPath queries.
        """
        xml_root = self._get_cached_xml()
        if xml_root is None:
            xml_root = self._build_xml_tree()
            self._set_cache(xml_root)

        return lxml.etree.tostring(xml_root, encoding="unicode")

    def get_active_window(self) -> dict | None:
        """Get active window class and title using xdotool / xprop."""
        if not self._check_x11_tools():
            return None
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode != 0:
                return None
            window_id = result.stdout.strip()

            result_name = subprocess.run(
                ["xdotool", "getwindowname", window_id],
                capture_output=True,
                text=True,
                timeout=1,
            )
            title = result_name.stdout.strip() if result_name.returncode == 0 else ""

            result_class = subprocess.run(
                ["xprop", "-id", window_id, "WM_CLASS"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            app_name = ""
            if result_class.returncode == 0:
                parts = result_class.stdout.split('"')
                if len(parts) >= 4:
                    app_name = parts[3]
                elif len(parts) >= 2:
                    app_name = parts[1]

            return {"active_window": title, "active_app": app_name}
        except Exception:
            return None

    def invalidate_cache(self) -> None:
        """Force-clear the cached tree."""
        with self._lock:
            self._cache.clear()

    def _get_cached_xml(self) -> Optional[lxml.etree._Element]:
        with self._lock:
            if "xml" in self._cache:
                cached_xml, cached_time = self._cache["xml"]
                if _time.time() - cached_time < self._cache_ttl:
                    return cached_xml  # type: ignore[return-value]
        return None

    def _set_cache(self, xml_root: lxml.etree._Element) -> None:
        with self._lock:
            self._cache["xml"] = (xml_root, _time.time())

    def _build_xml_tree(self) -> lxml.etree._Element:
        if self.backend == "pyatspi":
            return self._build_pyatspi_tree()
        elif self.backend == "x11":
            return self._build_x11_tree()
        # Empty fallback
        return lxml.etree.Element("desktop-frame", nsmap=NS_MAP)

    def _build_pyatspi_tree(self) -> lxml.etree._Element:
        if not is_pyatspi_available():
            return self._build_x11_tree()

        pyatspi = import_pyatspi()
        desktop = pyatspi.Registry.getDesktop(0)
        xml_root = lxml.etree.Element("desktop-frame", nsmap=NS_MAP)

        # Collect valid app nodes
        app_nodes = []
        for i in range(desktop.childCount):
            app = desktop.getChildAtIndex(i)
            if app:
                app_nodes.append(app)

        if not app_nodes:
            return xml_root

        # Parallel traversal of top-level app nodes (matches ComputerRL)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    _create_atspi_node,
                    app_node,
                    1,
                    None,
                    max_depth=self.max_depth,
                    max_width=self.max_width,
                ): app_node
                for app_node in app_nodes
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    xml_tree = future.result()
                    xml_root.append(xml_tree)
                except Exception as exc:
                    logger.warning("Error traversing app node: %s", exc)

        return xml_root

    def _build_x11_tree(self) -> lxml.etree._Element:
        """Fallback: window list only (no children) via wmctrl."""
        xml_root = lxml.etree.Element("desktop-frame", nsmap=NS_MAP)
        try:
            result = subprocess.run(
                ["wmctrl", "-l"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(maxsplit=4)
                    if len(parts) >= 5:
                        title = parts[4]
                        win_elem = lxml.etree.SubElement(
                            xml_root,
                            "frame",
                            attrib={"name": title, "window_id": parts[0]},
                            nsmap=NS_MAP,
                        )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return xml_root

    def _detect_backend(self) -> str:
        if is_pyatspi_available():
            return "pyatspi"
        if self._check_x11_tools():
            return "x11"
        return "empty"

    @staticmethod
    def _check_x11_tools() -> bool:
        return (
            shutil.which("xdotool") is not None
            and shutil.which("wmctrl") is not None
            and shutil.which("xprop") is not None
        )
