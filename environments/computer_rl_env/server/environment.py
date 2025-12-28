import time
import uuid
from typing import Optional

from openenv.core import Environment

from ..models import ComputerAction, ComputerObservation, ComputerState
from .controllers.accessibility import AccessibilityParser
from .controllers.keyboard import KeyboardController
from .controllers.mouse import MouseController
from .controllers.screenshot import ScreenCapture


class ComputerEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = False

    def __init__(self, display: str = ":99"):
        self.display = display
        self.step_count = 0
        self.episode_id = None
        self.current_task = None

        self.mouse_controller = MouseController(display=display)
        self.keyboard_controller = KeyboardController(display=display)
        self.screen_capture = ScreenCapture(display=display)
        self.accessibility_parser = AccessibilityParser()

    def reset(
        self, seed: Optional[int] = None, episode_id: Optional[str] = None, **kwargs
    ) -> ComputerObservation:
        self.episode_id = episode_id or str(uuid.uuid4())
        self.step_count = 0
        self.current_task = kwargs.get("task_config")

        screenshot = self.screen_capture.capture()
        acc_tree = self.accessibility_parser.parse()

        return ComputerObservation(
            screenshot_base64=screenshot,
            accessibility_tree=acc_tree,
            instruction=self.current_task.get("instruction") if self.current_task else None,
            step_count=0,
            done=False,
        )

    def step(
        self, action: ComputerAction, timeout_s: Optional[float] = None, **kwargs
    ) -> ComputerObservation:
        self.step_count += 1

        if action.action_type == "move":
            self.mouse_controller.move(action.x, action.y)
        elif action.action_type == "click":
            self.mouse_controller.click(action.x, action.y, action.button, action.num_clicks)
        elif action.action_type == "type":
            self.keyboard_controller.type_text(action.text)
        elif action.action_type == "press":
            self.keyboard_controller.press_key(action.key)
        elif action.action_type == "hotkey":
            self.keyboard_controller.press_hotkey(*action.keys)
        elif action.action_type == "scroll":
            self.mouse_controller.scroll(action.x, action.y, action.direction, action.amount)
        elif action.action_type == "drag":
            self.mouse_controller.drag(action.x1, action.y1, action.x2, action.y2)
        elif action.action_type == "wait":
            time.sleep(action.seconds)
        elif action.action_type == "done":
            pass

        time.sleep(0.5)

        screenshot = self.screen_capture.capture()
        acc_tree = self.accessibility_parser.parse()

        reward = 0.0
        done = False

        if self.current_task:
            max_steps = self.current_task.get("max_steps", 100)
            done = self.step_count >= max_steps

        return ComputerObservation(
            screenshot_base64=screenshot,
            accessibility_tree=acc_tree,
            instruction=self.current_task.get("instruction") if self.current_task else None,
            step_count=self.step_count,
            reward=reward,
            done=done,
        )

    @property
    def state(self) -> ComputerState:
        return ComputerState(
            step_count=self.step_count,
            episode_id=self.episode_id,
            current_task=self.current_task,
            display=self.display,
        )
