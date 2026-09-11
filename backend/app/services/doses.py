"""Dose instances for a user and a time window: computed, then joined to logs."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import DoseLog, Medication, Profile, Schedule
from app.services import recurrence
from app.services.recurrence import DoseStatus, ScheduleKind
from app.services.schedules import spec_of


@dataclass(frozen=True)
class DoseInstance:
    schedule: Schedule
    medication: Medication
    scheduled_at: datetime
    status: DoseStatus
    log: DoseLog | None


async def instances(
    db: AsyncSession, profile: Profile, window_start: datetime, window_end: datetime, now: datetime
) -> list[DoseInstance]:
    """Every scheduled dose in [window_start, window_end), ascending.

    Ended/replaced schedule versions are included when they overlap the window —
    that is exactly what keeps last week's history correct after an edit.
    """
    rows: Sequence[Schedule] = (
        (
            await db.execute(
                select(Schedule)
                .join(Medication)
                .options(selectinload(Schedule.medication))
                .where(
                    Schedule.user_id == profile.id,
                    Schedule.kind != ScheduleKind.AS_NEEDED.value,
                    Medication.archived_at.is_(None),
                    Schedule.starts_at < window_end,
                    (Schedule.ends_at.is_(None)) | (Schedule.ends_at > window_start),
                )
            )
        )
        .scalars()
        .all()
    )
    logs = (
        (
            await db.execute(
                select(DoseLog).where(
                    DoseLog.user_id == profile.id,
                    DoseLog.scheduled_at >= window_start,
                    DoseLog.scheduled_at < window_end,
                )
            )
        )
        .scalars()
        .all()
    )
    log_by_key: dict[tuple[uuid.UUID, datetime], DoseLog] = {
        (log.schedule_id, log.scheduled_at): log for log in logs if log.scheduled_at
    }

    default_grace = timedelta(minutes=profile.missed_grace_minutes)
    out: list[DoseInstance] = []
    for row in rows:
        spec = spec_of(row)
        grace = recurrence.grace_for(spec, default_grace)
        for at in recurrence.expand(spec, window_start, window_end):
            log = log_by_key.get((row.id, at))
            status = recurrence.dose_status(
                at, now=now, grace=grace, logged=log.status if log else None
            )
            out.append(DoseInstance(row, row.medication, at, status, log))
    out.sort(key=lambda d: (d.scheduled_at, d.medication.name.lower()))
    return out


def is_instance(row: Schedule, at: datetime) -> bool:
    """Does this schedule really produce a dose at `at`? Guards the log endpoint
    against keys that no schedule would ever generate."""
    spec = spec_of(row)
    return at in recurrence.expand(spec, at, at + timedelta(seconds=1))
