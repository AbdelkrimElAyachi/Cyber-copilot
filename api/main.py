"""
FastAPI application — entry point for the Cyber Copilot API.

Wires up all routers, manages startup/shutdown of shared services,
and configures CORS for the future React frontend.

Run with:
    uvicorn api.main:app --reload
"""

from __future__ import annotations

from logging_config import setup_logging

setup_logging()  # before anything else logs, so nothing is missed

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import startup, shutdown, get_current_user
from api.routers import auth, investigations, policies, assets, users, system, chat


# ── Lifespan ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to the database on startup, close on shutdown."""
    startup()
    yield
    shutdown()


# ── App ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Cyber Copilot",
    description="AI-Powered Security Investigation Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the React frontend (dev server) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ─────────────────────────────────────────────────────────────

# auth.router is the one exception — it's how a token is obtained, so it
# can't itself require one. Everything else needs a valid bearer token;
# there's a single access tier today (see api/auth.py), so this is a
# login wall rather than per-route permission checks for now.
app.include_router(auth.router)

_protected = Depends(get_current_user)
app.include_router(investigations.router, dependencies=[_protected])
app.include_router(policies.router, dependencies=[_protected])
app.include_router(assets.router, dependencies=[_protected])
app.include_router(users.router, dependencies=[_protected])
app.include_router(system.router, dependencies=[_protected])
app.include_router(chat.router, dependencies=[_protected])


# ── Health check ────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}
