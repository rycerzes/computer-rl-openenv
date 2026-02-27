import logging
import os
import time
import uuid
from typing import Optional

import pyautogui
from openenv.core import Environment

from ..models import (
    ComputerAction,
    ComputerObservation,
    ComputerState,
)
from ..tasks.base import Task
from .controllers.accessibility import AccessibilityParser
from .controllers.screenshot import ScreenCapture
from .evaluators.base import TaskManager
from .rewards import RewardComputer

logger = logging.getLogger(__name__)

# Sentinel action strings (case-insensitive matching)
_SENTINEL_ACTIONS = {"WAIT", "DONE", "FAIL"}


class ComputerEnvironment(Environment[ComputerAction, ComputerObservation, ComputerState]):
    SUPPORTS_CONCURRENT_SESSIONS = False

    def __init__(self, display: str = ":99", reward_config: dict | None = None):
        super().__init__()
        self.display = display
        self.step_count = 0
        self.episode_id = None
        self.current_task: Optional[Task] = None

        # Ensure DISPLAY is set for pyautogui
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = display
        pyautogui.FAILSAFE = False  # type: ignore

        self.screen_capture = ScreenCapture(display=display)
        self.accessibility_parser = AccessibilityParser(max_depth=50, max_width=1024)

        reward_config = reward_config or {
            "mode": "sparse",
            "success_reward": 1.0,
            "failure_reward": 0.0,
            "step_penalty": 0.01,
            "reward_clamp": (-1.0, 1.0),
        }
        self.reward_computer = RewardComputer(reward_config)
        self.prev_observation = None

    def reset(
        self, seed: Optional[int] = None, episode_id: Optional[str] = None, **kwargs
    ) -> ComputerObservation:
        self.episode_id = episode_id or str(uuid.uuid4())
        self.step_count = 0
        self.prev_observation = None

        task_config = kwargs.get("task_config")
        if task_config:
            if isinstance(task_config, Task):
                self.current_task = task_config
            elif isinstance(task_config, dict):
                # Ensure minimum required fields for Task model
                if "id" not in task_config:
                    task_config["id"] = self.episode_id
                if "evaluator" not in task_config:
                    task_config["evaluator"] = {"func": "infeasible"}
                self.current_task = Task(**task_config)
            else:
                self.current_task = None
        else:
            self.current_task = None

        if self.current_task:
            task_manager = TaskManager()
            task_manager.setup(self.current_task, env=self)

        screenshot = self.screen_capture.capture()
        acc_tree = self.accessibility_parser.parse()
        acc_tree_xml = self.accessibility_parser.parse_xml()
        terminal_output = self.accessibility_parser.get_terminal_output()
        active_info = self.accessibility_parser.get_active_window() or {}

        obs = ComputerObservation(
            screenshot_base64=screenshot,
            accessibility_tree=acc_tree,
            accessibility_tree_xml=acc_tree_xml,
            terminal_output=terminal_output,
            terminal_exit_code=None,
            instruction=self.current_task.instruction if self.current_task else None,
            active_window=active_info.get("active_window"),
            active_app=active_info.get("active_app"),
            step_count=0,
            done=False,
        )
        self.prev_observation = obs
        return obs

    def _execute_pyautogui_action(self, action_str: str) -> str:
        """Execute a pyautogui action string.

        Args:
            action_str: PyAutoGUI-style Python string or sentinel.

        Returns:
            Action category: 'wait', 'done', 'fail', or 'action'.
        """
        action_str = action_str.strip()
        upper = action_str.upper()

        # Handle sentinel strings
        if upper == "WAIT":
            time.sleep(1)
            return "wait"
        if upper == "DONE":
            return "done"
        if upper == "FAIL":
            return "fail"

        # Execute pyautogui string in sandboxed namespace
        namespace = {"pyautogui": pyautogui, "time": time}
        try:
            exec(action_str, {"__builtins__": {}}, namespace)
        except Exception as e:
            logger.warning(f"Failed to execute action '{action_str}': {e}")

        return "action"

    def _evaluate_task_success(self, last_action: Optional[str] = None) -> bool:
        if not self.current_task:
            return False

        task_manager = TaskManager()
        success, _ = task_manager.evaluate(
            self.current_task, self.step_count, env=self, last_action=last_action
        )
        return success

    def step(
        self, action: ComputerAction, timeout_s: Optional[float] = None, **kwargs
    ) -> ComputerObservation:
        self.step_count += 1

        # Execute the pyautogui action string
        action_category = self._execute_pyautogui_action(action.action)

        time.sleep(0.5)

        screenshot = self.screen_capture.capture()
        acc_tree = self.accessibility_parser.parse()
        acc_tree_xml = self.accessibility_parser.parse_xml()
        terminal_output = self.accessibility_parser.get_terminal_output()
        active_info = self.accessibility_parser.get_active_window() or {}

        done = False
        if self.current_task:
            max_steps = self.current_task.max_steps
            done = self.step_count >= max_steps

        curr_obs = ComputerObservation(
            screenshot_base64=screenshot,
            accessibility_tree=acc_tree,
            accessibility_tree_xml=acc_tree_xml,
            terminal_output=terminal_output,
            terminal_exit_code=None,
            instruction=self.current_task.instruction if self.current_task else None,
            active_window=active_info.get("active_window"),
            active_app=active_info.get("active_app"),
            step_count=self.step_count,
            done=done,
        )

        prev_obs = self.prev_observation
        self.prev_observation = curr_obs

        if done or action_category in ("done", "fail"):
            success = self._evaluate_task_success(last_action=action_category)
            reward = self.reward_computer.compute(success, self.step_count, prev_obs, curr_obs)
            curr_obs.reward = reward
        else:
            reward = self.reward_computer.compute(False, self.step_count, prev_obs, curr_obs)
            curr_obs.reward = reward

        return curr_obs

    @property
    def state(self) -> ComputerState:
        return ComputerState(
            step_count=self.step_count,
            episode_id=self.episode_id,
            current_task=self.current_task.model_dump() if self.current_task else None,
            display=self.display,
        )
