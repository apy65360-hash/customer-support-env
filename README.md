---
title: Customer Support Env
emoji: 🎫
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
tags:
  - openenv
  - customer-support
  - reinforcement-learning
  - agent-evaluation
---

# Customer Support OpenEnv

A **real-world customer-support ticket resolution environment** built with FastAPI + SQLite, exposing the standard OpenEnv `step()` / `reset()` / `state()` API for training and evaluating AI agents.

Agents learn to create tickets, route them through a lifecycle workflow, search a knowledge base, link relevant articles, and close resolved issues — all via a typed REST API.

---

## Environment Description & Motivation

Customer support ticket management is a task humans perform every day in every industry. It requires:

- **Structured data creation** (well-formed tickets with correct fields)
- **Multi-step workflow execution** (open → in_progress → resolved → closed)
- **Information retrieval** (finding relevant knowledge-base articles)
- **Decision-making under partial information** (which action moves the ticket forward?)

This makes it an ideal benchmark domain: it is real-world, measurable, and has clear success criteria that scale from trivial (did you fill in the title?) to genuinely hard (did you complete the full 7-step workflow in the correct order?).

---

## Observation Space

| Field | Type | Description |
|---|---|---|
| `task` | `string` | Active task name (`create-ticket`, `resolve-ticket`, `full-workflow`) |
| `step` | `integer` | Current step number (0 = just reset) |
| `done` | `boolean` | Whether the episode has ended |
| `instructions` | `string` | Human-readable task instructions for the agent |
| `available_actions` | `string[]` | List of valid action signatures for this task |
| `state` | `object` | Task-specific DB snapshot (tickets, comments, KB articles) |
| `last_action_result` | `string \| null` | Human-readable result of the previous action (null on reset) |

---

## Action Space

| Field | Type | Required | Description |
|---|---|---|---|
| `action_type` | `string` | ✅ | One of: `create_ticket`, `add_comment`, `update_status`, `search_kb`, `link_article`, `noop` |
| `title` | `string` | For `create_ticket` | Ticket title (≥10 chars for full reward) |
| `description` | `string` | For `create_ticket` | Ticket description (≥20 chars for full reward) |
| `priority` | `string` | For `create_ticket` | One of: `low`, `medium`, `high`, `urgent` |
| `category` | `string` | For `create_ticket` | Ticket category (non-empty) |
| `ticket_id` | `integer` | For `add_comment`, `update_status`, `link_article` | Target ticket ID |
| `status` | `string` | For `update_status` | One of: `in_progress`, `resolved`, `closed` |
| `body` | `string` | For `add_comment` | Comment text |
| `query` | `string` | For `search_kb` | Search query string |
| `article_id` | `integer` | For `link_article` | Knowledge base article ID to link |

---

## Tasks

### Task 1 — Create Support Ticket *(Easy, max 10 steps)*

**Objective:** Create a high-quality support ticket with all required fields.

**Reward structure** (0.25 each, total 1.0):
| Milestone | Reward |
|---|---|
| `title` ≥ 10 characters | 0.25 |
| `description` ≥ 20 characters | 0.25 |
| `priority` is `low`/`medium`/`high`/`urgent` | 0.25 |
| `category` is non-empty | 0.25 |

Episode ends as soon as all four quality dimensions are satisfied.

---

### Task 2 — Resolve Support Ticket *(Medium, max 15 steps)*

**Objective:** A pre-existing open ticket is assigned to the agent. Guide it to resolution.

**Reward structure** (0.25 each, total 1.0):
| Milestone | Reward |
|---|---|
| Add an acknowledgement comment | 0.25 |
| Move ticket to `in_progress` | 0.25 |
| Add a resolution-explanation comment | 0.25 |
| Move ticket to `resolved` | 0.25 |

Episode ends when the ticket reaches `resolved`.

---

### Task 3 — Full Support Workflow *(Hard, max 20 steps)*

**Objective:** Complete the entire end-to-end support workflow.

**Reward structure** (weighted, total 1.0):
| Milestone | Reward |
|---|---|
| Create ticket | 0.15 |
| Add a comment | 0.15 |
| Search knowledge base | 0.10 |
| Link a KB article to the ticket | 0.15 |
| Move ticket to `in_progress` | 0.10 |
| Move ticket to `resolved` | 0.15 |
| Move ticket to `closed` | 0.20 |

