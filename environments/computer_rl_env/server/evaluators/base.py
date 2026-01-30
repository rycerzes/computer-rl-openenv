from typing import Any

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
                self._launch_app(step.get("app"))
            elif step_type == "download":
                self._download_file(step.get("url"), step.get("path"))
            elif step_type == "create_file":
                self._create_file(step.get("path"), step.get("content", ""))
            elif step_type == "open_url":
                self._open_url(step.get("url"))

        self.active_task = task_config
        return True

    def evaluate(self, task_config: TaskConfig, elapsed_steps: int) -> tuple[bool, float]:
        from .metrics import evaluate_metric

        evaluator_config = task_config.evaluator
        metric_type = evaluator_config.get("type")
        params = evaluator_config.get("params", {})

        success = evaluate_metric(metric_type, **params)
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
