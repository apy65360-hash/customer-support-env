from datetime import datetime

from pydantic import BaseModel


class CommentCreate(BaseModel):
    body: str
    is_internal: bool = False


class CommentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    ticket_id: int
    author_id: int
    body: str
    is_internal: bool
    created_at: datetime
