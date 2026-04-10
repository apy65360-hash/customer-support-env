from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_agent
from app.models.user import User
from app.schemas.knowledge_base import ArticleCreate, ArticleOut, ArticleLinkOut, ArticleUpdate
from app.services import knowledge_base as svc
from app.services import tickets as ticket_svc

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.post("/articles", response_model=ArticleOut, status_code=status.HTTP_201_CREATED)
def create_article(
    data: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agent),
):
    return svc.create_article(db, data, current_user.id)


@router.get("/articles", response_model=list[ArticleOut])
def list_articles(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.list_articles(db, skip=skip, limit=limit)


@router.get("/articles/suggest", response_model=list[ArticleOut])
def suggest(
    text: str = Query(..., description="Ticket title + description text for keyword matching"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.suggest_articles(db, text)


@router.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    article = svc.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.patch("/articles/{article_id}", response_model=ArticleOut)
def update_article(
    article_id: int,
    data: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agent),
):
    article = svc.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return svc.update_article(db, article, data)


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agent),
):
    article = svc.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    svc.delete_article(db, article)


@router.post("/tickets/{ticket_id}/link/{article_id}", response_model=ArticleLinkOut)
def link_article(
    ticket_id: int,
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agent),
):
    ticket = ticket_svc.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    article = svc.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return svc.link_article_to_ticket(db, ticket_id, article_id)
