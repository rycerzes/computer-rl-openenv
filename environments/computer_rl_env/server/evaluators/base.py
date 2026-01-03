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

    def evaluate(self, task_config: TaskConfig, elapsed_steps: int) -> tuple[bool, float]:
        from .metrics import evaluate_metric

        evaluator_config = task_config.evaluator
        metric_type = evaluator_config.get("type")
        params = evaluator_config.get("params", {})

        if metric_type:
            success = evaluate_metric(str(metric_type), **params)
        else:
            success = False
        reward = 1.0 if success else 0.0

        if not success:
            step_penalty = 0.01 * elapsed_steps
            reward -= step_penalty

        return success, reward

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
