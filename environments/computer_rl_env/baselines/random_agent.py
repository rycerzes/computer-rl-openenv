import random
from typing import Any, Dict, List, Tuple


class RandomAgent:
    """
    Random action baseline agent.
    Generates random pyautogui-style action strings.
    """

    def __init__(self, action_space: Dict[str, Any] = None):
        """
        Initialize RandomAgent.

        Args:
            action_space: Optional dictionary definition of allowed actions.
                          If None, uses default ranges.
        """
        self.action_space = action_space or {}
        # Default screen size for random coordinates
        self.screen_width = 1280
        self.screen_height = 960

    def predict(self, instruction: str, observation: Dict[str, Any]) -> Tuple[str, List[str]]:
        """
        Generate random pyautogui-style action strings.

        Args:
            instruction: The task instruction string.
            observation: The current observation dictionary.

        Returns:
            Tuple of (response_text, list_of_action_strings).
        """
        # Randomly choose an action type
        action_types = ["key", "type", "click", "right_click", "double_click", "move"]
        action_type = random.choice(action_types)

        actions: list[str] = []

        if action_type == "key":
            keys = ["enter", "space", "backspace", "tab", "escape", "up", "down", "left", "right"]
            key = random.choice(keys)
            actions.append(f"pyautogui.press('{key}')")

        elif action_type == "type":
            chars = "abcdefghijklmnopqrstuvwxyz "
            text = "".join(random.choice(chars) for _ in range(random.randint(1, 10)))
            actions.append(f"pyautogui.write('{text}')")

        elif action_type == "click":
            x = random.randint(0, self.screen_width - 1)
            y = random.randint(0, self.screen_height - 1)
            actions.append(f"pyautogui.click(x={x}, y={y})")

        elif action_type == "right_click":
            x = random.randint(0, self.screen_width - 1)
            y = random.randint(0, self.screen_height - 1)
            actions.append(f"pyautogui.click(x={x}, y={y}, button='right')")

        elif action_type == "double_click":
            x = random.randint(0, self.screen_width - 1)
            y = random.randint(0, self.screen_height - 1)
            actions.append(f"pyautogui.doubleClick(x={x}, y={y})")

        elif action_type == "move":
            x = random.randint(0, self.screen_width - 1)
            y = random.randint(0, self.screen_height - 1)
            actions.append(f"pyautogui.moveTo(x={x}, y={y})")

        # Add a wait action occasionally
        if random.random() < 0.1:
            actions.append("WAIT")

        return "I am acting randomly.", actions

    def reset(self, logger=None):
        """Reset agent state."""
        pass