Episode ends when the ticket reaches `closed`.

---

## Setup & Usage

### 1. Clone and install

```bash
git clone https://github.com/apy65360-hash/customer-support-env
cd customer-support-env
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env — set HF_TOKEN, API_BASE_URL, MODEL_NAME at minimum
```

### 3. Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 7860
# API docs available at http://localhost:7860/docs
```

### 4. Run inference

```bash
# Run all three tasks
python inference.py

# Run a single task
TASK=create-ticket python inference.py
```

### 5. Run tests

```bash
pytest tests/ -v
```

### 6. Docker

```bash
docker build -t customer-support-env .
docker run -p 7860:7860 \
  -e HF_TOKEN=your-token \
  -e API_BASE_URL=https://router.huggingface.co/v1 \
  -e MODEL_NAME=your-model-name \
  customer-support-env
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `API_BASE_URL` | `https://router.huggingface.co/v1` | LLM inference endpoint (OpenAI-compatible) |
| `MODEL_NAME` | *(set via env var)* | Model identifier for inference |
| `HF_TOKEN` | — | HuggingFace API key / token (required for inference) |
| `SERVER_URL` | `http://localhost:7860` | OpenEnv server base URL used by inference.py |
| `TASK` | *(all three)* | Run a single task instead of all three |
| `DATABASE_URL` | `sqlite:///./support.db` | SQLAlchemy DSN for main app DB |
| `SECRET_KEY` | *(change me)* | JWT signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT token lifetime (minutes) |

---

## Baseline Scores

Baseline agent: HuggingFace Inference Router (set via `MODEL_NAME` env var)  
Temperature: 0.3 | Max tokens per step: 300

| Task | Difficulty | Score | Notes |
|---|---|---|---|
| `create-ticket` | Easy | **1.000** | LLM reliably produces all 4 required fields in a single action |
| `resolve-ticket` | Medium | **0.750** | Usually completes acknowledgement + in_progress + resolution comment; occasionally skips final resolved step |
| `full-workflow` | Hard | **0.550** | Reliably creates ticket and comments; KB search and article linking are the common failure points |

---

## OpenEnv API

| Endpoint | Method | Description |
|---|---|---|
| `/reset` | POST | Reset episode; body: `{"task": "create-ticket"}` |
| `/step` | POST | Execute action; body: `{"action": {...}}` |
| `/state` | GET | Inspect current state without advancing |
| `/tasks` | GET | List available task IDs |
| `/health` | GET | Health check |
| `/docs` | GET | Interactive Swagger UI |

---

## Project Structure

```
customer-support-env/
├── app/
│   ├── main.py            # FastAPI app + lifespan (DB init)
│   ├── config.py          # Settings (pydantic-settings / .env)
│   ├── database.py        # SQLAlchemy engine + session
│   ├── dependencies.py    # Auth & RBAC FastAPI dependencies
│   ├── models/            # SQLAlchemy ORM models
│   ├── schemas/           # Pydantic request/response schemas
│   ├── routers/           # FastAPI route handlers (auth, tickets, comments, kb, reports)
│   ├── services/          # Business logic
│   └── openenv/           # OpenEnv spec implementation
│       ├── env.py         # Episode state machine + task graders
│       ├── models.py      # Typed Pydantic models (Observation, Action, Reward)
│       └── router.py      # /reset, /step, /state endpoints
├── tests/                 # pytest test suite (28 tests)
├── inference.py           # Baseline inference script
├── openenv.yaml           # OpenEnv metadata
├── Dockerfile             # Docker build (port 7860)
└── requirements.txt
```

---

## Status Transition Rules

```
open ──► in_progress ──► resolved ──► closed
  ▲           │              │              │
  │           ▼              │              │
  └──── open ◄──────────────┘              │
  ▲                                        │
  └────────────────────────────────────────┘
       (requires reopen_reason via REST API)
```

> **Note:** Reopening a `closed` ticket to `open` via the REST API (`PATCH /tickets/{id}`) requires a `reopen_reason` field. The OpenEnv `update_status` action does not support reopening closed tickets — it is intended for forward-progression through the workflow only.

## SLA Thresholds

| Priority | SLA |
|---|---|
| urgent | 2 hours |
| high | 8 hours |
| medium | 24 hours |
| low | 72 hours |

