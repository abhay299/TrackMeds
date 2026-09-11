"""Dose instances (computed) and dose logs (the only thing stored per dose)."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import Me, Now
from app.core.db import DbSession
from app.models import DoseLog, Medication, Schedule
from app.schemas import DoseInstanceOut, DoseLogIn, DoseLogOut
from app.services import doses
from app.services.recurrence import ScheduleKind

router = APIRouter(tags=["doses"])

MAX_WINDOW = timedelta(days=62)


@router.get("/doses", response_model=list[DoseInstanceOut])
async def list_doses(
    profile: Me,
    db: DbSession,
    now: Now,
    window_start: Annotated[datetime, Query(alias="from")],
    window_end: Annotated[datetime, Query(alias="to")],
) -> list[DoseInstanceOut]:
    """Doses scheduled in [from, to). The app passes the UTC bounds of its local
    day for Today, or now..now+14d to schedule reminders."""
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "from/to need a UTC offset")
    if not (window_start < window_end <= window_start + MAX_WINDOW):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"window must be 0 < to - from <= {MAX_WINDOW}"
        )
    return [
        DoseInstanceOut(
            schedule_id=d.schedule.id,
            medication_id=d.medication.id,
            medication_name=d.medication.name,
            strength=d.medication.strength,
            form=d.medication.form,  # type: ignore[arg-type]
            dose_amount=d.schedule.dose_amount,
            dose_unit=d.schedule.dose_unit,
            instructions=d.schedule.instructions,
            scheduled_at=d.scheduled_at,
            status=d.status,
            log=DoseLogOut.model_validate(d.log) if d.log else None,
        )
        for d in await doses.instances(db, profile, window_start, window_end, now)
    ]


@router.post("/doses/log", response_model=DoseLogOut, status_code=status.HTTP_201_CREATED)
async def log_dose(body: DoseLogIn, profile: Me, db: DbSession, now: Now) -> DoseLogOut:
    """Record what happened to a dose. Idempotent per (schedule, scheduled_at):
    logging the same dose twice updates the first record instead of duplicating
    it, so a notification action and a tap in the app can't disagree."""
    row = await db.scalar(
        select(Schedule)
        .join(Medication)
        .where(Schedule.id == body.schedule_id, Schedule.user_id == profile.id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule not found")

    as_needed = row.kind == ScheduleKind.AS_NEEDED.value
    if as_needed and body.scheduled_at is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "as-needed doses have no scheduled_at"
        )
    if not as_needed:
        if body.scheduled_at is None or body.scheduled_at.tzinfo is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "scheduled_at is required")
        if body.scheduled_at > now + timedelta(hours=1):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "that dose is not due yet")
        if not doses.is_instance(row, body.scheduled_at):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "no dose is scheduled at that time"
            )

    values = {
        "user_id": profile.id,
        "medication_id": row.medication_id,
        "schedule_id": row.id,
        "scheduled_at": body.scheduled_at,
        "status": body.status,
        "taken_at": (body.taken_at or now) if body.status == "taken" else None,
        "note": body.note,
        "source": body.source,
    }
    stmt = insert(DoseLog).values(**values)
    if not as_needed:
        stmt = stmt.on_conflict_do_update(
            constraint="uq_dose_logs_schedule_scheduled_at",
            set_={k: values[k] for k in ("status", "taken_at", "note", "source")},
        )
    log_id = await db.scalar(stmt.returning(DoseLog.id))
    await db.commit()
    return DoseLogOut.model_validate(await db.get(DoseLog, log_id))


@router.delete("/doses/log/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def undo_log(log_id: uuid.UUID, profile: Me, db: DbSession) -> None:
    log = await db.scalar(
        select(DoseLog).where(DoseLog.id == log_id, DoseLog.user_id == profile.id)
    )
    if log is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "log not found")
    await db.delete(log)
    await db.commit()
