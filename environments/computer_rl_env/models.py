from typing import Annotated, Literal, Optional, Union

from openenv.core import Action, Observation, State
from pydantic import BaseModel, Field


class MouseMove(BaseModel):
    action_type: Literal["move"] = "move"
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)


class Click(BaseModel):
    action_type: Literal["click"] = "click"
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)
    button: Literal["left", "right", "middle"] = "left"
    num_clicks: Literal[1, 2] = 1


class TypeText(BaseModel):
    action_type: Literal["type"] = "type"
    text: str


class PressKey(BaseModel):
    action_type: Literal["press"] = "press"
    key: str


class HotKey(BaseModel):
    action_type: Literal["hotkey"] = "hotkey"
    keys: list[str] = Field(min_length=1)


class Scroll(BaseModel):
    action_type: Literal["scroll"] = "scroll"
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)
    direction: Literal["up", "down"] = "up"
    amount: int = Field(ge=1, le=10, default=1)


class Drag(BaseModel):
    action_type: Literal["drag"] = "drag"
    x1: int = Field(ge=0, le=1000)
    y1: int = Field(ge=0, le=1000)
    x2: int = Field(ge=0, le=1000)
    y2: int = Field(ge=0, le=1000)


class Wait(BaseModel):
    action_type: Literal["wait"] = "wait"
    seconds: float = Field(ge=0, le=10)


class Done(BaseModel):
    action_type: Literal["done"] = "done"


ComputerActionVariant = Annotated[
    Union[MouseMove, Click, TypeText, PressKey, HotKey, Scroll, Drag, Wait, Done],
    Field(discriminator="action_type"),
]


class ComputerAction(Action):
    """
    Action for the Computer Environment.
    Wraps the specific action variant to comply with OpenEnv Action schema.
    """
    action: ComputerActionVariant


class ComputerObservation(Observation):
    screenshot_base64: str
    screenshot_resolution: tuple[int, int] = (1280, 960)
    accessibility_tree: Optional[str] = None
    accessibility_tree_format: Literal["flat", "tree"] = "flat"
    terminal_output: Optional[str] = None
    terminal_exit_code: Optional[int] = None
    active_window: Optional[str] = None
    active_app: Optional[str] = None
    step_count: int = 0
    instruction: Optional[str] = None
    task_metadata: dict = Field(default_factory=dict)


class ComputerState(State):
    current_task: Optional[dict] = None
    display: str = ":99"
    max_steps: int = 100
    timeout: int = 60
    # step_count and episode_id are inherited from State
