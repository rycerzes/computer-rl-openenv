from openenv.core import EnvClient
from openenv.core.client_types import StepResult

from .models import ComputerAction, ComputerObservation, ComputerState


class ComputerEnvClient(EnvClient[ComputerAction, ComputerObservation, ComputerState]):
    def _step_payload(self, action: ComputerAction) -> dict:
        return action.model_dump()

    def _parse_result(self, payload: dict) -> StepResult[ComputerObservation]:
        observation = ComputerObservation(**payload["observation"])
        reward = payload.get("reward", 0.0)
        done = payload.get("done", False)
        return StepResult(
            observation=observation,
            reward=reward,
            done=done,
        )

    def _parse_state(self, payload: dict) -> ComputerState:
        return ComputerState(**payload)
