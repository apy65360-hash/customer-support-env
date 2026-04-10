from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_agent
from app.models.ticket import SLA_HOURS, Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
def ticket_summary(db: Session = Depends(get_db), _: User = Depends(require_agent)):
    """Open vs resolved counts across all statuses."""
    rows = db.query(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status).all()
    return {status.value: count for status, count in rows}


@router.get("/resolution-time")
def avg_resolution_time(db: Session = Depends(get_db), _: User = Depends(require_agent)):
    """Average resolution time (hours) grouped by category and priority."""
    resolved = (
        db.query(Ticket)
        .filter(Ticket.status == TicketStatus.resolved, Ticket.resolved_at.isnot(None))
        .all()
    )

    buckets: dict[str, list[float]] = {}
    for ticket in resolved:
        key = f"{ticket.category or 'uncategorized'}|{ticket.priority}"
        delta = ticket.resolved_at - ticket.created_at
        hours = delta.total_seconds() / 3600
        buckets.setdefault(key, []).append(hours)

    return {
        key: round(sum(vals) / len(vals), 2)
        for key, vals in buckets.items()
    }


@router.get("/agent-performance")
def agent_performance(db: Session = Depends(get_db), _: User = Depends(require_agent)):
    """Per-agent: tickets resolved and average response time (hours)."""
    agents = db.query(User).filter(User.role.in_([UserRole.agent, UserRole.admin])).all()
    result = []
    for agent in agents:
        resolved_tickets = [
            t for t in agent.assigned_tickets
            if t.status == TicketStatus.resolved and t.resolved_at
        ]
        total = len(resolved_tickets)
        avg_hours = 0.0
        if resolved_tickets:
            avg_hours = sum(
                (t.resolved_at - t.created_at).total_seconds() / 3600
                for t in resolved_tickets
            ) / total

        result.append(
            {
                "agent_id": agent.id,
                "email": agent.email,
                "full_name": agent.full_name,
                "tickets_resolved": total,
                "avg_resolution_hours": round(avg_hours, 2),
            }
        )
    return result


@router.get("/overdue")
def overdue_tickets(db: Session = Depends(get_db), _: User = Depends(require_agent)):
    """List all tickets that have exceeded their SLA threshold."""
    now = datetime.now(timezone.utc)
    open_tickets = (
        db.query(Ticket)
        .filter(Ticket.status.in_([TicketStatus.open, TicketStatus.in_progress]))
        .all()
    )
    overdue = []
    for ticket in open_tickets:
        threshold_hours = SLA_HOURS.get(ticket.priority, 24)
        created = ticket.created_at.replace(tzinfo=timezone.utc)
        age_hours = (now - created).total_seconds() / 3600
        if age_hours > threshold_hours:
            overdue.append(
                {
                    "ticket_id": ticket.id,
                    "title": ticket.title,
                    "priority": ticket.priority,
                    "age_hours": round(age_hours, 2),
                    "sla_hours": threshold_hours,
                    "assignee_id": ticket.assignee_id,
                }
            )
    return overdue
