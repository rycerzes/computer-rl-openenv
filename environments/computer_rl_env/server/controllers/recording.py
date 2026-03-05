from __future__ import annotations

import logging
import signal
import subprocess
import threading
from pathlib import Path

import mss

logger = logging.getLogger(__name__)


class ScreenRecorder:
    def __init__(
        self,
        display: str = ":99",
        output_path: str = "/tmp/computer_rl_recording.mp4",
        fps: int = 30,
    ):
        self.display = display
        self.output_path = output_path
        self.fps = fps
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None

    def _get_screen_size(self) -> tuple[int, int]:
        try:
            with mss.mss() as capture:
                monitors = capture.monitors
                monitor = monitors[1] if len(monitors) > 1 else monitors[0]
                return int(monitor["width"]), int(monitor["height"])
        except Exception as exc:
            logger.warning("Failed to detect screen size, using fallback 1280x960: %s", exc)
            return 1280, 960

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> str:
        with self._lock:
            if self._is_running():
                raise ValueError("Recording is already in progress")

            self._process = None
            output = Path(self.output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            if output.exists():
                output.unlink(missing_ok=True)

            width, height = self._get_screen_size()
            command = [
                "ffmpeg",
                "-y",
                "-video_size",
                f"{width}x{height}",
                "-framerate",
                str(self.fps),
                "-f",
                "x11grab",
                "-draw_mouse",
                "1",
                "-i",
                f"{self.display}.0",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ]

            self._process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )

            try:
                self._process.wait(timeout=2)
                stderr = self._process.stderr.read() if self._process.stderr else ""
                self._process = None
                raise RuntimeError(f"ffmpeg terminated unexpectedly: {stderr}")
            except subprocess.TimeoutExpired:
                return str(output)

    def stop(self) -> str:
        with self._lock:
            if not self._is_running():
                self._process = None
                raise ValueError("No recording in progress to stop")

            process = self._process
            error_output = ""
            try:
                process.send_signal(signal.SIGINT)
                _, error_output = process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                _, error_output = process.communicate()
                self._process = None
                raise RuntimeError(
                    "Recording process was unresponsive and had to be killed. "
                    f"Stderr: {error_output}"
                )
            finally:
                self._process = None

            output = Path(self.output_path)
            if output.exists() and output.stat().st_size > 0:
                return str(output)

            raise RuntimeError(
                f"Recording failed. Output file missing or empty. ffmpeg stderr: {error_output}"
            )

    def cleanup(self) -> None:
        with self._lock:
            if not self._is_running():
                self._process = None
                return

            process = self._process
            try:
                process.send_signal(signal.SIGINT)
                process.communicate(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            finally:
                self._process = None
