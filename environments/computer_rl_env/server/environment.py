import time
import uuid
from typing import Optional

from openenv.core import Environment

from ..models import (
    Click,
    ComputerAction,
    ComputerObservation,
    ComputerState,
    Drag,
    HotKey,
    MouseMove,
    PressKey,
    Scroll,
    TypeText,
    Wait,
)
from .controllers.accessibility import AccessibilityParser
from .controllers.keyboard import KeyboardController
from .controllers.mouse import MouseController
from .controllers.screenshot import ScreenCapture
from .evaluators.base import TaskConfig, TaskManager
from .rewards import RewardComputer


class ComputerEnvironment(Environment[ComputerAction, ComputerObservation, ComputerState]):
    SUPPORTS_CONCURRENT_SESSIONS = False

    def __init__(self, display: str = ":99", reward_config: dict | None = None):
        super().__init__()
        self.display = display
        self.step_count = 0
        self.episode_id = None
        self.current_task = None

        self.mouse_controller = MouseController(display=display)
        self.keyboard_controller = KeyboardController(display=display)
        self.screen_capture = ScreenCapture(display=display)
        self.accessibility_parser = AccessibilityParser()

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
        self.current_task = kwargs.get("task_config")
        self.prev_observation = None

        if self.current_task:
            task_manager = TaskManager()
            task_config = TaskConfig(**self.current_task)
            task_manager.setup(task_config)

        screenshot = self.screen_capture.capture()
        acc_tree = self.accessibility_parser.parse()
        active_info = self.accessibility_parser.get_active_window() or {}

        obs = ComputerObservation(
            screenshot_base64=screenshot,
            accessibility_tree=acc_tree,
            instruction=self.current_task.get("instruction") if self.current_task else None,
            active_window=active_info.get("active_window"),
            active_app=active_info.get("active_app"),
            step_count=0,
            done=False,
        )
        self.prev_observation = obs
        return obs

    def _evaluate_task_success(self) -> bool:
        if not self.current_task:
            return False

        task_manager = TaskManager()
        task_config = TaskConfig(**self.current_task)
        success, _ = task_manager.evaluate(task_config, self.step_count)
        return success

    def step(
        self, action: ComputerAction, timeout_s: Optional[float] = None, **kwargs
    ) -> ComputerObservation:
        self.step_count += 1

        # Unwrap the action variant from the wrapper
        computer_action = action.action

        if isinstance(computer_action, MouseMove):
            self.mouse_controller.move(computer_action.x, computer_action.y)
        elif isinstance(computer_action, Click):
            self.mouse_controller.click(computer_action.x, computer_action.y, computer_action.button, computer_action.num_clicks)
        elif isinstance(computer_action, TypeText):
            self.keyboard_controller.type_text(computer_action.text)
        elif isinstance(computer_action, PressKey):
            self.keyboard_controller.press_key(computer_action.key)
        elif isinstance(computer_action, HotKey):
            self.keyboard_controller.press_hotkey(*computer_action.keys)
        elif isinstance(computer_action, Scroll):
            self.mouse_controller.scroll(computer_action.x, computer_action.y, computer_action.direction, computer_action.amount)
        elif isinstance(computer_action, Drag):
            self.mouse_controller.drag(computer_action.x1, computer_action.y1, computer_action.x2, computer_action.y2)
        elif isinstance(computer_action, Wait):
            time.sleep(computer_action.seconds)
        elif computer_action.action_type == "done":
            pass

        time.sleep(0.5)

        screenshot = self.screen_capture.capture()
        acc_tree = self.accessibility_parser.parse()
        active_info = self.accessibility_parser.get_active_window() or {}

        done = False
        if self.current_task:
            max_steps = self.current_task.get("max_steps", 100)
            done = self.step_count >= max_steps

        curr_obs = ComputerObservation(
            screenshot_base64=screenshot,
            accessibility_tree=acc_tree,
            instruction=self.current_task.get("instruction") if self.current_task else None,
            active_window=active_info.get("active_window"),
            active_app=active_info.get("active_app"),
            step_count=self.step_count,
            done=done,
        )

        prev_obs = self.prev_observation
        self.prev_observation = curr_obs

        if done or computer_action.action_type == "done":
            success = self._evaluate_task_success()
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
            current_task=self.current_task,
            display=self.display,
        )
