import base64
import io

import mss
from mss import tools

try:
    from PIL import Image, ImageDraw

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


import threading


class ScreenCapture:
    def __init__(self, display: str = ":99"):
        self.display = display
        self._local = threading.local()

    def capture(self, quality: int = 85, include_cursor: bool = True) -> str:
        if not hasattr(self._local, "sct"):
            self._local.sct = mss.mss()

        monitors = self._local.sct.monitors
        if len(monitors) > 1:
            screen = monitors[1]
        else:
            screen = {"top": 0, "left": 0, "width": 1280, "height": 960}

        screenshot = self._local.sct.grab(screen)

        if HAS_PIL:
            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)  # pyright: ignore[reportPossiblyUnboundVariable]
            if include_cursor:
                try:
                    import pyautogui

                    cursor_x, cursor_y = pyautogui.position()
                    rel_x = int(cursor_x - screen["left"])
                    rel_y = int(cursor_y - screen["top"])
                    if 0 <= rel_x < screen["width"] and 0 <= rel_y < screen["height"]:
                        draw = ImageDraw.Draw(img)
                        radius = 7
                        draw.ellipse(
                            (rel_x - radius, rel_y - radius, rel_x + radius, rel_y + radius),
                            outline=(255, 64, 64),
                            width=2,
                        )
                        cross = 10
                        draw.line(
                            (rel_x - cross, rel_y, rel_x + cross, rel_y),
                            fill=(255, 64, 64),
                            width=2,
                        )
                        draw.line(
                            (rel_x, rel_y - cross, rel_x, rel_y + cross),
                            fill=(255, 64, 64),
                            width=2,
                        )
                except Exception:
                    pass
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        else:
            img = tools.to_png(screenshot.rgb, screenshot.size) or b""
            return base64.b64encode(img).decode("utf-8")
