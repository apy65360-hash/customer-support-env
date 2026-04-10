import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ticket import SLA_HOURS, Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate, TicketFilter, TicketUpdate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SLA helpers
# ---------------------------------------------------------------------------

def is_overdue(ticket: Ticket) -> bool:
    """Return True if the ticket has exceeded its SLA threshold."""
    if ticket.status in (TicketStatus.resolved, TicketStatus.closed):
        return False
    threshold_hours = SLA_HOURS.get(ticket.priority, 24)
    age = datetime.now(timezone.utc) - ticket.created_at.replace(tzinfo=timezone.utc)
    return age.total_seconds() / 3600 > threshold_hours


# ---------------------------------------------------------------------------
# Auto-assignment: pick the agent with the fewest open tickets (least-loaded)
# ---------------------------------------------------------------------------

def _least_loaded_agent(db: Session) -> User | None:
    subq = (
        db.query(Ticket.assignee_id, func.count(Ticket.id).label("cnt"))
        .filter(Ticket.status.in_([TicketStatus.open, TicketStatus.in_progress]))
        .filter(Ticket.assignee_id.isnot(None))
        .group_by(Ticket.assignee_id)
        .subquery()
    )
    agent = (
        db.query(User)
        .filter(User.role == UserRole.agent, User.is_active.is_(True))
        .outerjoin(subq, User.id == subq.c.assignee_id)
        .order_by(func.coalesce(subq.c.cnt, 0))
        .first()
    )
    return agent


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_ticket(db: Session, data: TicketCreate, creator_id: int) -> Ticket:
    assignee = _least_loaded_agent(db)
    ticket = Ticket(
        title=data.title,
        description=data.description,
        priority=data.priority,
        category=data.category,
        creator_id=creator_id,
        assignee_id=assignee.id if assignee else None,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    logger.info("Ticket %d created, auto-assigned to agent %s", ticket.id, assignee and assignee.email)
    return ticket


def get_ticket(db: Session, ticket_id: int) -> Ticket | None:
    return db.query(Ticket).filter(Ticket.id == ticket_id).first()


def list_tickets(db: Session, filters: TicketFilter, skip: int = 0, limit: int = 50) -> list[Ticket]:
    q = db.query(Ticket)
    if filters.status:
        q = q.filter(Ticket.status == filters.status)
    if filters.priority:
        q = q.filter(Ticket.priority == filters.priority)
    if filters.category:
        q = q.filter(Ticket.category == filters.category)
    if filters.assignee_id is not None:
        q = q.filter(Ticket.assignee_id == filters.assignee_id)
    if filters.search:
        term = f"%{filters.search}%"
        q = q.filter(Ticket.title.ilike(term) | Ticket.description.ilike(term))
    return q.order_by(Ticket.created_at.desc()).offset(skip).limit(limit).all()


# ---------------------------------------------------------------------------
# Status-transition rules
# ---------------------------------------------------------------------------

_ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.open: {TicketStatus.in_progress, TicketStatus.closed},
    TicketStatus.in_progress: {TicketStatus.resolved, TicketStatus.open, TicketStatus.closed},
    TicketStatus.resolved: {TicketStatus.closed, TicketStatus.open},
    TicketStatus.closed: {TicketStatus.open},  # requires reopen_reason
}


def _validate_transition(current: TicketStatus, target: TicketStatus, reopen_reason: str | None) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(f"Cannot transition from '{current}' to '{target}'")
    if current == TicketStatus.closed and target == TicketStatus.open and not reopen_reason:
        raise ValueError("A reopen_reason is required when reopening a closed ticket")


def update_ticket(db: Session, ticket: Ticket, data: TicketUpdate) -> Ticket:
    update_data = data.model_dump(exclude_unset=True)

    new_status = update_data.get("status")
    if new_status and new_status != ticket.status:
        _validate_transition(ticket.status, new_status, update_data.get("reopen_reason"))

    for field, value in update_data.items():
        setattr(ticket, field, value)

    ticket.updated_at = datetime.now(timezone.utc)

    if new_status == TicketStatus.resolved and ticket.resolved_at is None:
        ticket.resolved_at = datetime.now(timezone.utc)
    elif new_status and new_status != TicketStatus.resolved:
        # Clear resolved_at if moving away from resolved
        ticket.resolved_at = None

    db.commit()
    db.refresh(ticket)
    return ticket


def delete_ticket(db: Session, ticket: Ticket) -> None:
    db.delete(ticket)
    db.commit()
