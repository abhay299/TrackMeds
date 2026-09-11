"""The recurrence engine is pure, so every rule that matters gets a direct test.

Conventions: IST = Asia/Kolkata (UTC+5:30, no DST); NY = America/New_York
(DST starts 2026-03-08). `utc()` builds aware UTC datetimes tersely.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.recurrence import (
    UTC,
    DoseStatus,
    ScheduleKind,
    ScheduleSpec,
    dose_status,
    expand,
    grace_for,
)

IST = "Asia/Kolkata"
NY = "America/New_York"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def local(tz: str, *args: int) -> datetime:
    return datetime(*args, tzinfo=ZoneInfo(tz))


# --- daily -----------------------------------------------------------------


def test_daily_two_times_over_three_days():
    spec = ScheduleSpec(
        ScheduleKind.DAILY, IST, starts_at=local(IST, 2026, 9, 11), times_of_day=(time(8), time(20))
    )
    out = expand(spec, local(IST, 2026, 9, 11), local(IST, 2026, 9, 14))
    assert out == [
        utc(2026, 9, 11, 2, 30), utc(2026, 9, 11, 14, 30),
        utc(2026, 9, 12, 2, 30), utc(2026, 9, 12, 14, 30),
        utc(2026, 9, 13, 2, 30), utc(2026, 9, 13, 14, 30),
    ]  # fmt: skip


def test_starts_at_is_effective_from_not_start_of_day():
    # Created at 10:00 local: today's 08:00 has passed and must not appear.
    spec = ScheduleSpec(
        ScheduleKind.DAILY,
        IST,
        starts_at=local(IST, 2026, 9, 11, 10),
        times_of_day=(time(8), time(20)),
    )
    out = expand(spec, local(IST, 2026, 9, 11), local(IST, 2026, 9, 12))
    assert out == [utc(2026, 9, 11, 14, 30)]


def test_two_times_do_not_cross_multiply():
    # 08:00 and 20:30 must yield exactly those — not 08:30 and 20:00 as well.
    spec = ScheduleSpec(
        ScheduleKind.DAILY,
        IST,
        starts_at=local(IST, 2026, 9, 11),
        times_of_day=(time(8), time(20, 30)),
    )
    out = expand(spec, local(IST, 2026, 9, 11), local(IST, 2026, 9, 12))
    assert [t.astimezone(ZoneInfo(IST)).strftime("%H:%M") for t in out] == ["08:00", "20:30"]


def test_daily_wall_clock_survives_dst():
    # 08:00 New York on 7, 8, 9 March 2026: EST, then EDT from the 8th.
    spec = ScheduleSpec(
        ScheduleKind.DAILY, NY, starts_at=local(NY, 2026, 3, 7), times_of_day=(time(8),)
    )
    out = expand(spec, local(NY, 2026, 3, 7), local(NY, 2026, 3, 10))
    assert out == [utc(2026, 3, 7, 13), utc(2026, 3, 8, 12), utc(2026, 3, 9, 12)]
    assert {t.astimezone(ZoneInfo(NY)).hour for t in out} == {8}


# --- weekly ----------------------------------------------------------------


def test_weekly_mon_wed_fri():
    # 2026-09-14 is a Monday.
    spec = ScheduleSpec(
        ScheduleKind.WEEKLY, IST, starts_at=local(IST, 2026, 9, 14),
        times_of_day=(time(9),), days_of_week=(0, 2, 4),
    )  # fmt: skip
    out = expand(spec, local(IST, 2026, 9, 14), local(IST, 2026, 9, 28))
    assert [t.astimezone(ZoneInfo(IST)).strftime("%a %d") for t in out] == [
        "Mon 14", "Wed 16", "Fri 18", "Mon 21", "Wed 23", "Fri 25",
    ]  # fmt: skip


# --- every N days ------------------------------------------------------------


def test_every_2_days_anchor_parity_across_month_boundary():
    spec = ScheduleSpec(
        ScheduleKind.EVERY_N_DAYS, IST, starts_at=local(IST, 2026, 9, 29),
        times_of_day=(time(9),), interval=2,
    )  # fmt: skip
    out = expand(spec, local(IST, 2026, 9, 28), local(IST, 2026, 10, 6))
    assert [t.astimezone(ZoneInfo(IST)).strftime("%m-%d") for t in out] == [
        "09-29", "10-01", "10-03", "10-05",
    ]  # fmt: skip


def test_every_2_days_across_dst_keeps_wall_clock():
    spec = ScheduleSpec(
        ScheduleKind.EVERY_N_DAYS,
        NY,
        starts_at=local(NY, 2026, 3, 6),
        times_of_day=(time(8),),
        interval=2,
    )
    out = expand(spec, local(NY, 2026, 3, 6), local(NY, 2026, 3, 12))
    assert out == [utc(2026, 3, 6, 13), utc(2026, 3, 8, 12), utc(2026, 3, 10, 12)]


# --- every N hours -------------------------------------------------------------


def test_every_6_hours_course_of_20_doses():
    start = local(IST, 2026, 9, 11, 7)
    spec = ScheduleSpec(
        ScheduleKind.EVERY_N_HOURS, IST, starts_at=start, interval=6, total_doses=20
    )
    out = expand(spec, start - timedelta(days=1), start + timedelta(days=30))
    assert len(out) == 20
    assert out[0] == start.astimezone(UTC)
    assert all((b - a) == timedelta(hours=6) for a, b in zip(out, out[1:], strict=False))
    assert out[-1] == start.astimezone(UTC) + timedelta(hours=6 * 19)


def test_course_window_returns_only_the_overlap():
    start = local(IST, 2026, 9, 11, 7)
    spec = ScheduleSpec(
        ScheduleKind.EVERY_N_HOURS, IST, starts_at=start, interval=6, total_doses=20
    )
    out = expand(spec, start + timedelta(days=1), start + timedelta(days=2))
    assert len(out) == 4
    assert out[0] == start.astimezone(UTC) + timedelta(hours=24)


def test_hourly_intervals_stay_exact_across_dst():
    start = local(NY, 2026, 3, 7, 20)
    spec = ScheduleSpec(ScheduleKind.EVERY_N_HOURS, NY, starts_at=start, interval=6)
    out = expand(spec, start, start + timedelta(hours=24))
    assert [(b - a) for a, b in zip(out, out[1:], strict=False)] == [timedelta(hours=6)] * 3


# --- bounds ------------------------------------------------------------------


def test_course_of_doses_counts_across_times_of_day():
    spec = ScheduleSpec(
        ScheduleKind.DAILY, IST, starts_at=local(IST, 2026, 9, 11),
        times_of_day=(time(8), time(20)), total_doses=5,
    )  # fmt: skip
    out = expand(spec, local(IST, 2026, 9, 1), local(IST, 2026, 10, 1))
    assert [t.astimezone(ZoneInfo(IST)).strftime("%d %H") for t in out] == [
        "11 08", "11 20", "12 08", "12 20", "13 08",
    ]  # fmt: skip


def test_ends_at_is_exclusive():
    spec = ScheduleSpec(
        ScheduleKind.DAILY, IST, starts_at=local(IST, 2026, 9, 11),
        ends_at=local(IST, 2026, 9, 13, 8), times_of_day=(time(8),),
    )  # fmt: skip
    out = expand(spec, local(IST, 2026, 9, 1), local(IST, 2026, 10, 1))
    assert out == [utc(2026, 9, 11, 2, 30), utc(2026, 9, 12, 2, 30)]


def test_window_start_inclusive_window_end_exclusive():
    spec = ScheduleSpec(
        ScheduleKind.DAILY, IST, starts_at=local(IST, 2026, 9, 1), times_of_day=(time(8),)
    )
    out = expand(spec, utc(2026, 9, 11, 2, 30), utc(2026, 9, 12, 2, 30))
    assert out == [utc(2026, 9, 11, 2, 30)]


def test_as_needed_has_no_instances():
    spec = ScheduleSpec(ScheduleKind.AS_NEEDED, IST, starts_at=local(IST, 2026, 9, 11))
    assert expand(spec, local(IST, 2026, 1, 1), local(IST, 2027, 1, 1)) == []


def test_empty_window_before_start():
    spec = ScheduleSpec(
        ScheduleKind.DAILY, IST, starts_at=local(IST, 2026, 9, 11), times_of_day=(time(8),)
    )
    assert expand(spec, local(IST, 2026, 9, 1), local(IST, 2026, 9, 10)) == []


# --- validation ------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": ScheduleKind.DAILY, "times_of_day": ()},
        {"kind": ScheduleKind.WEEKLY, "times_of_day": (time(9),), "days_of_week": ()},
        {"kind": ScheduleKind.WEEKLY, "times_of_day": (time(9),), "days_of_week": (7,)},
        {"kind": ScheduleKind.DAILY, "times_of_day": (time(8), time(8))},
        {"kind": ScheduleKind.EVERY_N_HOURS, "interval": 0},
        {"kind": ScheduleKind.DAILY, "times_of_day": (time(8),), "total_doses": 0},
        {"kind": ScheduleKind.DAILY, "times_of_day": (time(8),), "tz": "Mars/Olympus"},
        {
            "kind": ScheduleKind.DAILY,
            "times_of_day": (time(8),),
            "starts_at": datetime(2026, 9, 11),
        },
    ],
)
def test_invalid_specs_are_rejected(kwargs):
    base = {"tz": IST, "starts_at": local(IST, 2026, 9, 11)}
    with pytest.raises(ValueError):
        ScheduleSpec(**{**base, **kwargs})


# --- status ------------------------------------------------------------------------


def test_dose_status_transitions():
    at = utc(2026, 9, 11, 8)
    grace = timedelta(hours=2)
    assert (
        dose_status(at, now=at - timedelta(minutes=1), grace=grace, logged=None)
        is DoseStatus.UPCOMING
    )
    assert dose_status(at, now=at, grace=grace, logged=None) is DoseStatus.DUE
    assert dose_status(at, now=at + grace, grace=grace, logged=None) is DoseStatus.DUE
    assert (
        dose_status(at, now=at + grace + timedelta(seconds=1), grace=grace, logged=None)
        is DoseStatus.MISSED
    )
    assert (
        dose_status(at, now=at + timedelta(days=3), grace=grace, logged="taken") is DoseStatus.TAKEN
    )
    assert (
        dose_status(at, now=at - timedelta(days=3), grace=grace, logged="skipped")
        is DoseStatus.SKIPPED
    )


def test_hourly_grace_never_reaches_the_next_dose():
    hourly = ScheduleSpec(
        ScheduleKind.EVERY_N_HOURS, IST, starts_at=local(IST, 2026, 9, 11), interval=2
    )
    daily = ScheduleSpec(
        ScheduleKind.DAILY, IST, starts_at=local(IST, 2026, 9, 11), times_of_day=(time(8),)
    )
    assert grace_for(hourly, timedelta(hours=2)) == timedelta(hours=1)
    assert grace_for(daily, timedelta(hours=2)) == timedelta(hours=2)
