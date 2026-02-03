from pydantic import BaseModel, Field


class TaskConfig(BaseModel):
    id: str
    instruction: str
    setup: list[dict] = Field(default_factory=list)
    evaluator: dict
    max_steps: int = 50
    timeout: int = 60
    metadata: dict = Field(default_factory=dict)


class TaskManager:
    def __init__(self):
        self.active_task = None
        self.observers = []

    def setup(self, task_config: TaskConfig) -> bool:
        for step in task_config.setup:
            step_type = step.get("type")

            if step_type == "launch":
                app = step.get("app")
                if app:
                    self._launch_app(str(app))
            elif step_type == "download":
                url = step.get("url")
                path = step.get("path")
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

        self.active_task = task_config
        return True

    def evaluate(self, task_config: TaskConfig, elapsed_steps: int, env=None) -> tuple[bool, float]:
        """Evaluate task completion using OSWorld-style evaluation.

        OSWorld evaluation flow:
        1. Run postconfig steps (save files, restart apps)
        2. Fetch result via getter
        3. Compare with expected using metric

        Args:
            task_config: Task configuration with evaluator
            elapsed_steps: Number of steps taken
            env: Environment instance (for getters)

        Returns:
            (success, reward) tuple
        """
        from .getters import GETTER_REGISTRY, get_result
        from .metrics import METRIC_REGISTRY, evaluate_metric

        evaluator_config = task_config.evaluator

        # Handle legacy format (type/params)
        if "type" in evaluator_config and "func" not in evaluator_config:
            metric_type = evaluator_config.get("type")
            params = evaluator_config.get("params", {})
            if metric_type:
                score = evaluate_metric(str(metric_type), **params)
            else:
                score = 0.0
            success = score > 0
            reward = score if success else -0.01 * elapsed_steps
            return success, reward

        # OSWorld format (func/result/expected)
        func_name = evaluator_config.get("func", "")

        # Handle infeasible tasks
        if func_name == "infeasible":
            # Task is meant to be failed if agent tries
            success = False
            return success, 0.0

        # 1. Run postconfig if present
        postconfig = evaluator_config.get("postconfig", [])
        for step in postconfig:
            self._execute_config_step(step, env)

        # 2. Fetch result via getter
        result_config = evaluator_config.get("result", {})
        result = None
        if result_config:
            getter_type = result_config.get("type", "")
            if getter_type and getter_type in GETTER_REGISTRY:
                try:
                    result = get_result(getter_type, env, result_config)
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).error(f"Getter failed: {e}")
                    result = None

        # 3. Get expected value
        expected_config = evaluator_config.get("expected", {})
        expected = None
        if expected_config:
            if isinstance(expected_config, dict) and "type" in expected_config:
                getter_type = expected_config.get("type", "")
                if getter_type and getter_type in GETTER_REGISTRY:
                    expected = get_result(getter_type, env, expected_config)
                else:
                    expected = expected_config
            else:
                expected = expected_config

        # 4. Get options
        options = evaluator_config.get("options", {})

        # 5. Call metric
        if func_name in METRIC_REGISTRY:
            try:
                if expected is not None:
                    score = evaluate_metric(func_name, result=result, expected=expected, **options)
                else:
                    score = evaluate_metric(func_name, result=result, **options)
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"Metric failed: {e}")
                score = 0.0
        else:
            # Unknown metric
            import logging

            logging.getLogger(__name__).warning(f"Unknown metric: {func_name}")
            score = 0.0

        success = score > 0
        reward = score if success else -0.01 * elapsed_steps
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
        elif step_type == "download":
            files = params.get("files", [])
            for f in files:
                url = f.get("url", "")
                path = f.get("path", "")
                if url and path:
                    self._download_file(url, path)

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
