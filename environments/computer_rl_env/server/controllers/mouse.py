import os

import pyautogui


class MouseController:
    def __init__(self, display: str = ":99"):
        self.display = display
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = display
        pyautogui.FAILSAFE = False

    def _normalize_coords(
        self, x: int, y: int, screen_width: int = 1280, screen_height: int = 960
    ):
        screen_w, screen_h = pyautogui.size()
        return int(x / 1000 * screen_w), int(y / 1000 * screen_h)

    def move(self, x: int, y: int):
        px, py = self._normalize_coords(x, y)
        pyautogui.moveTo(px, py)

    def click(self, x: int, y: int, button: str = "left", num_clicks: int = 1):
        px, py = self._normalize_coords(x, y)
        pyautogui.click(px, py, clicks=num_clicks, button=button)

    def type_text(self, text: str):
        pyautogui.write(text)

    def press_key(self, key: str):
        pyautogui.press(key)

    def scroll(self, x: int, y: int, direction: str = "up", amount: int = 1):
        px, py = self._normalize_coords(x, y)
        pyautogui.moveTo(px, py)
        scroll_amount = -amount if direction == "up" else amount
        pyautogui.scroll(scroll_amount)

    def drag(self, x1: int, y1: int, x2: int, y2: int):
        px1, py1 = self._normalize_coords(x1, y1)
        px2, py2 = self._normalize_coords(x2, y2)
        pyautogui.moveTo(px1, py1)
        pyautogui.dragTo(px2, py2)
