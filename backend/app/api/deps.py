"""Dependencies shared by the routes."""

import uuid
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Header
from sqlalchemy.dialects.postgresql import insert

from app.core.db import DbSession
from app.core.security import CurrentUser
from app.models import Profile


def _valid_tz(name: str | None) -> str:
    if not name:
        return "UTC"
    try:
        ZoneInfo(name)
    except Exception:
        return "UTC"
    return name


async def current_profile(
    user: CurrentUser,
    db: DbSession,
    x_timezone: Annotated[str | None, Header()] = None,
) -> Profile:
    """The caller's profile row, created on first contact.

    Supabase owns sign-up; we only learn about a user when their first request
    arrives. The insert is ON CONFLICT DO NOTHING so two first requests racing
    (the app fires /me and /doses together) can't collide.
    """
    user_id = uuid.UUID(user.id)
    await db.execute(
        insert(Profile)
        .values(id=user_id, tz=_valid_tz(x_timezone))
        .on_conflict_do_nothing(index_elements=[Profile.id])
    )
    await db.commit()
    profile = await db.get(Profile, user_id)
    assert profile is not None
    return profile


Me = Annotated[Profile, Depends(current_profile)]


def now_utc() -> datetime:
    # A dependency rather than a bare call so tests can freeze time.
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(now_utc)]
