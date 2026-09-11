"""Database tables, as SQLAlchemy 2.0 typed models.

The shape follows one rule from the plan: **schedules are immutable versions**.
Editing a schedule ends the old row (`ends_at`) and inserts a new one linked by
`replaces_schedule_id`, so history stays explainable — a dose logged last week
still points at the schedule that produced it.

Nothing here stores dose *instances*; those are computed by
`app.services.recurrence`. `DoseLog` is the only per-dose row, and only when
the user acted (took or skipped). Its unique key (schedule_id, scheduled_at) is
what makes logging idempotent: a notification action and a tap on the Today
screen for the same dose cannot create two records.

Every table is created with row-level security enabled and no policies, so the
publishable key shipped inside the app can't read them through Supabase's REST
layer; only the API (connecting as `postgres`) can.
"""

import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEDULE_KINDS = ("daily", "weekly", "every_n_days", "every_n_hours", "as_needed")
MEDICATION_FORMS = ("tablet", "capsule", "liquid", "injection", "drops", "inhaler", "other")
LOG_STATUSES = ("taken", "skipped")
LOG_SOURCES = ("app", "notification", "web")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Profile(TimestampMixin, Base):
    """One row per signed-in user; `id` is the Supabase Auth user id."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    tz: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")
    missed_grace_minutes: Mapped[int] = mapped_column(nullable=False, server_default=text("120"))


class Medication(TimestampMixin, Base):
    __tablename__ = "medications"
    __table_args__ = (
        CheckConstraint(_in("form", MEDICATION_FORMS), name="medications_form_check"),
        Index("ix_medications_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(60))  # "500 mg", "10 mg/ml"
    form: Mapped[str] = mapped_column(String(20), nullable=False, server_default="tablet")
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="medication", order_by="Schedule.created_at"
    )


class Schedule(TimestampMixin, Base):
    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint(_in("kind", SCHEDULE_KINDS), name="schedules_kind_check"),
        CheckConstraint("interval >= 1", name="schedules_interval_check"),
        CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at", name="schedules_ends_after_start"
        ),
        Index("ix_schedules_user_id", "user_id"),
        Index("ix_schedules_medication_id", "medication_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    medication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    times_of_day: Mapped[list[time]] = mapped_column(
        ARRAY(Time), nullable=False, server_default=text("'{}'")
    )
    days_of_week: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), nullable=False, server_default=text("'{}'")
    )
    interval: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_doses: Mapped[int | None]
    tz: Mapped[str] = mapped_column(String(64), nullable=False)
    dose_amount: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    dose_unit: Mapped[str] = mapped_column(String(20), nullable=False)  # tablet, ml, puff...
    instructions: Mapped[str | None] = mapped_column(Text)  # "after food"
    replaces_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL")
    )

    medication: Mapped[Medication] = relationship(back_populates="schedules")


class DoseLog(TimestampMixin, Base):
    __tablename__ = "dose_logs"
    __table_args__ = (
        CheckConstraint(_in("status", LOG_STATUSES), name="dose_logs_status_check"),
        CheckConstraint(_in("source", LOG_SOURCES), name="dose_logs_source_check"),
        # One log per scheduled dose. NULL scheduled_at (as-needed doses) is
        # exempt, since Postgres treats NULLs as distinct in unique constraints.
        UniqueConstraint("schedule_id", "scheduled_at", name="uq_dose_logs_schedule_scheduled_at"),
        Index("ix_dose_logs_user_scheduled_at", "user_id", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    medication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="app")
