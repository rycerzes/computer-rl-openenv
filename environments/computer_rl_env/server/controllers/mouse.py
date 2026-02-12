import os

import pyautogui


class MouseController:
    def __init__(self, display: str = ":99"):
        self.display = display
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = display
        pyautogui.FAILSAFE = False  # type: ignore

    def move(self, x: int, y: int) -> None:
        pyautogui.moveTo(x, y)

    def click(self, x: int, y: int, button: str = "left", num_clicks: int = 1) -> None:
        pyautogui.click(x, y, clicks=num_clicks, button=button)

    def scroll(self, x: int, y: int, direction: str = "up", amount: int = 1) -> None:
        pyautogui.moveTo(x, y)
        scroll_amount = -amount if direction == "up" else amount
        pyautogui.scroll(scroll_amount)

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2)
