"""Turning a schedule into concrete dose times.

This is the heart of the app and deliberately has no idea that a database
exists: a `ScheduleSpec` in, a list of UTC datetimes out. Everything else —
the Today screen, reminders, adherence — is built on `expand()`.

Why compute instead of store? A stored table of future doses needs a job to
keep generating rows and a rewrite on every edit. Computing on demand needs
neither; the only thing we ever persist about a dose is the user's log entry,
keyed by (schedule, scheduled time).

The maths is delegated to `dateutil.rrule` (RFC 5545 recurrence rules), the
same engine calendar apps use. Three things about it matter enough to spell
out here, because getting them wrong produces reminders at the wrong time:

1. One rule per time of day. `byhour=[8, 20], byminute=[0, 30]` does not mean
   "08:00 and 20:30" — rrule takes the cross product and yields 08:00, 08:30,
   20:00 and 20:30. So day-based schedules build one rule per clock time and
   merge them in an `rruleset`.

2. Wall-clock vs. absolute time. "08:00 every day" must stay 08:00 through a
   DST change, so day-based rules iterate in the schedule's own time zone and
   are converted to UTC afterwards. "Every 6 hours" must stay exactly 6 hours
   apart, so hourly rules iterate in UTC. (India has no DST; the tests cover
   America/New_York anyway so the behaviour is proven, not assumed.)

3. `starts_at` means "effective from". A schedule created at 10:00 saying
   "daily at 08:00 and 20:00" must not produce a dose for the 08:00 that has
   already passed. For every-N-days schedules the *local date* of `starts_at`
   also fixes which days are "on" days.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from itertools import islice
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import DAILY, HOURLY, WEEKLY, rrule, rruleset


class ScheduleKind(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    EVERY_N_DAYS = "every_n_days"
    EVERY_N_HOURS = "every_n_hours"
    AS_NEEDED = "as_needed"


DAY_BASED = frozenset({ScheduleKind.DAILY, ScheduleKind.WEEKLY, ScheduleKind.EVERY_N_DAYS})


@dataclass(frozen=True)
class ScheduleSpec:
    """Everything needed to generate dose times. Immutable, like the DB row it mirrors."""

    kind: ScheduleKind
    tz: str  # IANA name, e.g. "Asia/Kolkata"
    starts_at: datetime  # aware; effective-from instant (and the anchor for every_n_days)
    ends_at: datetime | None = None  # aware; exclusive
    times_of_day: tuple[time, ...] = ()  # day-based kinds; local wall-clock
    days_of_week: tuple[int, ...] = ()  # weekly; 0=Mon .. 6=Sun
    interval: int = 1  # every_n_days / every_n_hours
    total_doses: int | None = None  # fixed-length course, counted from starts_at

    def __post_init__(self) -> None:
        _require_aware("starts_at", self.starts_at)
        if self.ends_at is not None:
            _require_aware("ends_at", self.ends_at)
            if self.ends_at <= self.starts_at:
                raise ValueError("ends_at must be after starts_at")
        try:
            ZoneInfo(self.tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone {self.tz!r}") from exc
        if self.interval < 1:
            raise ValueError("interval must be at least 1")
        if self.total_doses is not None and self.total_doses < 1:
            raise ValueError("total_doses must be at least 1")

        if self.kind in DAY_BASED:
            if not self.times_of_day:
                raise ValueError(f"{self.kind} schedules need at least one time of day")
            if len(set(self.times_of_day)) != len(self.times_of_day):
                raise ValueError("times_of_day contains duplicates")
        if self.kind is ScheduleKind.WEEKLY:
            if not self.days_of_week:
                raise ValueError("weekly schedules need at least one day of the week")
            if any(d not in range(7) for d in self.days_of_week):
                raise ValueError("days_of_week values must be 0 (Mon) .. 6 (Sun)")


def expand(spec: ScheduleSpec, window_start: datetime, window_end: datetime) -> list[datetime]:
    """All dose times t with window_start <= t < window_end, as UTC datetimes, ascending.

    Also respects the schedule's own bounds: t >= starts_at, t < ends_at, and at
    most total_doses instances counted from starts_at.
    """
    _require_aware("window_start", window_start)
    _require_aware("window_end", window_end)
    if spec.kind is ScheduleKind.AS_NEEDED:
        return []

    lower = max(window_start, spec.starts_at)
    upper = window_end if spec.ends_at is None else min(window_end, spec.ends_at)
    if lower >= upper:
        return []

    rules = _rules(spec)
    if spec.total_doses is None:
        candidates = rules.between(lower, upper, inc=True)
    else:
        # A course of N doses is N doses of the whole schedule, not N per rule,
        # so count on the merged set — starting from starts_at, not the window.
        candidates = islice(rules.xafter(spec.starts_at, inc=True), spec.total_doses)

    seen: set[datetime] = set()
    out: list[datetime] = []
    for t in candidates:
        t = t.astimezone(UTC)
        if lower <= t < upper and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def grace_for(spec: ScheduleSpec, default: timedelta) -> timedelta:
    """How long after its time a dose stays 'due' before it counts as missed.

    For hourly schedules the grace can never reach the next dose: half the
    interval at most, so two doses are never 'due' at once.
    """
    if spec.kind is ScheduleKind.EVERY_N_HOURS:
        return min(default, timedelta(hours=spec.interval) / 2)
    return default


class DoseStatus(StrEnum):
    UPCOMING = "upcoming"
    DUE = "due"
    TAKEN = "taken"
    SKIPPED = "skipped"
    MISSED = "missed"


def dose_status(
    scheduled_at: datetime, *, now: datetime, grace: timedelta, logged: str | None
) -> DoseStatus:
    """Derive a dose's status; nothing here is ever stored."""
    if logged == DoseStatus.TAKEN:
        return DoseStatus.TAKEN
    if logged == DoseStatus.SKIPPED:
        return DoseStatus.SKIPPED
    if now < scheduled_at:
        return DoseStatus.UPCOMING
    if now <= scheduled_at + grace:
        return DoseStatus.DUE
    return DoseStatus.MISSED


def _rules(spec: ScheduleSpec) -> rruleset:
    rules = rruleset()
    if spec.kind is ScheduleKind.EVERY_N_HOURS:
        rules.rrule(rrule(HOURLY, interval=spec.interval, dtstart=spec.starts_at.astimezone(UTC)))
        return rules

    tz = ZoneInfo(spec.tz)
    # Anchor at local midnight of the start date so byhour/byminute pick the
    # clock times; rrule keeps the tzinfo, i.e. it iterates in wall-clock time.
    anchor = datetime.combine(spec.starts_at.astimezone(tz).date(), time(0), tzinfo=tz)
    for t in spec.times_of_day:
        common = {"dtstart": anchor, "byhour": t.hour, "byminute": t.minute, "bysecond": 0}
        if spec.kind is ScheduleKind.DAILY:
            rules.rrule(rrule(DAILY, **common))
        elif spec.kind is ScheduleKind.WEEKLY:
            rules.rrule(rrule(WEEKLY, byweekday=list(spec.days_of_week), **common))
        else:  # EVERY_N_DAYS: the anchor date is an "on" day, then every interval-th day
            rules.rrule(rrule(DAILY, interval=spec.interval, **common))
    return rules


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
