from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_agent
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate, TicketFilter, TicketOut, TicketUpdate
from app.services import tickets as svc
from app.services import knowledge_base as kb_svc

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _ticket_out(ticket) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    out.is_overdue = svc.is_overdue(ticket)
    return out


@router.post("/", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    data: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = svc.create_ticket(db, data, current_user.id)
    # Suggest KB articles based on title + description
    suggestions = kb_svc.suggest_articles(db, f"{data.title} {data.description}")
    if suggestions:
        for art in suggestions[:3]:
            kb_svc.link_article_to_ticket(db, ticket.id, art.id)
    return _ticket_out(ticket)


@router.get("/", response_model=list[TicketOut])
def list_tickets(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    category: str | None = Query(None),
    assignee_id: int | None = Query(None),
    search: str | None = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = TicketFilter(
        status=status,
        priority=priority,
        category=category,
        assignee_id=assignee_id,
        search=search,
    )
    tickets = svc.list_tickets(db, filters, skip=skip, limit=limit)
    # Customers only see their own tickets
    if current_user.role == UserRole.customer:
        tickets = [t for t in tickets if t.creator_id == current_user.id]
    return [_ticket_out(t) for t in tickets]


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = svc.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if current_user.role == UserRole.customer and ticket.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")
    return _ticket_out(ticket)


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: int,
    data: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = svc.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    # Customers can only edit their own tickets and cannot change assignee
    if current_user.role == UserRole.customer:
        if ticket.creator_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your ticket")
        if data.assignee_id is not None:
            raise HTTPException(status_code=403, detail="Customers cannot reassign tickets")
    try:
        updated = svc.update_ticket(db, ticket, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _ticket_out(updated)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agent),
):
    ticket = svc.get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    svc.delete_ticket(db, ticket)
