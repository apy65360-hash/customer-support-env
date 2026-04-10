"""Core OpenEnv environment logic.

Three tasks, all backed by a dedicated SQLite database that is wiped on every
reset() call so each episode starts from a clean, reproducible state.

Task difficulty / reward overview
──────────────────────────────────
create-ticket  (easy,   max 10 steps)  – create a well-formed ticket; 0.25 per
                                          quality dimension (title / desc /
                                          priority / category) → max 1.0

resolve-ticket (medium, max 15 steps)  – guide an open ticket to resolved;
                                          0.25 per workflow stage → max 1.0

full-workflow  (hard,   max 20 steps)  – create + comment + KB link +
                                          in_progress + resolved + closed;
                                          weighted partial credits → max 1.0
"""
import threading
from typing import Any, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.database import Base
from app.models.comment import Comment
from app.models.knowledge_base import KnowledgeBaseArticle, TicketArticleLink
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import User, UserRole
from app.services.auth import create_access_token, hash_password

from .models import ActionModel, Observation, StateResponse, StepResult

# ── DB for OpenEnv (isolated from the main app DB) ───────────────────────────
_OPENENV_DB_URL = "sqlite:///./openenv_session.db"
_engine = create_engine(_OPENENV_DB_URL, connect_args={"check_same_thread": False})
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

_lock = threading.Lock()

# ── Task metadata ─────────────────────────────────────────────────────────────
TASK_NAMES = ["create-ticket", "resolve-ticket", "full-workflow"]

_TASK_META: dict[str, dict] = {
    "create-ticket":  {"max_steps": 10, "difficulty": "easy"},
    "resolve-ticket": {"max_steps": 15, "difficulty": "medium"},
    "full-workflow":  {"max_steps": 20, "difficulty": "hard"},
}

_TASK_INSTRUCTIONS: dict[str, str] = {
    "create-ticket": (
        "Create a high-quality support ticket using action_type='create_ticket'. "
        "Required fields: title (≥10 chars), description (≥20 chars), "
        "priority (low|medium|high|urgent), category (non-empty string). "
        'Example: {"action_type":"create_ticket","title":"Cannot log in to account",'
        '"description":"I have been unable to log in for two days despite resetting my password.",'
        '"priority":"high","category":"account-access"}'
    ),
    "resolve-ticket": (
        "A support ticket is pre-created and open. You are the assigned agent. "
        "Follow this exact workflow for full marks: "
        "1) add_comment to acknowledge the issue, "
        "2) update_status to 'in_progress', "
        "3) add_comment with a resolution explanation, "
        "4) update_status to 'resolved'. "
        'add_comment: {"action_type":"add_comment","ticket_id":<id>,"body":"<text>"}. '
        'update_status: {"action_type":"update_status","ticket_id":<id>,"status":"in_progress|resolved"}.'
    ),
    "full-workflow": (
        "Complete an end-to-end support workflow for full marks: "
        "1) create_ticket (title, description, priority, category), "
        "2) add_comment (ticket_id, body), "
        "3) search_kb (query) to find relevant articles, "
        "4) link_article (ticket_id, article_id from search results), "
        "5) update_status to 'in_progress', "
        "6) update_status to 'resolved', "
        "7) update_status to 'closed'. "
        'search_kb: {"action_type":"search_kb","query":"<text>"}. '
        'link_article: {"action_type":"link_article","ticket_id":<id>,"article_id":<id>}. '
        "noop: {\"action_type\":\"noop\"} (no reward)."
    ),
}

_AVAILABLE_ACTIONS: dict[str, list[str]] = {
    "create-ticket": [
        "create_ticket(title, description, priority, category)",
    ],
    "resolve-ticket": [
        "add_comment(ticket_id, body)",
        "update_status(ticket_id, status: in_progress|resolved)",
    ],
    "full-workflow": [
        "create_ticket(title, description, priority, category)",
        "add_comment(ticket_id, body)",
        "search_kb(query)",
        "link_article(ticket_id, article_id)",
        "update_status(ticket_id, status: in_progress|resolved|closed)",
        "noop()",
    ],
}

