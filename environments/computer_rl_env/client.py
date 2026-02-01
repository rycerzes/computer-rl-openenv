from openenv.core import EnvClient
from openenv.core.client_types import StepResult

from .models import ComputerAction, ComputerObservation, ComputerState


class ComputerEnvClient(EnvClient[ComputerAction, ComputerObservation, ComputerState]):
    def _step_payload(self, action: ComputerAction) -> dict:
        return action.model_dump()

    def _parse_result(self, payload: dict) -> StepResult[ComputerObservation]:
        # Payload comes from EnvClient.step -> parse_result
        # The payload will structure matches what serialize_observation produces
        # "observation": {...}, "reward": ..., "done": ...

        # We need to construct the Observation object from the dict
        observation_data = payload["observation"]
        observation = ComputerObservation.model_validate(observation_data)

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: dict) -> ComputerState:
        return ComputerState.model_validate(payload)
