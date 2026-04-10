from datetime import datetime

from pydantic import BaseModel


class ArticleCreate(BaseModel):
    title: str
    body: str
    tags: str | None = None
    category: str | None = None


class ArticleUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: str | None = None
    category: str | None = None


class ArticleOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    body: str
    tags: str | None
    category: str | None
    author_id: int
    created_at: datetime
    updated_at: datetime


class ArticleLinkOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    ticket_id: int
    article_id: int
    created_at: datetime
