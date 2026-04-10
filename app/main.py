from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.openenv.router import router as openenv_router
from app.routers import auth, comments, knowledge_base, reports, tickets


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup (for development / SQLite)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Customer Support OpenEnv",
    description=(
        "Customer support ticket resolution environment — "
        "exposes the standard OpenEnv step()/reset()/state() API alongside "
        "the full customer-support REST API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── OpenEnv endpoints (root-level so the validator can ping /reset) ───────────
app.include_router(openenv_router)

# ── Existing customer-support API ─────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(knowledge_base.router)
app.include_router(reports.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
