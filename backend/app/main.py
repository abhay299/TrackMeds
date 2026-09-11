"""ASGI entry point: `uvicorn app.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import me
from app.core.config import get_settings
from app.core.db import DbSession
from app.core.security import CurrentUser


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Load (and validate) settings before serving a single request. A container
    # missing SUPABASE_URL or DATABASE_URL must refuse to start — Cloud Run then
    # fails the deploy with the reason in the logs — instead of passing /health
    # and returning 500 on everything else.
    get_settings()
    yield


app = FastAPI(title="TrackMeds API", version="0.1.0", lifespan=lifespan)

# CORS only matters for browser clients (Expo web now, the website later). Native
# apps ignore it. No cookies are involved — auth is a bearer header — so
# credentials stay off and the origin list can be explicit.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Timezone"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    # Liveness only — no DB, no auth. Cloud Run and uptime checks hit this.
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(_: CurrentUser, db: DbSession) -> dict[str, str]:
    # Proves the whole DB path (pooler host, TLS, credentials) from wherever this
    # runs. Authenticated so strangers can't make us open connections.
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}


app.include_router(me.router)
