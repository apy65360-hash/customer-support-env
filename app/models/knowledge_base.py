from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class KnowledgeBaseArticle(Base):
    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Comma-separated keyword tags for basic keyword matching
    tags: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    author: Mapped["User"] = relationship("User")
    ticket_links: Mapped[list["TicketArticleLink"]] = relationship(
        "TicketArticleLink", back_populates="article", cascade="all, delete-orphan"
    )


class TicketArticleLink(Base):
    """Many-to-many join between tickets and KB articles."""

    __tablename__ = "ticket_article_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("kb_articles.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="kb_links")
    article: Mapped["KnowledgeBaseArticle"] = relationship("KnowledgeBaseArticle", back_populates="ticket_links")