# Reward flags and their weight per task
_REWARD_WEIGHTS: dict[str, dict[str, float]] = {
    "create-ticket": {
        "has_title":       0.25,
        "has_description": 0.25,
        "has_priority":    0.25,
        "has_category":    0.25,
    },
    "resolve-ticket": {
        "comment_added":        0.25,
        "moved_in_progress":    0.25,
        "resolution_comment":   0.25,
        "moved_resolved":       0.25,
    },
    "full-workflow": {
        "ticket_created":    0.15,
        "comment_added":     0.15,
        "kb_searched":       0.10,
        "article_linked":    0.15,
        "moved_in_progress": 0.10,
        "moved_resolved":    0.15,
        "ticket_closed":     0.20,
    },
}

_VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


# ── Global episode state (singleton, thread-safe via _lock) ──────────────────
class _EpisodeState:
    def __init__(self) -> None:
        self._init()

    def _init(self) -> None:
        self.task: str = "create-ticket"
        self.step: int = 0
        self.done: bool = True   # needs reset before first use
        self.rewards: list[float] = []
        self.earned: dict[str, bool] = {}  # reward flags already awarded
        self.customer_id: int = 0
        self.agent_id: int = 0
        self.customer_token: str = ""
        self.agent_token: str = ""
        self.ticket_id: Optional[int] = None
        self.kb_article_ids: list[int] = []
        self.search_results: list[dict] = []
        self.last_action_result: Optional[str] = None
        self.comment_count: int = 0        # total comments added so far


_state = _EpisodeState()


# ── DB helpers ────────────────────────────────────────────────────────────────

def _new_session() -> Session:
    return _SessionLocal()


