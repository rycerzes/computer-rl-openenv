import shutil
import subprocess

from .utils import import_pyatspi, is_pyatspi_available


class AccessibilityParser:
    def __init__(self, backend: str = "auto"):
        self.backend = backend or self._detect_backend()
        self._cache: dict[str, tuple[str, float]] = {}
        self._cache_ttl: float = 0.5

    def parse(self) -> str:
        cached = self._get_cached()
        if cached:
            return cached

        tree_data = self._parse_window_tree()
        text = self.format_tree(tree_data)
        self._cache["tree"] = (text, __import__("time").time())
        return text

    def _get_cached(self) -> str | None:
        import time

        if "tree" in self._cache:
            cached_text, cached_time = self._cache["tree"]
            if time.time() - cached_time < self._cache_ttl:
                return cached_text
        return None

    def _detect_backend(self) -> str:
        if is_pyatspi_available():
            return "pyatspi"

        if self._check_x11_tools():
            return "x11"

        return "empty"

    def _check_x11_tools(self) -> bool:
        return (
            shutil.which("xdotool") is not None
            and shutil.which("wmctrl") is not None
            and shutil.which("xprop") is not None
        )

    def _parse_window_tree(self) -> dict:
        if self.backend == "pyatspi":
            return self._parse_pyatspi()
        elif self.backend == "x11":
            return self._parse_x11()
        return {"windows": [], "error": "No backend available"}

    def _parse_pyatspi(self) -> dict:
        if not is_pyatspi_available():
            return self._parse_x11()

        pyatspi = import_pyatspi()

        registry = pyatspi.Registry
        desktop = registry.getDesktop(0)
        windows = []

        for i in range(desktop.childCount):
            app = desktop.getChildAtIndex(i)
            if not app or app.childCount == 0:
                continue

            for j in range(app.childCount):
                window = app.getChildAtIndex(j)
                if not window:
                    continue

                window_info = self._extract_window_info(window)
                if window_info:
                    windows.append(window_info)

        return {"windows": windows}

    def _extract_window_info(self, window) -> dict | None:
        try:
            return {
                "name": window.name or "",
                "role": window.getRoleName() or "window",
                "description": window.description or "",
                "accessible_id": f"acc-{id(window)}",
                "children": self._get_children(window),
            }
        except Exception:
            return None

    def _get_children(self, window, max_depth: int = 3, current_depth: int = 0) -> list:
        if current_depth >= max_depth:
            return []

        children = []
        for i in range(min(window.childCount, 20)):
            try:
                child = window.getChildAtIndex(i)
                if child:
                    child_info = {
                        "name": child.name or "",
                        "role": child.getRoleName() or "component",
                        "description": child.description or "",
                    }
                    if current_depth < max_depth - 1:
                        child_info["children"] = self._get_children(
                            child, max_depth, current_depth + 1
                        )
                    children.append(child_info)
            except Exception:
                continue
        return children

    def _parse_x11(self) -> dict:
        windows = []
        try:
            result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(maxsplit=4)
                    if len(parts) >= 5:
                        window_id = parts[0]
                        desktop_num = parts[1]
                        hostname = parts[2]
                        title = parts[4]

                        windows.append(
                            {
                                "window_id": window_id,
                                "name": title,
                                "role": "window",
                                "desktop": desktop_num,
                                "hostname": hostname,
                                "children": [],
                            }
                        )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return {"windows": windows}

    def format_tree(self, tree_data: dict) -> str:
        lines = []
        for window in tree_data.get("windows", []):
            lines.extend(self._format_node(window, depth=0))

        return "\n".join(lines) if lines else "[No windows detected]"

    def _format_node(self, node: dict, depth: int = 0) -> list:
        lines = []
        indent = "  " * depth
        name = node.get("name") or "(unnamed)"
        role = node.get("role") or "unknown"

        identifier = []
        if node.get("window_id"):
            identifier.append(f"id={node['window_id']}")
        else:
            identifier.append(f"acc={node.get('accessible_id', 'unknown')}")

        lines.append(f"{indent}{role}: {name} [{', '.join(identifier)}]")

        for child in node.get("children", []):
            lines.extend(self._format_node(child, depth + 1))

        return lines

    def get_active_window(self) -> dict | None:
        """Get active window class and title using xdotool/xprop."""
        if not self._check_x11_tools():
            return None

        try:
            # Get active window ID
            result = subprocess.run(
                ["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=1
            )
            if result.returncode != 0:
                return None
            window_id = result.stdout.strip()

            # Get title
            result_name = subprocess.run(
                ["xdotool", "getwindowname", window_id],
                capture_output=True,
                text=True,
                timeout=1,
            )
            title = result_name.stdout.strip() if result_name.returncode == 0 else ""

            # Get class (app name) using xprop
            # xprop -id 12345 WM_CLASS returns 'WM_CLASS(STRING) = "leafpad", "Leafpad"'
            result_class = subprocess.run(
                ["xprop", "-id", window_id, "WM_CLASS"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            app_name = ""
            if result_class.returncode == 0:
                # Parse: WM_CLASS(STRING) = "app_id", "App Name"
                parts = result_class.stdout.split('"')
                if len(parts) >= 4:
                    app_name = parts[3]  # The printable class name
                elif len(parts) >= 2:
                    app_name = parts[1]

            return {"active_window": title, "active_app": app_name}
        except Exception:
            return None
