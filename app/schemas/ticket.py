from datetime import datetime

from pydantic import BaseModel

from app.models.ticket import TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    title: str
    description: str
    priority: TicketPriority = TicketPriority.medium
    category: str | None = None


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category: str | None = None
    assignee_id: int | None = None
    reopen_reason: str | None = None


class TicketOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    category: str | None
    creator_id: int
    assignee_id: int | None
    reopen_reason: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    is_overdue: bool = False


class TicketFilter(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category: str | None = None
    assignee_id: int | None = None
    search: str | None = None
