"""Pydantic models for the OpenEnv API (reset / step / state endpoints)."""
from typing import Any, Optional

from pydantic import BaseModel


class ResetRequest(BaseModel):
    task: str = "create-ticket"


class ActionModel(BaseModel):
    action_type: str
    # create_ticket fields
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    # add_comment / update_status / link_article fields
    ticket_id: Optional[int] = None
    status: Optional[str] = None
    body: Optional[str] = None
    is_internal: bool = False
    # search_kb / link_article fields
    query: Optional[str] = None
    article_id: Optional[int] = None


class StepRequest(BaseModel):
    action: ActionModel


class Observation(BaseModel):
    task: str
    step: int
    done: bool
    instructions: str
    available_actions: list[str]
    state: dict[str, Any]
    last_action_result: Optional[str] = None


class StepResult(BaseModel):
    observation: Observation
    reward: float
    done: bool
    error: Optional[str] = None
    info: dict[str, Any] = {}


class StateResponse(BaseModel):
    task: str
    step: int
    done: bool
    total_reward: float
    rewards: list[float]
    state: dict[str, Any]
