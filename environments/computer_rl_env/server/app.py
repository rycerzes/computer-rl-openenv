import base64
import logging
import os
import shlex
import subprocess
from typing import List, Optional

from fastapi.responses import JSONResponse, Response
from openenv.core import create_app as openenv_create_app
from pydantic import BaseModel

from ..models import ComputerAction, ComputerObservation
from .controllers.accessibility import AccessibilityParser
from .controllers.screenshot import ScreenCapture
from .environment import ComputerEnvironment

logger = logging.getLogger(__name__)


# Request Models
class ExecuteRequest(BaseModel):
    command: List[str] | str
    shell: bool = False
    verification: Optional[dict] = None
    max_wait_time: int = 10
    check_interval: int = 1


class LaunchRequest(BaseModel):
    command: List[str] | str
    shell: bool = False


def main():
    app = create_app()
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


def create_app():
    app = openenv_create_app(
        env=ComputerEnvironment,
        action_cls=ComputerAction,
        observation_cls=ComputerObservation,
    )

    @app.post("/setup/launch")
    async def launch_app(request: LaunchRequest):
        cmd = request.command
        if isinstance(cmd, str) and not request.shell:
            cmd = shlex.split(cmd)

        # Expand user
        if isinstance(cmd, list):
            cmd = [os.path.expanduser(arg) if arg.startswith("~/") else arg for arg in cmd]

        try:
            subprocess.Popen(cmd, shell=request.shell, start_new_session=True)
            return {"status": "success", "message": "Launched"}
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    @app.get("/screenshot")
    async def get_screenshot():
        try:
            # Re-use ScreenCapture logic
            capture = ScreenCapture(":99")
            # Returns base64 string
            b64_str = capture.capture()
            img_bytes = base64.b64decode(b64_str)
            return Response(content=img_bytes, media_type="image/png")
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    @app.get("/terminal")
    async def get_terminal_output():
        try:
            parser = AccessibilityParser(max_depth=50, max_width=1024)
            output = parser.get_terminal_output()
            return {"status": "success", "output": output, "exit_code": None}
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    return app


__all__ = ["create_app", "main"]