def _seed(task: str) -> None:
    """Wipe and re-seed the OpenEnv DB for the given task."""
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)

    db = _new_session()
    try:
        customer = User(
            email="customer@env.test",
            full_name="Alice Customer",
            hashed_password=hash_password("secret"),
            role=UserRole.customer,
        )
        agent = User(
            email="agent@env.test",
            full_name="Bob Agent",
            hashed_password=hash_password("secret"),
            role=UserRole.agent,
        )
        db.add_all([customer, agent])
        db.commit()
        db.refresh(customer)
        db.refresh(agent)

        _state.customer_id = customer.id
        _state.agent_id = agent.id
        _state.customer_token = create_access_token(customer.id)
        _state.agent_token = create_access_token(agent.id)

        if task == "resolve-ticket":
            ticket = Ticket(
                title="Cannot access my account after password reset",
                description=(
                    "I reset my password but still cannot log in. "
                    "I have tried multiple times and cleared my browser cache."
                ),
                status=TicketStatus.open,
                priority=TicketPriority.high,
                category="account-access",
                creator_id=customer.id,
                assignee_id=agent.id,
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            _state.ticket_id = ticket.id

        elif task == "full-workflow":
            articles = [
                KnowledgeBaseArticle(
                    title="Password Reset Guide",
                    body=(
                        "To reset your password, go to the login page and click "
                        "'Forgot Password'. Enter your email and follow the link sent."
                    ),
                    tags="password,reset,login,account",
                    category="account",
                    author_id=agent.id,
                ),
                KnowledgeBaseArticle(
                    title="Billing FAQ",
                    body=(
                        "Common billing questions: How do I update my payment method? "
                        "Go to Account Settings > Billing. "
                        "When will I be charged? At the start of each billing cycle."
                    ),
                    tags="billing,payment,invoice,charge",
                    category="billing",
                    author_id=agent.id,
                ),
                KnowledgeBaseArticle(
                    title="Technical Troubleshooting",
                    body=(
                        "For technical issues: 1. Clear browser cache. "
                        "2. Try incognito mode. 3. Check your internet connection. "
                        "4. Disable browser extensions."
                    ),
                    tags="technical,troubleshoot,browser,cache,error",
                    category="technical",
                    author_id=agent.id,
                ),
            ]
            db.add_all(articles)
            db.commit()
            for a in articles:
                db.refresh(a)
            _state.kb_article_ids = [a.id for a in articles]
            _state.ticket_id = None
    finally:
        db.close()


def _snapshot() -> dict[str, Any]:
    """Return a JSON-serialisable snapshot of the current DB state."""
    db = _new_session()
    try:
        task = _state.task

        if task == "create-ticket":
            tickets = db.query(Ticket).filter(Ticket.creator_id == _state.customer_id).all()
            return {
                "tickets": [
                    {"id": t.id, "title": t.title,
                     "status": t.status, "priority": t.priority}
                    for t in tickets
                ],
            }

        if task == "resolve-ticket":
            ticket = (
                db.query(Ticket).filter(Ticket.id == _state.ticket_id).first()
                if _state.ticket_id else None
            )
            comments = (
                db.query(Comment).filter(Comment.ticket_id == _state.ticket_id).all()
                if _state.ticket_id else []
            )
            return {
                "ticket": {
                    "id": ticket.id,
                    "title": ticket.title,
                    "description": ticket.description,
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "category": ticket.category,
                } if ticket else None,
                "comments": [
                    {"id": c.id, "body": c.body} for c in comments
                ],
            }

        # full-workflow
        articles = [
            db.query(KnowledgeBaseArticle).filter(KnowledgeBaseArticle.id == aid).first()
            for aid in _state.kb_article_ids
        ]
        current_ticket = None
        comments: list[dict] = []
        linked: list[dict] = []
        if _state.ticket_id:
            t = db.query(Ticket).filter(Ticket.id == _state.ticket_id).first()
            if t:
                current_ticket = {
                    "id": t.id, "title": t.title,
                    "status": t.status, "priority": t.priority,
                    "category": t.category,
                }
                comments = [
                    {"id": c.id, "body": c.body}
                    for c in db.query(Comment).filter(Comment.ticket_id == t.id).all()
                ]
                linked = [
                    {"article_id": lnk.article_id}
                    for lnk in db.query(TicketArticleLink)
                    .filter(TicketArticleLink.ticket_id == t.id).all()
                ]
        return {
            "kb_articles": [
                {"id": a.id, "title": a.title, "tags": a.tags}
                for a in articles if a
            ],
            "current_ticket": current_ticket,
            "ticket_comments": comments,
            "linked_articles": linked,
            "search_results": _state.search_results,
        }
    finally:
        db.close()


# ── Action executors ──────────────────────────────────────────────────────────

def _earn(flag: str) -> float:
    """Award a reward flag (idempotent). Returns the reward delta."""
    if _state.earned.get(flag):
        return 0.0
    weight = _REWARD_WEIGHTS[_state.task].get(flag, 0.0)
    _state.earned[flag] = True
    return weight


def _exec_create_ticket(db: Session, action: ActionModel) -> tuple[float, str]:
    task = _state.task
    title = (action.title or "").strip()
    desc = (action.description or "").strip()
    prio = (action.priority or "").strip().lower()
    cat = (action.category or "").strip()
    reward = 0.0

    if task == "create-ticket":
        if len(title) >= 10:
            reward += _earn("has_title")
        if len(desc) >= 20:
            reward += _earn("has_description")
        if prio in _VALID_PRIORITIES:
            reward += _earn("has_priority")
        if cat:
            reward += _earn("has_category")
        # Mark done once all four quality flags earned
        if all(_state.earned.get(f) for f in _REWARD_WEIGHTS["create-ticket"]):
            _state.done = True
    elif task == "full-workflow":
        if title and desc and not _state.earned.get("ticket_created"):
            reward += _earn("ticket_created")

    if not (title and desc):
        return reward, "create_ticket failed: 'title' and 'description' are required."

    resolved_prio = TicketPriority(prio) if prio in _VALID_PRIORITIES else TicketPriority.medium
    ticket = Ticket(
        title=title,
        description=desc,
        priority=resolved_prio,
        category=cat or None,
        status=TicketStatus.open,
        creator_id=_state.customer_id,
        assignee_id=_state.agent_id,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    _state.ticket_id = ticket.id
    return reward, f"Ticket #{ticket.id} created: '{title[:50]}'"


def _exec_add_comment(db: Session, action: ActionModel) -> tuple[float, str]:
    task = _state.task
    tid = action.ticket_id or _state.ticket_id
    body = (action.body or "").strip()

    if not tid:
        return 0.0, "add_comment failed: ticket_id required."
    if not body:
        return 0.0, "add_comment failed: body is required."

    ticket = db.query(Ticket).filter(Ticket.id == tid).first()
    if not ticket:
        return 0.0, f"add_comment failed: ticket #{tid} not found."

    comment = Comment(
        ticket_id=tid,
        author_id=_state.agent_id,
        body=body,
        is_internal=action.is_internal,
    )
    db.add(comment)
    db.commit()
    _state.comment_count += 1
    reward = 0.0

    if task == "resolve-ticket":
        if _state.comment_count == 1:
            reward += _earn("comment_added")
        elif _state.comment_count >= 2 and _state.earned.get("moved_in_progress"):
            reward += _earn("resolution_comment")
    elif task == "full-workflow":
        reward += _earn("comment_added")

    return reward, f"Comment added to ticket #{tid}."


def _exec_update_status(db: Session, action: ActionModel) -> tuple[float, str]:
    task = _state.task
    tid = action.ticket_id or _state.ticket_id
    new_status_raw = (action.status or "").strip().lower()

    if not tid:
        return 0.0, "update_status failed: ticket_id required."
    if not new_status_raw:
        return 0.0, "update_status failed: status required."

    try:
        new_status = TicketStatus(new_status_raw)
    except ValueError:
        return 0.0, f"update_status failed: invalid status '{new_status_raw}'."

    ticket = db.query(Ticket).filter(Ticket.id == tid).first()
    if not ticket:
        return 0.0, f"update_status failed: ticket #{tid} not found."

    _ALLOWED: dict[TicketStatus, set[TicketStatus]] = {
        TicketStatus.open:        {TicketStatus.in_progress, TicketStatus.closed},
        TicketStatus.in_progress: {TicketStatus.resolved, TicketStatus.open, TicketStatus.closed},
        TicketStatus.resolved:    {TicketStatus.closed, TicketStatus.open},
        TicketStatus.closed:      {TicketStatus.open},
    }
    if new_status not in _ALLOWED.get(ticket.status, set()):
        return 0.0, (
            f"update_status failed: cannot transition from '{ticket.status}' to '{new_status}'."
        )

    ticket.status = new_status
    db.commit()
    reward = 0.0

    if task == "resolve-ticket":
        if new_status == TicketStatus.in_progress:
            reward += _earn("moved_in_progress")
        elif new_status == TicketStatus.resolved:
            reward += _earn("moved_resolved")
            _state.done = True
    elif task == "full-workflow":
        if new_status == TicketStatus.in_progress:
            reward += _earn("moved_in_progress")
        elif new_status == TicketStatus.resolved:
            reward += _earn("moved_resolved")
        elif new_status == TicketStatus.closed:
            reward += _earn("ticket_closed")
            _state.done = True

    return reward, f"Ticket #{tid} status → '{new_status}'."


def _exec_search_kb(db: Session, action: ActionModel) -> tuple[float, str]:
    query = (action.query or "").strip()
    if not query:
        return 0.0, "search_kb failed: query is required."

    words = [w for w in query.lower().split() if len(w) > 2]
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
            .limit(5)
            .all()
        )
        for r in rows:
            results[r.id] = r
        if len(results) >= 5:
            break

    _state.search_results = [
        {"id": a.id, "title": a.title, "category": a.category, "tags": a.tags}
        for a in list(results.values())[:5]
    ]
    reward = 0.0
    if _state.task == "full-workflow":
        reward += _earn("kb_searched")
    return reward, f"KB search for '{query}' returned {len(_state.search_results)} article(s)."


def _exec_link_article(db: Session, action: ActionModel) -> tuple[float, str]:
    tid = action.ticket_id or _state.ticket_id
    aid = action.article_id

    if not tid:
        return 0.0, "link_article failed: ticket_id required."
    if not aid:
        return 0.0, "link_article failed: article_id required."

    ticket = db.query(Ticket).filter(Ticket.id == tid).first()
    if not ticket:
        return 0.0, f"link_article failed: ticket #{tid} not found."
    article = db.query(KnowledgeBaseArticle).filter(KnowledgeBaseArticle.id == aid).first()
    if not article:
        return 0.0, f"link_article failed: article #{aid} not found."

    existing = (
        db.query(TicketArticleLink)
        .filter(TicketArticleLink.ticket_id == tid, TicketArticleLink.article_id == aid)
        .first()
    )
    if existing:
        return 0.0, f"Article #{aid} already linked to ticket #{tid}."

    db.add(TicketArticleLink(ticket_id=tid, article_id=aid))
    db.commit()

    reward = 0.0
    if _state.task == "full-workflow":
        reward += _earn("article_linked")
    return reward, f"Article #{aid} ('{article.title[:40]}') linked to ticket #{tid}."


def _execute(action: ActionModel) -> tuple[float, Optional[str], Optional[str]]:
    """Dispatch action, return (reward, result_msg, error_msg)."""
    atype = action.action_type
    db = _new_session()
    try:
        if atype == "create_ticket":
            r, msg = _exec_create_ticket(db, action)
        elif atype == "add_comment":
            r, msg = _exec_add_comment(db, action)
        elif atype == "update_status":
            r, msg = _exec_update_status(db, action)
        elif atype == "search_kb":
            r, msg = _exec_search_kb(db, action)
        elif atype == "link_article":
            r, msg = _exec_link_article(db, action)
        elif atype == "noop":
            return 0.0, "No operation.", None
        else:
            return 0.0, None, f"Unknown action_type: '{atype}'"
        return r, msg, None
    except Exception as exc:  # noqa: BLE001
        return 0.0, None, str(exc)
    finally:
        db.close()


# ── Public API ────────────────────────────────────────────────────────────────

def do_reset(task: str) -> Observation:
    if task not in _TASK_META:
        task = "create-ticket"
    with _lock:
        _state._init()
        _state.task = task
        _state.done = False
        _seed(task)
        return Observation(
            task=task,
            step=0,
            done=False,
            instructions=_TASK_INSTRUCTIONS[task],
            available_actions=_AVAILABLE_ACTIONS[task],
            state=_snapshot(),
            last_action_result=None,
        )


def do_step(action: ActionModel) -> StepResult:
    with _lock:
        if _state.done:
            obs = Observation(
                task=_state.task,
                step=_state.step,
                done=True,
                instructions=_TASK_INSTRUCTIONS.get(_state.task, ""),
                available_actions=_AVAILABLE_ACTIONS.get(_state.task, []),
                state=_snapshot(),
                last_action_result="Episode finished. Call POST /reset to start a new episode.",
            )
            return StepResult(observation=obs, reward=0.0, done=True)

        _state.step += 1
        reward, result_msg, error_msg = _execute(action)
        _state.rewards.append(reward)
        _state.last_action_result = result_msg or error_msg

        max_steps = _TASK_META[_state.task]["max_steps"]
        if _state.step >= max_steps:
            _state.done = True

        obs = Observation(
            task=_state.task,
            step=_state.step,
            done=_state.done,
            instructions=_TASK_INSTRUCTIONS[_state.task],
            available_actions=_AVAILABLE_ACTIONS[_state.task],
            state=_snapshot(),
            last_action_result=_state.last_action_result,
        )
        return StepResult(
            observation=obs,
            reward=reward,
            done=_state.done,
            error=error_msg,
        )


def do_state() -> StateResponse:
    with _lock:
        return StateResponse(
            task=_state.task,
            step=_state.step,
            done=_state.done,
            total_reward=sum(_state.rewards),
            rewards=list(_state.rewards),
            state=_snapshot(),
        )
