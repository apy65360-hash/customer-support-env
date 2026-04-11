from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.schemas.comment import CommentCreate, CommentOut
from app.models.comment import Comment
from app.services import tickets as ticket_svc
from app.services.notifications import notify_new_comment

router = APIRouter(prefix="/tickets/{ticket_id}/comments", tags=["comments"])


@router.post("/", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    ticket_id: int,
    data: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_svc.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Only agents/admins can post internal notes
    if data.is_internal and current_user.role == UserRole.customer:
        raise HTTPException(status_code=403, detail="Customers cannot post internal notes")

    # Customers can only comment on their own tickets
    if current_user.role == UserRole.customer and ticket.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")

    comment = Comment(
        ticket_id=ticket_id,
        author_id=current_user.id,
        body=data.body,
        is_internal=data.is_internal,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    # Notify the other party (agent → customer or customer → assignee)
    try:
        if current_user.role == UserRole.customer and ticket.assignee:
            notify_new_comment(ticket_id, current_user.full_name, ticket.assignee.email)
        elif current_user.role in (UserRole.agent, UserRole.admin):
            notify_new_comment(ticket_id, current_user.full_name, ticket.creator.email)
    except Exception:
        pass  # Never let notification errors break the response

    return comment


@router.get("/", response_model=list[CommentOut])
def list_comments(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_svc.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if current_user.role == UserRole.customer and ticket.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")

    comments = (
        db.query(Comment)
        .filter(Comment.ticket_id == ticket_id)
        .order_by(Comment.created_at)
        .all()
    )
    # Strip internal notes from customer view
    if current_user.role == UserRole.customer:
        comments = [c for c in comments if not c.is_internal]
    return comments
