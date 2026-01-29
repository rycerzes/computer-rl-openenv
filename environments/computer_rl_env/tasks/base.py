from typing import Literal, Optional, Any, Dict, List, Union
from pydantic import BaseModel, Field

class ConfigStep(BaseModel):
    """
    Represents a single step in the task configuration/setup process.
    """
    type: str # e.g., "launch", "sleep", "execute"
    parameters: Dict[str, Any] = Field(default_factory=dict)

class EvaluatorConfig(BaseModel):
    """
    Configuration for the task evaluator, matching OSWorld schema.
    """
    func: Union[str, List[str]] # e.g., "match_in_list", "check_file"
    result: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(default_factory=dict)
    expected: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(default_factory=dict)
    postconfig: List[ConfigStep] = Field(default_factory=list)

class Task(BaseModel):
    """
    Definition of a Computer RL Task, matching OSWorld JSON schema.
    """
    id: str
    snapshot: str # e.g., "chrome", "ubuntu"
    instruction: str
    source: Optional[str] = None
    config: List[ConfigStep] = Field(default_factory=list)
    trajectory: Optional[str] = None
    related_apps: List[str] = Field(default_factory=list)
    evaluator: EvaluatorConfig
    proxy: bool = False
    fixed_ip: bool = False
    
    # Optional metadata fields that might not be in every OSWorld JSON but are useful
    category: Optional[str] = None
    difficulty: Optional[str] = None
    max_steps: int = 50
    timeout: int = 60
    metadata: Dict[str, Any] = Field(default_factory=dict)
