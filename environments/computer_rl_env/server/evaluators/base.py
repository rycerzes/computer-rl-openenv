import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from ...tasks.base import EvaluatorConfig, Task

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self):
        self.active_task = None
        self.observers = []

    def setup(self, task: Task) -> bool:
        steps = task.config
        for step in steps:
            step_type = step.get("type")

            if step_type == "launch":
                params = step.get("parameters", step)
                command = params.get("command", [])
                app = command[0] if isinstance(command, list) and command else params.get("app")
                if app:
                    self._launch_app(str(app))
            elif step_type == "download":
                params = step.get("parameters", step)
                files = params.get("files", [])
                for f in files:
                    url = f.get("url")
                    path = f.get("path")
                    if url and path:
                        self._download_file(str(url), str(path))

            elif step_type == "create_file":
                path = step.get("path")
                if path:
                    self._create_file(str(path), str(step.get("content", "")))
            elif step_type == "open_url":
                url = step.get("url")
                if url:
                    self._open_url(str(url))

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
        import time

        step_type = step.get("type", "")
        params = step.get("parameters", step)

        if step_type == "sleep":
            seconds = params.get("seconds", 1)
            time.sleep(seconds)
        elif step_type == "launch":
            command = params.get("command", [])
            if isinstance(command, list):
                self._launch_app(command[0] if command else "")
            else:
                self._launch_app(command)
        elif step_type == "execute":
            command = params.get("command", [])
            if env and hasattr(env, "docker_provider") and env.docker_provider:
                cmd_str = " ".join(command) if isinstance(command, list) else command
                env.docker_provider.execute(cmd_str)
        elif step_type == "activate_window":
            # Use xdotool to activate window
            window_name = params.get("window_name", "")
            if env and hasattr(env, "docker_provider") and env.docker_provider:
                env.docker_provider.execute(f'xdotool search --name "{window_name}" windowactivate')
        elif step_type == "open":
            path = params.get("path", "")
            if env and hasattr(env, "docker_provider") and env.docker_provider:
                env.docker_provider.execute(f"xdg-open '{path}' &")
        elif step_type in ("command", "exec"):
            # Aliases for "execute"
            command = params.get("command", [])
            if env and hasattr(env, "docker_provider") and env.docker_provider:
                cmd_str = " ".join(command) if isinstance(command, list) else command
                env.docker_provider.execute(cmd_str)
        elif step_type == "download":
            files = params.get("files", [])
            for f in files:
                url = f.get("url", "")
                path = f.get("path", "")
                if url and path:
                    self._download_file(url, path)
        else:
            logger.warning(f"Unhandled config step type: {step_type}")

    def teardown(self) -> None:
        self.observers.clear()
        self.active_task = None

    def _launch_app(self, app_name: str) -> None:
        import subprocess

        try:
            subprocess.Popen([app_name], start_new_session=True)
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

    def _download_file(self, url: str, path: str) -> None:
        import subprocess

        try:
            subprocess.run(
                ["wget", "-q", "-O", path, url], check=True, timeout=30, capture_output=True
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            pass

    def _create_file(self, path: str, content: str) -> None:
        import os

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
        except (OSError, IOError):
            pass

    def _open_url(self, url: str) -> None:
        import subprocess

        try:
            subprocess.Popen(["firefox", "--new-tab", url], start_new_session=True)
        except (FileNotFoundError, subprocess.SubprocessError):
            try:
                subprocess.Popen(["google-chrome", "--new-tab", url], start_new_session=True)
            except (FileNotFoundError, subprocess.SubprocessError):
                pass
