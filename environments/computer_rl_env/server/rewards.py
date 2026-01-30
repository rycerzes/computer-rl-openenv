from typing import TYPE_CHECKING

from ..models import ComputerObservation

if TYPE_CHECKING:
    pass


class RewardComputer:
    def __init__(self, config: dict):
        self.mode = config.get("mode", "sparse")

    def compute(
        self,
        success: bool,
        step_count: int,
        prev_obs: ComputerObservation | None = None,
        curr_obs: ComputerObservation | None = None,
    ) -> float:
        if self.mode == "sparse":
            return self.compute_sparse(success, step_count)
        elif self.mode == "shaped":
            return self.compute_shaped(success, step_count, prev_obs, curr_obs)
        return self.compute_sparse(success, step_count)

    def compute_sparse(self, success: bool, step_count: int) -> float:
        reward = 1.0 if success else 0.0
        step_penalty = 0.01 * step_count
        reward -= step_penalty
        return max(-1.0, min(1.0, reward))

    def compute_shaped(
        self,
        success: bool,
        step_count: int,
        prev_obs: ComputerObservation | None,
        curr_obs: ComputerObservation | None,
    ) -> float:
        reward = 1.0 if success else 0.0
        step_penalty = 0.01 * step_count
        reward -= step_penalty

        if prev_obs and curr_obs:
            progress_reward = self.compute_progress_reward(prev_obs, curr_obs)
            reward += progress_reward

        return max(-1.0, min(1.0, reward))

    def compute_progress_reward(
        self, prev_obs: ComputerObservation, curr_obs: ComputerObservation
    ) -> float:
        progress = 0.0

        if prev_obs.accessibility_tree != curr_obs.accessibility_tree:
            progress += 0.05

        if prev_obs.active_window != curr_obs.active_window:
            if curr_obs.active_window:
                progress += 0.1

        if prev_obs.active_app != curr_obs.active_app:
            if curr_obs.active_app:
                progress += 0.1

        return min(0.3, progress)
