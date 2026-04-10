from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routers import auth, comments, knowledge_base, reports, tickets


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup (for development / SQLite)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Customer Support API",
    description="Customer support ticket resolution environment",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(knowledge_base.router)
app.include_router(reports.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
