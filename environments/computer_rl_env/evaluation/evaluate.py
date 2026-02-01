import concurrent.futures
import logging
import time
import traceback
from typing import Any, Dict, List

from ..server.environment import ComputerEnvironment
from ..tasks.base import Task
from .metrics import (
    compute_category_breakdown,
    compute_efficiency_score,
    compute_success_rate,
)

logger = logging.getLogger(__name__)


class Evaluator:
    """
    Evaluates agents on a set of tasks using ComputerEnvironment.
    """

    def __init__(self, task_set: List[Task], max_workers: int = 1):
        """
        Initialize the Evaluator.

        Args:
            task_set: List of Task objects to evaluate on.
            max_workers: Number of parallel workers (default 1).
                         Note: Parallelism requires careful display management.
        """
        self.task_set = task_set
        self.max_workers = max_workers

    def evaluate_agent(self, agent: Any, episodes_per_task: int = 1) -> Dict[str, Any]:
        """
        Evaluate an agent across the entire task set.

        Args:
            agent: The agent instance to evaluate. Must accept (instruction, obs) and return (response, actions).
            episodes_per_task: Number of times to run each task (default 1).

        Returns:
            Dict containing aggregated results and metrics.
        """
        all_results = []

        # Prepare all evaluation jobs
        jobs = []
        for task in self.task_set:
            for i in range(episodes_per_task):
                jobs.append((task, i))

        logger.info(f"Starting evaluation of {len(jobs)} episodes with {self.max_workers} workers.")

        if self.max_workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_job = {
                    executor.submit(self.evaluate_single_task, agent, task, episode_idx=i): (
                        task,
                        i,
                    )
                    for task, i in jobs
                }

                for future in concurrent.futures.as_completed(future_to_job):
                    task, i = future_to_job[future]
                    try:
                        result = future.result()
                        all_results.append(result)
                        logger.info(
                            f"Task {task.id} (Episode {i}) completed: success={result['success']}"
                        )
                    except Exception as e:
                        logger.error(f"Task {task.id} (Episode {i}) generated an exception: {e}")
                        traceback.print_exc()
                        all_results.append(
                            {
                                "task_id": task.id,
                                "episode_idx": i,
                                "success": False,
                                "error": str(e),
                            }
                        )
        else:
            for task, i in jobs:
                try:
                    result = self.evaluate_single_task(agent, task, episode_idx=i)
                    all_results.append(result)
                    logger.info(
                        f"Task {task.id} (Episode {i}) completed: success={result['success']}"
                    )
                except Exception as e:
                    logger.error(f"Task {task.id} (Episode {i}) generated an exception: {e}")
                    traceback.print_exc()
                    all_results.append(
                        {"task_id": task.id, "episode_idx": i, "success": False, "error": str(e)}
                    )

        metrics = {
            "total_episodes": len(all_results),
            "success_rate": compute_success_rate(all_results),
            "efficiency": compute_efficiency_score(all_results),
            "category_breakdown": compute_category_breakdown(all_results),
            "results": all_results,
        }

        return metrics

    def evaluate_single_task(self, agent: Any, task: Task, episode_idx: int = 0) -> Dict[str, Any]:
        """
        Run a single episode for a task.
        """
        env = ComputerEnvironment(display=":99")

        try:
            task_config = {
                "id": task.id,
                "instruction": task.instruction,
                "config": [step.model_dump() for step in task.config],
                "setup": [],
                "evaluator": task.evaluator.model_dump(),
                "max_steps": task.max_steps,
                "timeout": task.timeout,
                "metadata": task.metadata,
                "proxy": task.proxy,
            }

            obs = env.reset(task_config=task_config, episode_id=f"{task.id}_{episode_idx}")

            done = False
            step_count = 0
            start_time = time.time()

            while not done and step_count < task.max_steps:
                try:
                    if hasattr(agent, "predict"):
                        response, actions = agent.predict(task.instruction, obs)

                        if isinstance(actions, list):
                            for action in actions:
                                if done:
                                    break
                                obs = env.step(action)
                                step_count += 1
                                if getattr(obs, "done", False):
                                    done = True
                        else:
                            obs = env.step(actions)
                            step_count += 1
                            if getattr(obs, "done", False):
                                done = True

                    elif hasattr(agent, "act"):
                        action = agent.act(obs)
                        obs = env.step(action)
                        step_count += 1
                        if getattr(obs, "done", False):
                            done = True
                    else:
                        raise ValueError("Agent must implement predict() or act() method")

                except Exception as e:
                    logger.error(f"Error during agent step: {e}")
                    traceback.print_exc()
                    break

            elapsed_time = time.time() - start_time
            success = env._evaluate_task_success()

            return {
                "task_id": task.id,
                "episode_idx": episode_idx,
                "success": success,
                "step_count": step_count,
                "elapsed_time": elapsed_time,
                "category": task.category or "unknown",
                "metadata": task.metadata,
            }

        finally:
            pass
