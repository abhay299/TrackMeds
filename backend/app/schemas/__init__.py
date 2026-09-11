"""Request/response shapes. The API contract lives here, and the OpenAPI schema
FastAPI derives from it is what the mobile app's TypeScript types are generated
from — so field names and optionality are chosen for the client, not the DB.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import MEDICATION_FORMS
from app.services.recurrence import DoseStatus, ScheduleKind, ScheduleSpec

MedicationForm = Literal["tablet", "capsule", "liquid", "injection", "drops", "inhaler", "other"]
assert set(MedicationForm.__args__) == set(MEDICATION_FORMS)  # keep API and DB in step


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- profile ---------------------------------------------------------------------


class ProfileOut(ORMModel):
    id: uuid.UUID
    display_name: str | None
    tz: str
    missed_grace_minutes: int


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    tz: str | None = None
    missed_grace_minutes: int | None = Field(default=None, ge=0, le=720)

    @field_validator("tz")
    @classmethod
    def _known_tz(cls, v: str | None) -> str | None:
        if v is not None:
            _zone(v)
        return v


# --- schedules -----------------------------------------------------------------


class ScheduleIn(BaseModel):
    """How the app describes a schedule. Dates and clock times are the user's
    local ones; the API converts them to instants using `tz`."""

    kind: ScheduleKind
    tz: str  # the device's IANA zone at creation, e.g. "Asia/Kolkata"
    times_of_day: list[time] = []  # daily / weekly / every_n_days
    days_of_week: list[int] = Field(default=[], max_length=7)  # weekly, 0=Mon .. 6=Sun
    interval: int = Field(default=1, ge=1, le=365)  # every_n_days / every_n_hours
    start_date: date | None = None  # day-based kinds; default: effective immediately
    first_dose_at: datetime | None = None  # every_n_hours; default: now
    end_date: date | None = None  # last day, inclusive
    total_doses: int | None = Field(default=None, ge=1, le=10_000)
    dose_amount: Decimal = Field(gt=0, max_digits=8, decimal_places=3)
    dose_unit: str = Field(min_length=1, max_length=20)  # "tablet", "ml", "puff"
    instructions: str | None = Field(default=None, max_length=500)

    @field_validator("tz")
    @classmethod
    def _known_tz(cls, v: str) -> str:
        _zone(v)
        return v

    def to_spec(self, now: datetime) -> ScheduleSpec:
        """Resolve local dates to instants. Raises ValueError for inconsistent input;
        the route turns that into a 422."""
        zone = _zone(self.tz)
        today = now.astimezone(zone).date()

        if self.kind is ScheduleKind.EVERY_N_HOURS:
            starts_at = self.first_dose_at or now
            if starts_at.tzinfo is None:
                raise ValueError("first_dose_at must include a UTC offset")
        elif self.start_date is None or self.start_date <= today:
            starts_at = now  # "effective from now": today's earlier times are not doses
        else:
            starts_at = datetime.combine(self.start_date, time(0), tzinfo=zone)

        ends_at = None
        if self.end_date is not None:
            ends_at = datetime.combine(self.end_date + timedelta(days=1), time(0), tzinfo=zone)

        return ScheduleSpec(
            kind=self.kind,
            tz=self.tz,
            starts_at=starts_at.astimezone(UTC),
            ends_at=ends_at.astimezone(UTC) if ends_at else None,
            times_of_day=tuple(sorted(self.times_of_day)),
            days_of_week=tuple(sorted(set(self.days_of_week))),
            interval=self.interval,
            total_doses=self.total_doses,
        )


class ScheduleOut(ORMModel):
    id: uuid.UUID
    medication_id: uuid.UUID
    kind: ScheduleKind
    tz: str
    times_of_day: list[time]
    days_of_week: list[int]
    interval: int
    starts_at: datetime
    ends_at: datetime | None
    total_doses: int | None
    dose_amount: Decimal
    dose_unit: str
    instructions: str | None
    replaces_schedule_id: uuid.UUID | None
    created_at: datetime


# --- medications -----------------------------------------------------------------


class MedicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    strength: str | None = Field(default=None, max_length=60)
    form: MedicationForm = "tablet"
    notes: str | None = Field(default=None, max_length=2000)
    schedule: ScheduleIn


class MedicationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    strength: str | None = Field(default=None, max_length=60)
    form: MedicationForm | None = None
    notes: str | None = Field(default=None, max_length=2000)


class MedicationOut(ORMModel):
    id: uuid.UUID
    name: str
    strength: str | None
    form: MedicationForm
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    schedules: list[ScheduleOut]  # current (open) schedules only


# --- doses ---------------------------------------------------------------------------


class DoseLogIn(BaseModel):
    schedule_id: uuid.UUID
    scheduled_at: datetime | None = None  # null only for as-needed schedules
    status: Literal["taken", "skipped"]
    taken_at: datetime | None = None  # defaults to now for "taken"
    note: str | None = Field(default=None, max_length=500)
    source: Literal["app", "notification", "web"] = "app"


class DoseLogOut(ORMModel):
    id: uuid.UUID
    schedule_id: uuid.UUID
    medication_id: uuid.UUID
    scheduled_at: datetime | None
    status: Literal["taken", "skipped"]
    taken_at: datetime | None
    note: str | None
    source: str
    created_at: datetime


class DoseInstanceOut(BaseModel):
    """A computed dose: what to take, when, and what happened to it."""

    schedule_id: uuid.UUID
    medication_id: uuid.UUID
    medication_name: str
    strength: str | None
    form: MedicationForm
    dose_amount: Decimal
    dose_unit: str
    instructions: str | None
    scheduled_at: datetime
    status: DoseStatus
    log: DoseLogOut | None


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown time zone {name!r}") from exc
