"""Medications and their schedules.

Ownership is enforced the same way everywhere: every query filters by the
caller's profile id, and anything not found *for this user* is a 404 — never a
403, which would confirm that someone else's id exists.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import Me, Now
from app.core.db import DbSession
from app.models import Medication, Profile, Schedule
from app.schemas import MedicationIn, MedicationOut, MedicationPatch, ScheduleIn, ScheduleOut
from app.services import schedules as sched

router = APIRouter(tags=["medications"])


async def _medication(db: AsyncSession, profile: Profile, medication_id: uuid.UUID) -> Medication:
    row = await db.scalar(
        select(Medication)
        .options(selectinload(Medication.schedules))
        .where(Medication.id == medication_id, Medication.user_id == profile.id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "medication not found")
    return row


async def _schedule(db: AsyncSession, profile: Profile, schedule_id: uuid.UUID) -> Schedule:
    row = await db.scalar(
        select(Schedule).where(Schedule.id == schedule_id, Schedule.user_id == profile.id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule not found")
    return row


def _out(med: Medication, now) -> MedicationOut:
    current = [ScheduleOut.model_validate(s) for s in med.schedules if sched.is_open(s, now)]
    return MedicationOut(
        id=med.id,
        name=med.name,
        strength=med.strength,
        form=med.form,  # type: ignore[arg-type]
        notes=med.notes,
        archived_at=med.archived_at,
        created_at=med.created_at,
        schedules=current,
    )


def _spec(body: ScheduleIn, now):
    try:
        return body.to_spec(now)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/medications", response_model=list[MedicationOut])
async def list_medications(
    profile: Me, db: DbSession, now: Now, archived: bool = False
) -> list[MedicationOut]:
    rows = await db.scalars(
        select(Medication)
        .options(selectinload(Medication.schedules))
        .where(
            Medication.user_id == profile.id,
            Medication.archived_at.is_not(None) if archived else Medication.archived_at.is_(None),
        )
        .order_by(Medication.name)
    )
    return [_out(m, now) for m in rows]


@router.post("/medications", response_model=MedicationOut, status_code=status.HTTP_201_CREATED)
async def create_medication(
    body: MedicationIn, profile: Me, db: DbSession, now: Now
) -> MedicationOut:
    spec = _spec(body.schedule, now)
    med = Medication(
        user_id=profile.id,
        name=body.name.strip(),
        strength=body.strength,
        form=body.form,
        notes=body.notes,
    )
    db.add(med)
    await db.flush()  # assigns med.id for the schedule row
    db.add(
        sched.new_row(
            spec,
            user_id=profile.id,
            medication_id=med.id,
            dose_amount=body.schedule.dose_amount,
            dose_unit=body.schedule.dose_unit,
            instructions=body.schedule.instructions,
        )
    )
    await db.commit()
    return _out(await _medication(db, profile, med.id), now)


@router.get("/medications/{medication_id}", response_model=MedicationOut)
async def read_medication(
    medication_id: uuid.UUID, profile: Me, db: DbSession, now: Now
) -> MedicationOut:
    return _out(await _medication(db, profile, medication_id), now)


@router.patch("/medications/{medication_id}", response_model=MedicationOut)
async def update_medication(
    medication_id: uuid.UUID, patch: MedicationPatch, profile: Me, db: DbSession, now: Now
) -> MedicationOut:
    med = await _medication(db, profile, medication_id)
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(med, field, value.strip() if field == "name" else value)
    await db.commit()
    return _out(await _medication(db, profile, med.id), now)


@router.delete("/medications/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_medication(
    medication_id: uuid.UUID, profile: Me, db: DbSession, now: Now
) -> None:
    """Archive, never delete: history keeps referring to it."""
    med = await _medication(db, profile, medication_id)
    if med.archived_at is None:
        med.archived_at = now
        for s in list(med.schedules):
            if sched.is_open(s, now):
                await sched.end(db, s, now)
    await db.commit()


@router.post(
    "/medications/{medication_id}/schedules",
    response_model=ScheduleOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_schedule(
    medication_id: uuid.UUID, body: ScheduleIn, profile: Me, db: DbSession, now: Now
) -> ScheduleOut:
    """A second schedule for the same medicine, e.g. a different dose at night."""
    med = await _medication(db, profile, medication_id)
    if med.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "medication is archived")
    row = sched.new_row(
        _spec(body, now),
        user_id=profile.id,
        medication_id=med.id,
        dose_amount=body.dose_amount,
        dose_unit=body.dose_unit,
        instructions=body.instructions,
    )
    db.add(row)
    await db.commit()
    return ScheduleOut.model_validate(row)


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
async def replace_schedule(
    schedule_id: uuid.UUID, body: ScheduleIn, profile: Me, db: DbSession, now: Now
) -> ScheduleOut:
    """'Edit' = end the old version now and start a new one that points back at it."""
    old = await _schedule(db, profile, schedule_id)
    if not sched.is_open(old, now):
        raise HTTPException(status.HTTP_409_CONFLICT, "schedule has already ended")
    spec = _spec(body, now)
    kept = await sched.end(db, old, now)
    row = sched.new_row(
        spec,
        user_id=profile.id,
        medication_id=old.medication_id,
        dose_amount=body.dose_amount,
        dose_unit=body.dose_unit,
        instructions=body.instructions,
        replaces=kept,
    )
    db.add(row)
    await db.commit()
    return ScheduleOut.model_validate(row)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_schedule(schedule_id: uuid.UUID, profile: Me, db: DbSession, now: Now) -> None:
    row = await _schedule(db, profile, schedule_id)
    if sched.is_open(row, now):
        await sched.end(db, row, now)
    await db.commit()
