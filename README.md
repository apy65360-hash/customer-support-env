# Customer Support Environment

A fully-featured customer support ticket resolution API built with **FastAPI** + **SQLite** (swappable to PostgreSQL).

## Features

| Feature | Details |
|---|---|
| **Auth** | JWT bearer tokens, bcrypt passwords, role-based access (customer / agent / admin) |
| **Ticket Management** | CRUD, search/filter by status · priority · category · assignee |
| **Ticketing Workflow** | Auto-assign (least-loaded agent), status-transition rules, SLA overdue flagging |
| **Comments / Messaging** | Threaded comments per ticket, internal agent-only notes, email notification stub |
| **Knowledge Base** | Article CRUD, keyword-based suggestion on ticket creation, manual article–ticket linking |
| **Reporting** | Open/resolved summary, avg resolution time by category+priority, per-agent performance, overdue list |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) copy and edit environment variables
cp .env.example .env

# 3. Run the API (tables are created automatically)
uvicorn app.main:app --reload
```

Interactive docs: http://localhost:8000/docs

---

## Project Structure

```
app/
├── main.py            # FastAPI app + lifespan (DB init)
├── config.py          # Settings (pydantic-settings / .env)
├── database.py        # SQLAlchemy engine + session
├── dependencies.py    # Auth & RBAC FastAPI dependencies
├── models/            # SQLAlchemy ORM models
├── schemas/           # Pydantic request/response schemas
├── routers/           # FastAPI route handlers
└── services/          # Business logic
tests/                 # pytest test suite (28 tests)
```

---

## API Overview

### Auth — `/auth/`
Register, login (JWT), profile update, admin user management.

### Tickets — `/tickets/`
Full CRUD. Filter by `status`, `priority`, `category`, `assignee_id`, `search`.
Customers only see their own tickets.

### Comments — `/tickets/{id}/comments/`
Threaded comments. Set `is_internal=true` for agent-only notes (hidden from customers).

### Knowledge Base — `/kb/`
Article CRUD (agents only for writes). Keyword suggestion via `GET /kb/articles/suggest?text=…`.
Articles are auto-suggested and linked when a ticket is created.

### Reports — `/reports/`  *(agent+ only)*
- `/summary` — ticket counts by status
- `/resolution-time` — avg resolution hours by category + priority
- `/agent-performance` — resolved count + avg hours per agent
- `/overdue` — tickets past their SLA threshold

---

## SLA Thresholds

| Priority | SLA |
|---|---|
| urgent | 2 hours |
| high | 8 hours |
| medium | 24 hours |
| low | 72 hours |

---

## Status Transition Rules

```
open ──► in_progress ──► resolved ──► closed
  ▲           │              │
  │           ▼              │
  └──── open ◄──────────────┘  (requires reopen_reason when from closed)
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./support.db` | SQLAlchemy DSN |
| `SECRET_KEY` | *(change me)* | JWT signing key |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token lifetime |
| `SMTP_HOST` | `localhost` | SMTP server (stub when localhost) |
| `SMTP_PORT` | `25` | SMTP port |
| `SMTP_USER` / `SMTP_PASSWORD` | — | SMTP credentials |
| `EMAIL_FROM` | `support@example.com` | Sender address |
