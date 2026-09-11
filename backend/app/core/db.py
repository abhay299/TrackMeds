"""Database access: one async engine per process, one session per request.

Why async + asyncpg: FastAPI is async; a blocking driver would pin a worker
thread for every DB round trip. asyncpg is the fastest Postgres driver in
Python and SQLAlchemy 2.0 speaks it natively.

Why such a small pool: Cloud Run runs at most `max-instances` (2) copies of
this process and Supabase's pooler caps client connections, so 2 + 2 overflow
per process is plenty for four users. `pool_pre_ping` notices connections the
pooler dropped while the instance sat idle; `pool_recycle` retires them first.

Why `ssl=require`: Supabase only accepts TLS. "require" encrypts without
verifying the certificate chain — fine while the pooler host is pinned in
DATABASE_URL; tighten to a verified SSLContext if that ever changes.
"""

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        get_settings().database_url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"ssl": "require"},
    )
    # expire_on_commit=False: after a commit we still want to read the objects we
    # just wrote without SQLAlchemy issuing a surprise refresh query.
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]
