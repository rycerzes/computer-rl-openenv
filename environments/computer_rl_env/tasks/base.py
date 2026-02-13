from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvaluatorConfig(BaseModel):
    """
    Configuration for the task evaluator, matching full OSWorld schema.

    Supports single and multi-metric evaluation with conjunction logic.
    """

    model_config = ConfigDict(extra="allow")

    func: Union[str, List[str]]  # e.g., "match_in_list", ["compare_csv", "compare_table"]
    result: Union[Dict[str, Any], List[Dict[str, Any]], None] = None
    expected: Any = None  # Can be raw value, dict (getter config), or list
    postconfig: List[Dict[str, Any]] = Field(default_factory=list)
    conj: str = "and"  # Conjunction mode: "and" or "or"
    options: Union[Dict[str, Any], List[Dict[str, Any]], None] = None


class Task(BaseModel):
    """
    Definition of a Computer RL Task, matching OSWorld JSON schema.

    This is the single unified task model used throughout the system:
    - TaskLoader loads JSON/YAML into Task objects
    - TaskManager.setup() and evaluate() accept Task objects
    - ComputerEnvironment stores the current Task
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    snapshot: str = ""  # e.g., "chrome", "ubuntu"
    instruction: str
    source: Optional[str] = None
    config: List[Dict[str, Any]] = Field(default_factory=list)
    setup: List[Dict[str, Any]] = Field(default_factory=list)
    trajectory: Optional[str] = None
    related_apps: List[str] = Field(default_factory=list)
    evaluator: EvaluatorConfig
    proxy: bool = False
    fixed_ip: bool = False

    # Optional metadata fields
    category: Optional[str] = None
    difficulty: Optional[str] = None
    max_steps: int = 50
    timeout: int = 60
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_evaluator(cls, data: Any) -> Any:
        """Convert raw dict evaluator to EvaluatorConfig if needed."""
        if isinstance(data, dict) and "evaluator" in data:
            ev = data["evaluator"]
            if isinstance(ev, dict):
                data["evaluator"] = EvaluatorConfig(**ev)
        return data
