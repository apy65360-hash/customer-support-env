"""FastAPI router exposing the OpenEnv API at /reset, /step, /state."""
from fastapi import APIRouter

from .env import TASK_NAMES, do_reset, do_state, do_step
from .models import (
    Observation,
    ResetRequest,
    StateResponse,
    StepRequest,
    StepResult,
)

router = APIRouter(tags=["openenv"])


@router.post("/reset", response_model=Observation, summary="Reset environment episode")
def reset(body: ResetRequest = ResetRequest()) -> Observation:
    """Reset the environment to an initial state for the given task.

    - **task**: one of ``create-ticket``, ``resolve-ticket``, ``full-workflow``
      (defaults to ``create-ticket`` when omitted).

    Returns the initial ``Observation``.
    """
    return do_reset(body.task)


@router.post("/step", response_model=StepResult, summary="Take one environment step")
def step(body: StepRequest) -> StepResult:
    """Execute one action and return the resulting observation + reward.

    Call ``POST /reset`` first; repeated calls after the episode is ``done``
    return ``reward=0`` until a new reset is issued.
    """
    return do_step(body.action)


@router.get("/state", response_model=StateResponse, summary="Inspect current state")
def state() -> StateResponse:
    """Return the current episode state without advancing the environment."""
    return do_state()


@router.get("/tasks", summary="List available tasks")
def list_tasks() -> dict:
    """Return the names of all available tasks."""
    return {"tasks": TASK_NAMES}
