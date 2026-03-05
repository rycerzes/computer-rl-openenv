from .accessibility import AccessibilityParser
from .recording import ScreenRecorder
from .screenshot import ScreenCapture

__all__ = [
    "KeyboardController",
    "AccessibilityParser",
    "MouseController",
    "ScreenCapture",
    "ScreenRecorder",
]


def __getattr__(name: str):
    if name == "KeyboardController":
        from .keyboard import KeyboardController

        return KeyboardController
    if name == "MouseController":
        from .mouse import MouseController

        return MouseController
    raise AttributeError(name)
