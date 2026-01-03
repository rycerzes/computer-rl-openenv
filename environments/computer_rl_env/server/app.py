from openenv.core import create_app as openenv_create_app

from ..models import ComputerAction, ComputerObservation, ComputerState
from .environment import ComputerEnvironment


def main():
    app = create_app()
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


def create_app():
    return openenv_create_app(
        env=ComputerEnvironment,
        action_cls=ComputerAction,  # type: ignore[arg-type]
        observation_cls=ComputerObservation,
    )


__all__ = ["create_app", "main"]
