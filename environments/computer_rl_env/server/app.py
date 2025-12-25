from openenv.core.server import create_app as openenv_create_app

from ..models import ComputerAction, ComputerObservation, ComputerState
from .environment import ComputerEnvironment


def main():
    app = create_app(
        environment_class=ComputerEnvironment,
        action_model=ComputerAction,
        observation_model=ComputerObservation,
        state_model=ComputerState,
    )
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


def create_app():
    return openenv_create_app(
        environment_class=ComputerEnvironment,
        action_model=ComputerAction,
        observation_model=ComputerObservation,
        state_model=ComputerState,
    )


__all__ = ["create_app", "main"]
