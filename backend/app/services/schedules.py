"""Schedule rows <-> recurrence specs, and the 'immutable version' rules."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Schedule
from app.services.recurrence import ScheduleKind, ScheduleSpec


def spec_of(row: Schedule) -> ScheduleSpec:
    return ScheduleSpec(
        kind=ScheduleKind(row.kind),
        tz=row.tz,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        times_of_day=tuple(row.times_of_day),
        days_of_week=tuple(row.days_of_week),
        interval=row.interval,
        total_doses=row.total_doses,
    )


def new_row(
    spec: ScheduleSpec,
    *,
    user_id,
    medication_id,
    dose_amount: Decimal,
    dose_unit: str,
    instructions: str | None,
    replaces: Schedule | None = None,
) -> Schedule:
    return Schedule(
        user_id=user_id,
        medication_id=medication_id,
        kind=spec.kind.value,
        tz=spec.tz,
        times_of_day=list(spec.times_of_day),
        days_of_week=list(spec.days_of_week),
        interval=spec.interval,
        starts_at=spec.starts_at,
        ends_at=spec.ends_at,
        total_doses=spec.total_doses,
        dose_amount=dose_amount,
        dose_unit=dose_unit,
        instructions=instructions,
        replaces_schedule_id=replaces.id if replaces else None,
    )


async def end(db: AsyncSession, row: Schedule, now: datetime) -> Schedule | None:
    """Stop a schedule as of now.

    A schedule that has already produced doses is *ended*, never deleted, so
    those doses and their logs stay explainable. One that hasn't started yet
    has no history, so it is simply removed. Returns the row if it was kept.
    """
    if row.starts_at >= now:
        await db.delete(row)
        return None
    # ends_at must stay strictly after starts_at (DB check constraint).
    row.ends_at = max(now, row.starts_at + timedelta(seconds=1))
    return row


def is_open(row: Schedule, now: datetime) -> bool:
    return row.ends_at is None or row.ends_at > now
