import os

import pyautogui


class KeyboardController:
    def __init__(self, display: str = ":99"):
        self.display = display
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = display
        pyautogui.FAILSAFE = False

    def type_text(self, text: str, delay: float = 0.01) -> None:
        pyautogui.write(text, interval=delay)

    def press_key(self, key: str) -> None:
        pyautogui.press(key)

    def hold_key(self, key: str) -> None:
        pyautogui.keyDown(key)

    def release_key(self, key: str) -> None:
        pyautogui.keyUp(key)

    def press_hotkey(self, *keys: str) -> None:
        pyautogui.hotkey(*keys)

    def write(self, text: str) -> None:
        pyautogui.typewrite(text)

    def validate_key(self, key: str) -> bool:
        try:
            pyautogui.press(key, interval=0)
            return True
        except Exception:
            return False
