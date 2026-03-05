import json
import logging
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from ...tasks.base import Task

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self):
        self.active_task = None
        self.observers = []
        self.cache_dir = Path("/tmp/computer_rl_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def setup(self, task: Task, env=None) -> bool:
        if task.proxy:
            proxy_params = {}
            if isinstance(task.metadata, dict):
                proxy_url = task.metadata.get("proxy_url")
                if proxy_url:
                    proxy_params["proxy_url"] = proxy_url
            self._proxy_setup(proxy_params, env=env)

        steps = task.config
        for step in steps:
            self._execute_config_step(step, env=env)

        self.active_task = task
        return True

    def evaluate(
        self,
        task: Task,
        elapsed_steps: int,
        env=None,
        last_action: Optional[str] = None,
    ) -> tuple[bool, float]:
        """Evaluate task completion using OSWorld-style evaluation.

        OSWorld evaluation flow:
        1. Run postconfig steps (save files, restart apps)
        2. Fetch result via getter
        3. Compare with expected using metric

        Args:
            task: Task with evaluator configuration
            elapsed_steps: Number of steps taken
            env: Environment instance (for getters)

        Returns:
            (success, reward) tuple
        """
        from .getters import get_result
        from .metrics import METRIC_REGISTRY, evaluate_metric

        ev = task.evaluator

        # Handle infeasible tasks
        func_name = ev.func
        if func_name == "infeasible":
            if last_action == "fail":
                return True, 1.0
            return False, 0.0

        # If agent gives up on a feasible task
        if last_action == "fail":
            return False, 0.0

        # 1. Run postconfig if present
        for step in ev.postconfig:
            self._execute_config_step(step, env)

        # Helper to get result/expected/options for a single metric index
        def get_config_item(key: str, idx: int, is_list_mode: bool) -> Any:
            item = getattr(ev, key, None)
            if is_list_mode and isinstance(item, list):
                if idx < len(item):
                    return item[idx]
                return None
            return item

        # Determine if we are in multi-metric mode
        is_multi_metric = isinstance(func_name, list)
        metric_names = func_name if is_multi_metric else [func_name]

        # Conjunction mode: "and" (default) or "or"
        conj = ev.conj

        metric_scores = []

        for i, metric in enumerate(metric_names):
            # 2. Fetch result via getter
            result_config = get_config_item("result", i, is_multi_metric)
            result = None
            if result_config:
                getter_type = (
                    result_config.get("type", "") if isinstance(result_config, dict) else ""
                )
                if getter_type:
                    try:
                        result = get_result(getter_type, env, result_config)
                    except ValueError as e:
                        logger.warning(
                            f"Getter type '{getter_type}' not found for task {task.id}: {e}"
                        )
                        result = None
                    except Exception as e:
                        logger.error(f"Getter '{getter_type}' failed: {e}")
                        result = None

            # 3. Get expected value
            expected_config = get_config_item("expected", i, is_multi_metric)
            expected = None
            if expected_config:
                if isinstance(expected_config, dict) and "type" in expected_config:
                    getter_type = expected_config.get("type", "")
                    if getter_type:
                        try:
                            expected = get_result(getter_type, env, expected_config)
                        except ValueError as e:
                            logger.warning(
                                f"Expected getter type '{getter_type}' not found for task {task.id}: {e}"
                            )
                            expected = expected_config
                        except Exception as e:
                            logger.error(f"Expected getter '{getter_type}' failed: {e}")
                            expected = None
                    else:
                        expected = expected_config
                else:
                    expected = expected_config

            # 4. Get options
            options = get_config_item("options", i, is_multi_metric)
            if options is None:
                options = {}

            # 5. Call metric
            current_score = 0.0
            if metric in METRIC_REGISTRY:
                try:
                    if expected is not None:
                        current_score = evaluate_metric(
                            metric, result=result, expected=expected, **options
                        )
                    else:
                        current_score = evaluate_metric(metric, result=result, **options)
                except Exception as e:
                    logger.error(f"Metric {metric} failed: {e}")
                    current_score = 0.0
            else:
                logger.warning(f"Unknown metric: {metric}")
                current_score = 0.0

            # Short-circuit logic
            if conj == "and" and current_score == 0.0:
                success = False
                return success, -0.01 * elapsed_steps
            if conj == "or" and current_score == 1.0:
                success = True
                return success, 1.0

            metric_scores.append(current_score)

        if not metric_scores:
            final_score = 0.0
        elif conj == "and":
            final_score = sum(metric_scores) / len(metric_scores)
        else:  # conj == "or"
            final_score = max(metric_scores)

        success = final_score > 0
        reward = final_score if success else -0.01 * elapsed_steps
        return success, reward

    def _execute_config_step(self, step: dict, env=None) -> None:
        """Execute a config/postconfig step."""
        step_type = step.get("type", "")
        params = step.get("parameters", step)

        handlers: dict[str, Callable[[dict, Any], None]] = {
            "sleep": self._sleep_setup,
            "launch": self._launch_setup,
            "execute": self._execute_setup,
            "command": self._execute_setup,
            "exec": self._execute_setup,
            "activate_window": self._activate_window_setup,
            "close_window": self._close_window_setup,
            "open": self._open_setup,
            "download": self._download_setup,
            "upload_file": self._upload_file_setup,
            "change_wallpaper": self._change_wallpaper_setup,
            "chrome_open_tabs": self._chrome_open_tabs_setup,
            "chrome_close_tabs": self._chrome_close_tabs_setup,
            "googledrive": self._googledrive_setup,
            "login": self._login_setup,
            "update_browse_history": self._update_browse_history_setup,
            "execute_with_verification": self._execute_with_verification_setup,
            "proxy": self._proxy_setup,
            "create_file": self._create_file_setup,
            "open_url": self._open_url_setup,
        }

        handler = handlers.get(step_type)
        if handler is None:
            logger.warning(f"Unhandled config step type: {step_type}")
            return
        handler(params, env)

    def teardown(self) -> None:
        self.observers.clear()
        self.active_task = None

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p

        candidates = [
            Path.cwd() / p,
            Path(__file__).resolve().parents[2] / p,
            Path(__file__).resolve().parents[2] / "tasks" / p,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _run_command(
        self,
        command: list[str] | str,
        env=None,
        *,
        shell: bool = False,
        background: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if env is not None and hasattr(env, "docker_provider") and env.docker_provider:
            container = getattr(env.docker_provider, "container", None)
            if container is not None:
                if isinstance(command, list):
                    cmd_exec: list[str] = [str(part) for part in command]
                    if shell:
                        cmd_exec = [
                            "/bin/bash",
                            "-lc",
                            " ".join(shlex.quote(part) for part in cmd_exec),
                        ]
                else:
                    cmd_exec = ["/bin/bash", "-lc", command] if shell else shlex.split(command)

                if timeout is not None and timeout > 0 and not background:
                    cmd_exec = ["timeout", f"{int(timeout)}s", *cmd_exec]

                try:
                    result = container.exec_run(cmd_exec, detach=background)
                except Exception as exc:
                    logger.error(f"Container command execution failed: {exc}")
                    return {"returncode": 1, "stdout": "", "stderr": str(exc)}

                if background:
                    return {"returncode": 0, "stdout": "", "stderr": ""}

                output = result.output.decode("utf-8", errors="replace")
                return {
                    "returncode": int(result.exit_code),
                    "stdout": output if result.exit_code == 0 else "",
                    "stderr": "" if result.exit_code == 0 else output,
                }

            cmd_str = " ".join(command) if isinstance(command, list) else command
            out = env.docker_provider.execute(
                cmd_str,
                shell=shell,
                background=background,
                timeout=int(timeout) if timeout else None,
            )
            return {"returncode": 0, "stdout": out, "stderr": ""}

        if background:
            subprocess.Popen(
                command,
                shell=shell,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"returncode": 0, "stdout": "", "stderr": ""}

        proc = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}

    def _replace_template_vars(self, command: list[str] | str, env=None) -> list[str] | str:
        screen_width = 1280
        screen_height = 960
        client_password = os.environ.get("CLIENT_PASSWORD", "")

        mapping = {
            "{CLIENT_PASSWORD}": client_password,
            "{SCREEN_WIDTH}": str(screen_width),
            "{SCREEN_HEIGHT}": str(screen_height),
            "{SCREEN_WIDTH_HALF}": str(screen_width // 2),
            "{SCREEN_HEIGHT_HALF}": str(screen_height // 2),
        }

        def replace_text(text: str) -> str:
            out = text
            for key, value in mapping.items():
                out = out.replace(key, value)
            return out

        if isinstance(command, list):
            return [replace_text(item) for item in command]
        return replace_text(command)

    def _sleep_setup(self, params: dict, env=None) -> None:
        seconds = float(params.get("seconds", 1))
        time.sleep(seconds)

    def _launch_setup(self, params: dict, env=None) -> None:
        command = params.get("command", [])
        shell = bool(params.get("shell", False))
        if not command:
            return
        self._run_command(command, env=env, shell=shell, background=True)

    def _execute_setup(self, params: dict, env=None) -> None:
        command = params.get("command", [])
        shell = bool(params.get("shell", False))
        until = params.get("until") or {}
        stdout_file = params.get("stdout", "")
        stderr_file = params.get("stderr", "")
        if not command:
            return

        command = self._replace_template_vars(command, env=env)

        attempts = 0
        while True:
            attempts += 1
            result = self._run_command(command, env=env, shell=shell)

            if stdout_file:
                out_path = self.cache_dir / stdout_file
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(result.get("stdout", ""), encoding="utf-8")
            if stderr_file:
                err_path = self.cache_dir / stderr_file
                err_path.parent.mkdir(parents=True, exist_ok=True)
                err_path.write_text(result.get("stderr", ""), encoding="utf-8")

            if not until:
                return

            matched = False
            if "returncode" in until and result["returncode"] == until["returncode"]:
                matched = True
            if "stdout" in until and str(until["stdout"]) in result.get("stdout", ""):
                matched = True
            if "stderr" in until and str(until["stderr"]) in result.get("stderr", ""):
                matched = True

            if matched or attempts >= 5:
                return
            time.sleep(0.3)

    def _execute_with_verification_setup(self, params: dict, env=None) -> None:
        command = params.get("command", [])
        verification = params.get("verification") or {}
        verification_mode = str(params.get("verification_mode", "all")).strip().lower()
        if verification_mode not in {"all", "any"}:
            verification_mode = "all"
        max_wait_time = int(params.get("max_wait_time", 10))
        check_interval = float(params.get("check_interval", 1.0))
        per_check_timeout = float(params.get("per_check_timeout", 2.0))
        shell = bool(params.get("shell", False))
        background = bool(params.get("background", False))

        command = self._replace_template_vars(command, env=env)

        if command:
            self._run_command(command, env=env, shell=shell, background=background)

        if not verification:
            return

        window_exists = verification.get("window_exists")
        window_name = ""
        window_strict = False
        window_by_class = False
        if isinstance(window_exists, str):
            window_name = window_exists
        elif isinstance(window_exists, dict):
            window_name = str(window_exists.get("window_name", "")).strip()
            window_strict = bool(window_exists.get("strict", False))
            window_by_class = bool(window_exists.get("by_class", False))

        command_success = verification.get("command_success")
        if command_success:
            command_success = self._replace_template_vars(command_success, env=env)

        start = time.time()
        while time.time() - start <= max_wait_time:
            checks: list[bool] = []

            if window_name:
                selector = "--class" if window_by_class else "--name"
                pattern = f"^{re.escape(window_name)}$" if window_strict else window_name
                try:
                    result = self._run_command(
                        ["xdotool", "search", selector, pattern],
                        env=env,
                        timeout=per_check_timeout,
                    )
                    matched = result["returncode"] == 0
                    if not matched and window_by_class:
                        fallback = self._run_command(
                            ["xdotool", "search", "--name", pattern],
                            env=env,
                            timeout=per_check_timeout,
                        )
                        matched = fallback["returncode"] == 0
                    checks.append(matched)
                except Exception:
                    checks.append(False)

            if command_success:
                try:
                    result = self._run_command(
                        command_success,
                        env=env,
                        shell=isinstance(command_success, str),
                        timeout=per_check_timeout,
                    )
                    checks.append(result["returncode"] == 0)
                except Exception:
                    checks.append(False)

            if checks:
                if verification_mode == "any":
                    ok = any(checks)
                else:
                    ok = all(checks)
            else:
                ok = True

            if ok:
                return
            time.sleep(check_interval)

        raise RuntimeError("execute_with_verification did not satisfy verification criteria")

    def _activate_window_setup(self, params: dict, env=None) -> None:
        window_name = str(params.get("window_name", "")).strip()
        if not window_name:
            return

        strict = bool(params.get("strict", False))
        by_class = bool(params.get("by_class", False))
        selector = "--class" if by_class else "--name"
        pattern = f"^{re.escape(window_name)}$" if strict else window_name

        command = f"xdotool search {selector} {json.dumps(pattern)} | head -n1 | xargs -r xdotool windowactivate"
        self._run_command(command, env=env, shell=True)

    def _close_window_setup(self, params: dict, env=None) -> None:
        window_name = str(params.get("window_name", "")).strip()
        if not window_name:
            return

        strict = bool(params.get("strict", False))
        by_class = bool(params.get("by_class", False))
        selector = "--class" if by_class else "--name"
        pattern = f"^{re.escape(window_name)}$" if strict else window_name

        command = (
            f"xdotool search {selector} {json.dumps(pattern)} | xargs -r -n1 xdotool windowclose"
        )
        self._run_command(command, env=env, shell=True)

    def _open_setup(self, params: dict, env=None) -> None:
        path = str(params.get("path", "")).strip()
        if not path:
            return
        resolved = self._resolve_path(path)

        wait_for_window = params.get("window_name") or params.get("wait_for_window")
        if wait_for_window:
            wait_target = str(wait_for_window).strip()
            verification = {
                "window_exists": {
                    "window_name": wait_target,
                    "strict": bool(params.get("strict", False)),
                    "by_class": bool(params.get("by_class", False)),
                },
                "command_success": ["pgrep", "-f", wait_target],
            }
            self._execute_with_verification_setup(
                {
                    "command": ["xdg-open", str(resolved)],
                    "verification": verification,
                    "verification_mode": "any",
                    "max_wait_time": params.get("max_wait_time", 10),
                    "check_interval": params.get("check_interval", 1.0),
                    "per_check_timeout": params.get("per_check_timeout", 2.0),
                    "shell": False,
                    "background": True,
                },
                env=env,
            )
            return

        self._run_command(["xdg-open", str(resolved)], env=env, background=True)

    def _download_setup(self, params: dict, env=None) -> None:
        files = params.get("files", [])
        for file_spec in files:
            url = str(file_spec.get("url", "")).strip()
            target_path = str(file_spec.get("path", "")).strip()
            if not url or not target_path:
                continue

            target = Path(target_path)
            target.parent.mkdir(parents=True, exist_ok=True)

            cache_name = f"{abs(hash(url))}_{target.name}"
            cache_path = self.cache_dir / cache_name
            if not cache_path.exists():
                with requests.get(url, stream=True, timeout=300) as response:
                    response.raise_for_status()
                    with cache_path.open("wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

            shutil.copy2(cache_path, target)

    def _upload_file_setup(self, params: dict, env=None) -> None:
        files = params.get("files", [])
        for file_spec in files:
            local_path = str(file_spec.get("local_path", "")).strip()
            target_path = str(file_spec.get("path", "")).strip()
            if not local_path or not target_path:
                continue

            src = self._resolve_path(local_path)
            if not src.exists():
                raise FileNotFoundError(f"upload_file source not found: {src}")

            dest = Path(target_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def _change_wallpaper_setup(self, params: dict, env=None) -> None:
        path = str(params.get("path", "")).strip()
        if not path:
            return
        resolved = self._resolve_path(path)
        command = (
            "xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/image-path "
            f"-s {json.dumps(str(resolved))} || "
            "xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/workspace0/last-image "
            f"-s {json.dumps(str(resolved))}"
        )
        self._run_command(command, env=env, shell=True)

    def _get_cdp_endpoints(self, env=None) -> list[str]:
        endpoints = ["http://127.0.0.1:1337", "http://127.0.0.1:9222"]
        if env is not None and hasattr(env, "docker_provider") and env.docker_provider:
            cdp_port = getattr(env.docker_provider, "cdp_port", None)
            if cdp_port:
                endpoints.insert(0, f"http://127.0.0.1:{cdp_port}")
        return endpoints

    def _connect_chrome(self, playwright, env=None):
        last_error = None
        for endpoint in self._get_cdp_endpoints(env=env):
            for _ in range(15):
                try:
                    return playwright.chromium.connect_over_cdp(endpoint)
                except Exception as exc:
                    last_error = exc
                    time.sleep(1)
        raise RuntimeError(f"Unable to connect to Chrome CDP: {last_error}")

    def _chrome_open_tabs_setup(self, params: dict, env=None) -> None:
        urls = params.get("urls_to_open", [])
        if not urls:
            return

        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = self._connect_chrome(playwright, env=env)
            if not browser.contexts:
                browser.new_context()
            context = browser.contexts[0]

            default_page = context.pages[0] if context.pages else None
            for url in urls:
                page = context.new_page()
                try:
                    page.goto(str(url), timeout=60000)
                except Exception:
                    logger.warning(f"Timed out while opening tab: {url}")

            if default_page is not None:
                try:
                    default_page.close()
                except Exception:
                    pass

    def _chrome_close_tabs_setup(self, params: dict, env=None) -> None:
        urls_to_close = params.get("urls_to_close", [])
        if not urls_to_close:
            return

        from playwright.sync_api import sync_playwright

        from .metrics.utils import compare_urls

        with sync_playwright() as playwright:
            browser = self._connect_chrome(playwright, env=env)
            if not browser.contexts:
                return
            context = browser.contexts[0]

            for target_url in urls_to_close:
                for page in list(context.pages):
                    try:
                        if compare_urls(page.url, str(target_url)):
                            page.close()
                            break
                    except Exception:
                        continue

    def _googledrive_setup(self, params: dict, env=None) -> None:
        from pydrive2.auth import GoogleAuth
        from pydrive2.drive import GoogleDrive

        settings_file = str(
            params.get("settings_file", "evaluation_examples/settings/googledrive/settings.yml")
        )
        settings_path = self._resolve_path(settings_file)
        gauth = GoogleAuth(settings_file=str(settings_path))
        drive = GoogleDrive(gauth)

        def mkdirs(paths: list[str]) -> str:
            parent_id = "root"
            for segment in paths:
                query = (
                    f'"{parent_id}" in parents and title = "{segment}" '
                    "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                )
                folders = drive.ListFile({"q": query}).GetList()
                if folders:
                    parent_id = folders[0]["id"]
                    continue

                metadata: dict[str, Any] = {
                    "title": segment,
                    "mimeType": "application/vnd.google-apps.folder",
                }
                if parent_id != "root":
                    metadata["parents"] = [{"id": parent_id}]
                folder = drive.CreateFile(metadata)
                folder.Upload()
                parent_id = folder["id"]
            return parent_id

        operations = params.get("operation", [])
        args = params.get("args", [])
        for idx, operation in enumerate(operations):
            op_args = args[idx] if idx < len(args) else {}
            if operation == "delete":
                query = str(op_args.get("query", "")).strip()
                trash = bool(op_args.get("trash", False))
                file_query = (
                    f"({query}) and mimeType != 'application/vnd.google-apps.folder'"
                    if query
                    else "mimeType != 'application/vnd.google-apps.folder'"
                )
                folder_query = (
                    f"({query}) and mimeType = 'application/vnd.google-apps.folder'"
                    if query
                    else "mimeType = 'application/vnd.google-apps.folder'"
                )

                for item in drive.ListFile({"q": file_query}).GetList():
                    item.Trash() if trash else item.Delete()
                for item in drive.ListFile({"q": folder_query}).GetList():
                    item.Trash() if trash else item.Delete()
            elif operation == "mkdirs":
                folder_path = op_args.get("path", [])
                if isinstance(folder_path, str):
                    folder_path = [folder_path]
                mkdirs(folder_path)
            elif operation == "upload":
                url = str(op_args.get("url", "")).strip()
                destination = op_args.get("path", [])
                if isinstance(destination, str):
                    destination = [destination]
                if not url or not destination:
                    continue

                with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp_file:
                    tmp_path = Path(tmp_file.name)
                    with requests.get(url, stream=True, timeout=300) as response:
                        response.raise_for_status()
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                tmp_file.write(chunk)

                parent_id = mkdirs(destination[:-1]) if len(destination) > 1 else "root"
                metadata: dict[str, Any] = {"title": destination[-1]}
                if parent_id != "root":
                    metadata["parents"] = [{"id": parent_id}]
                uploaded = drive.CreateFile(metadata)
                uploaded.SetContentFile(str(tmp_path))
                uploaded.Upload()
                tmp_path.unlink(missing_ok=True)
            else:
                raise ValueError(f"Unsupported googledrive operation: {operation}")

    def _login_setup(self, params: dict, env=None) -> None:
        platform_name = str(params.get("platform", "")).strip().lower()
        settings_file = params.get("settings_file")
        if not settings_file:
            raise ValueError("login setup requires settings_file")

        settings_path = self._resolve_path(str(settings_file))
        with settings_path.open("r", encoding="utf-8") as f:
            credentials = json.load(f)

        email = credentials.get("email")
        password = credentials.get("password")
        if not email or not password:
            raise ValueError("login settings must contain email and password")

        if platform_name != "googledrive":
            raise NotImplementedError(f"Unsupported login platform: {platform_name}")

        from playwright.sync_api import TimeoutError, sync_playwright

        with sync_playwright() as playwright:
            browser = self._connect_chrome(playwright, env=env)
            if not browser.contexts:
                browser.new_context()
            context = browser.contexts[0]
            page = context.new_page()
            page.goto("https://drive.google.com/drive/my-drive", timeout=60000)

            try:
                page.wait_for_selector('input[type="email"]', state="visible", timeout=5000)
                page.fill('input[type="email"]', str(email))
                page.click("#identifierNext > div > button")
                page.wait_for_selector('input[type="password"]', state="visible", timeout=10000)
                page.fill('input[type="password"]', str(password))
                page.click("#passwordNext > div > button")
                page.wait_for_load_state("load", timeout=10000)
            except TimeoutError as exc:
                raise RuntimeError("Google Drive login timed out") from exc

    def _update_browse_history_setup(self, params: dict, env=None) -> None:
        history_items = params.get("history", [])
        if not history_items:
            return

        chrome_history_path = Path("/root/chrome-profile/Default/History")
        chrome_history_path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path_str = tempfile.mkstemp(
            prefix="history_setup_", suffix=".sqlite", dir=str(chrome_history_path.parent)
        )
        os.close(fd)
        temp_history_path = Path(temp_path_str)

        try:
            if chrome_history_path.exists():
                shutil.copy2(chrome_history_path, temp_history_path)

            conn = sqlite3.connect(str(temp_history_path), timeout=30)
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA busy_timeout = 30000")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS urls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url LONGVARCHAR,
                        title LONGVARCHAR,
                        visit_count INTEGER DEFAULT 0,
                        typed_count INTEGER DEFAULT 0,
                        last_visit_time INTEGER DEFAULT 0,
                        hidden INTEGER DEFAULT 0
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS visits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url INTEGER,
                        visit_time INTEGER,
                        from_visit INTEGER,
                        transition INTEGER,
                        segment_id INTEGER,
                        visit_duration INTEGER
                    )
                    """
                )

                epoch_start = datetime(1601, 1, 1)
                for item in history_items:
                    url = str(item.get("url", ""))
                    title = str(item.get("title", ""))
                    seconds_ago = int(item.get("visit_time_from_now_in_seconds", 0))
                    visit_time = datetime.now() - timedelta(seconds=seconds_ago)
                    chrome_timestamp = int((visit_time - epoch_start).total_seconds() * 1_000_000)

                    cursor.execute(
                        """
                        INSERT INTO urls (url, title, visit_count, typed_count, last_visit_time, hidden)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (url, title, 1, 0, chrome_timestamp, 0),
                    )
                    url_id = cursor.lastrowid
                    cursor.execute(
                        """
                        INSERT INTO visits (url, visit_time, from_visit, transition, segment_id, visit_duration)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (url_id, chrome_timestamp, 0, 805306368, 0, 0),
                    )
                conn.commit()
            finally:
                conn.close()

            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(chrome_history_path) + suffix)
                if sidecar.exists():
                    sidecar.unlink(missing_ok=True)

            temp_history_path.replace(chrome_history_path)
        finally:
            if temp_history_path.exists():
                temp_history_path.unlink(missing_ok=True)

    def _proxy_setup(self, params: dict, env=None) -> None:
        proxy_url = str(
            params.get("proxy_url")
            or os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
            or ""
        ).strip()
        if not proxy_url:
            logger.warning("proxy requested but no proxy_url/HTTP_PROXY configured; skipping")
            return

        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url
        os.environ["HTTP_PROXY"] = proxy_url
        os.environ["HTTPS_PROXY"] = proxy_url

        if bool(params.get("start_tinyproxy", False)):
            port = int(params.get("local_port", 18888))
            config_path = Path("/tmp/tinyproxy.conf")
            config_path.write_text(
                f"Port {port}\nAllow 127.0.0.1\nUpstream http {proxy_url.replace('http://', '')}\n",
                encoding="utf-8",
            )
            self._run_command(
                f"tinyproxy -c {config_path} -d", env=env, shell=True, background=True
            )

    def _create_file_setup(self, params: dict, env=None) -> None:
        path = params.get("path")
        if not path:
            return
        content = str(params.get("content", ""))
        file_path = Path(str(path))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def _open_url_setup(self, params: dict, env=None) -> None:
        url = str(params.get("url", "")).strip()
        if not url:
            return
        try:
            self._run_command(["firefox", "--new-tab", url], env=env, background=True)
        except Exception:
            self._run_command(["google-chrome", "--new-tab", url], env=env, background=True)
