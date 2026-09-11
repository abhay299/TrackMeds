"""API tests run against a real Postgres (docker compose up -d db), because the
interesting behaviour — unique constraints, arrays, timestamptz, ON CONFLICT —
is Postgres behaviour. Each test starts from truncated tables and gets a fresh
session per request (as production does), so tests never see each other's rows
and never a stale identity-map object.

Auth is bypassed here (the security tests cover it): `as_user` swaps the
caller's identity so ownership rules can be tested. Time is frozen via the
`now_utc` dependency so 'today', 'due' and 'missed' are deterministic.
"""

import os
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import now_utc
from app.core.db import get_session
from app.core.security import AuthUser, current_user
from app.main import app
from app.models import Base

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://trackmeds:trackmeds@localhost:54329/trackmeds_test"
)
USER_A = "00000000-0000-0000-0000-00000000000a"
USER_B = "00000000-0000-0000-0000-00000000000b"

# Thursday 2026-09-11 10:00 IST = 04:30 UTC. Tests reason in IST.
FROZEN_NOW = datetime(2026, 9, 11, 4, 30, tzinfo=UTC)


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except OSError as exc:
        pytest.exit(
            f"test database unreachable at {TEST_DB_URL} — run `docker compose up -d db` ({exc})"
        )
    yield engine
    await engine.dispose()


# Isolation by truncation before each test — order-independent and bulletproof,
# and cheap against the throwaway database. (Rolling back one outer transaction
# would not isolate endpoints that commit several times per request.)
_TABLES = "dose_logs, schedules, medications, profiles"


@pytest_asyncio.fixture
async def sessionmaker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    yield async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    # For tests that seed or inspect the database directly.
    async with sessionmaker() as session:
        yield session


class Clock:
    def __init__(self) -> None:
        self.now = FROZEN_NOW


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest_asyncio.fixture
async def api(
    sessionmaker: async_sessionmaker[AsyncSession], clock: Clock
) -> AsyncIterator[AsyncClient]:
    identity = {"id": USER_A}

    async def _session() -> AsyncIterator[AsyncSession]:
        # A fresh session per request, exactly as production get_session does —
        # so the identity map never carries stale rows between requests.
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[current_user] = lambda: AuthUser(id=identity["id"], email=None)
    app.dependency_overrides[now_utc] = lambda: clock.now
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Timezone": "Asia/Kolkata"},
    ) as client:
        client.identity = identity  # type: ignore[attr-defined]
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def as_user(api: AsyncClient) -> Callable[[str], None]:
    def _switch(user_id: str) -> None:
        api.identity["id"] = user_id  # type: ignore[attr-defined]

    return _switch


# --- request bodies used across tests ------------------------------------------


def daily(times: list[str], **extra) -> dict:
    return {
        "kind": "daily",
        "tz": "Asia/Kolkata",
        "times_of_day": times,
        "dose_amount": 1,
        "dose_unit": "tablet",
        **extra,
    }


def every_n_days(n: int, times: list[str], **extra) -> dict:
    return {
        "kind": "every_n_days",
        "interval": n,
        "tz": "Asia/Kolkata",
        "times_of_day": times,
        "dose_amount": 1,
        "dose_unit": "capsule",
        **extra,
    }


def medication(name: str, schedule: dict, **extra) -> dict:
    return {"name": name, "strength": "500 mg", "form": "tablet", "schedule": schedule, **extra}


def ist_window(day: str) -> dict[str, str]:
    """Query params for one local day in IST, as the app would send them."""
    start = datetime.fromisoformat(f"{day}T00:00:00+05:30")
    end = start.replace(day=start.day + 1)
    return {"from": start.isoformat(), "to": end.isoformat()}


def new_id() -> str:
    return str(uuid.uuid4())
