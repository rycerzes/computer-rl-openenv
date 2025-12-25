import base64
import io

import mss

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ScreenCapture:
    def __init__(self, display: str = ":99"):
        self.display = display
        self.sct = mss.mss()

    def capture(self, quality: int = 85) -> str:
        monitors = self.sct.monitors
        if len(monitors) > 1:
            screen = monitors[1]
        else:
            screen = {"top": 0, "left": 0, "width": 1280, "height": 960}

        screenshot = self.sct.grab(screen)

        if HAS_PIL:
            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        else:
            import mss as m

            img = m.to_png(screenshot.rgb, screenshot.size)
            return base64.b64encode(img).decode("utf-8")
