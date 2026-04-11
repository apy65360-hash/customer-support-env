from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBaseArticle, TicketArticleLink
from app.schemas.knowledge_base import ArticleCreate, ArticleUpdate


def create_article(db: Session, data: ArticleCreate, author_id: int) -> KnowledgeBaseArticle:
    article = KnowledgeBaseArticle(
        title=data.title,
        body=data.body,
        tags=data.tags,
        category=data.category,
        author_id=author_id,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def get_article(db: Session, article_id: int) -> KnowledgeBaseArticle | None:
    return db.query(KnowledgeBaseArticle).filter(KnowledgeBaseArticle.id == article_id).first()


def list_articles(db: Session, skip: int = 0, limit: int = 50) -> list[KnowledgeBaseArticle]:
    return db.query(KnowledgeBaseArticle).offset(skip).limit(limit).all()


def update_article(
    db: Session, article: KnowledgeBaseArticle, data: ArticleUpdate
) -> KnowledgeBaseArticle:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(article, field, value)
    db.commit()
    db.refresh(article)
    return article


def delete_article(db: Session, article: KnowledgeBaseArticle) -> None:
    db.delete(article)
    db.commit()


def suggest_articles(db: Session, text: str, limit: int = 5) -> list[KnowledgeBaseArticle]:
    """Return KB articles whose title, tags, or body contain any word from *text*."""
    words = [w.strip() for w in text.lower().split() if len(w.strip()) > 3]
    if not words:
        return []

    results: dict[int, KnowledgeBaseArticle] = {}
    for word in words:
        term = f"%{word}%"
        rows = (
            db.query(KnowledgeBaseArticle)
            .filter(
                KnowledgeBaseArticle.title.ilike(term)
                | KnowledgeBaseArticle.tags.ilike(term)
                | KnowledgeBaseArticle.body.ilike(term)
            )
            .limit(limit)
            .all()
        )
        for row in rows:
            results[row.id] = row
        if len(results) >= limit:
            break

    return list(results.values())[:limit]


def link_article_to_ticket(db: Session, ticket_id: int, article_id: int) -> TicketArticleLink:
    existing = (
        db.query(TicketArticleLink)
        .filter(TicketArticleLink.ticket_id == ticket_id, TicketArticleLink.article_id == article_id)
        .first()
    )
    if existing:
        return existing
    link = TicketArticleLink(ticket_id=ticket_id, article_id=article_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link
