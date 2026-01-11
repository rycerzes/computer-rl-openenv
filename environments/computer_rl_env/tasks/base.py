from typing import Literal, Optional, Any, Dict, List
from pydantic import BaseModel, Field

class SetupStep(BaseModel):
    """
    Represents a single step in the task setup process.
    """
    type: Literal["launch", "download", "create_file", "open_url"]
    params: Dict[str, Any]

class EvaluatorConfig(BaseModel):
    """
    Configuration for the task evaluator.
    """
    type: Literal["url_match", "file_exists", "app_launched", "text_present", "process_running"]
    params: Dict[str, Any]
    success_threshold: float = 1.0

class Task(BaseModel):
    """
    Definition of a Computer RL Task.
    """
    id: str
    instruction: str
    category: Literal["browser", "office", "file", "system"]
    difficulty: Literal["easy", "medium", "hard"]
    setup: List[SetupStep] = Field(default_factory=list)
    evaluator: EvaluatorConfig
    max_steps: int = 50
    timeout: int = 60
    reference_solution: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
