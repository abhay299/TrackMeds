from datetime import timedelta

from tests.api.conftest import (
    FROZEN_NOW,
    USER_B,
    daily,
    every_n_days,
    ist_window,
    medication,
    new_id,
)


async def seed(api):
    """The plan's Phase 1 exit scenario, created at 10:00 IST on Thu 2026-09-11."""
    met = (
        await api.post("/medications", json=medication("Metformin", daily(["08:00", "20:00"])))
    ).json()
    vit = (
        await api.post("/medications", json=medication("Vitamin D3", every_n_days(2, ["09:00"])))
    ).json()
    return met, vit


def summary(doses: list[dict]) -> list[tuple[str, str, str]]:
    return [(d["medication_name"], d["scheduled_at"], d["status"]) for d in doses]


async def test_today_and_the_following_days(api):
    await seed(api)
    # Today: 08:00 and 09:00 were before creation, so only Metformin 20:00 remains.
    today = (await api.get("/doses", params=ist_window("2026-09-11"))).json()
    assert summary(today) == [("Metformin", "2026-09-11T14:30:00Z", "upcoming")]

    tomorrow = (await api.get("/doses", params=ist_window("2026-09-12"))).json()
    assert summary(tomorrow) == [
        ("Metformin", "2026-09-12T02:30:00Z", "upcoming"),
        ("Metformin", "2026-09-12T14:30:00Z", "upcoming"),
    ]
    # Every 2 days anchored on the creation date: the 13th is an "on" day.
    day_after = (await api.get("/doses", params=ist_window("2026-09-13"))).json()
    assert summary(day_after) == [
        ("Metformin", "2026-09-13T02:30:00Z", "upcoming"),
        ("Vitamin D3", "2026-09-13T03:30:00Z", "upcoming"),
        ("Metformin", "2026-09-13T14:30:00Z", "upcoming"),
    ]


async def test_statuses_follow_the_clock(api, clock):
    await seed(api)
    at = "2026-09-11T14:30:00Z"  # Metformin 20:00 IST
    clock.now = FROZEN_NOW.replace(hour=15)  # 20:30 IST: within the 2h grace
    assert summary((await api.get("/doses", params=ist_window("2026-09-11"))).json()) == [
        ("Metformin", at, "due")
    ]
    clock.now = FROZEN_NOW.replace(hour=17)  # 22:30 IST: grace over
    assert summary((await api.get("/doses", params=ist_window("2026-09-11"))).json()) == [
        ("Metformin", at, "missed")
    ]


async def test_log_take_then_change_to_skip_updates_the_same_record(api, clock):
    met, _ = await seed(api)
    sched_id = met["schedules"][0]["id"]
    at = "2026-09-11T14:30:00Z"
    clock.now = FROZEN_NOW.replace(hour=14, minute=35)

    r = await api.post(
        "/doses/log", json={"schedule_id": sched_id, "scheduled_at": at, "status": "taken"}
    )
    assert r.status_code == 201, r.text
    log = r.json()
    assert log["taken_at"] == "2026-09-11T14:35:00Z"  # defaulted to now
    doses = (await api.get("/doses", params=ist_window("2026-09-11"))).json()
    assert doses[0]["status"] == "taken" and doses[0]["log"]["id"] == log["id"]

    r = await api.post(
        "/doses/log",
        json={"schedule_id": sched_id, "scheduled_at": at, "status": "skipped", "note": "nausea"},
    )
    assert r.status_code == 201
    assert r.json()["id"] == log["id"]  # updated in place, not duplicated
    assert r.json()["taken_at"] is None
    doses = (await api.get("/doses", params=ist_window("2026-09-11"))).json()
    assert doses[0]["status"] == "skipped" and doses[0]["log"]["note"] == "nausea"


async def test_undo_restores_the_derived_status(api, clock):
    met, _ = await seed(api)
    sched_id = met["schedules"][0]["id"]
    clock.now = FROZEN_NOW.replace(hour=14, minute=35)
    log = (
        await api.post(
            "/doses/log",
            json={
                "schedule_id": sched_id,
                "scheduled_at": "2026-09-11T14:30:00Z",
                "status": "taken",
            },
        )
    ).json()
    assert (await api.delete(f"/doses/log/{log['id']}")).status_code == 204
    assert (await api.get("/doses", params=ist_window("2026-09-11"))).json()[0]["status"] == "due"
    assert (await api.delete(f"/doses/log/{log['id']}")).status_code == 404


async def test_late_log_keeps_the_scheduled_time_and_records_when_it_was_taken(api, clock):
    met, _ = await seed(api)
    sched_id = met["schedules"][0]["id"]
    clock.now = FROZEN_NOW + timedelta(days=1)
    r = await api.post(
        "/doses/log",
        json={
            "schedule_id": sched_id,
            "scheduled_at": "2026-09-11T14:30:00Z",
            "status": "taken",
            "taken_at": "2026-09-11T17:00:00Z",
        },
    )
    assert r.status_code == 201
    assert r.json()["scheduled_at"] == "2026-09-11T14:30:00Z"
    assert r.json()["taken_at"] == "2026-09-11T17:00:00Z"


async def test_log_rejects_times_the_schedule_never_produces(api):
    met, _ = await seed(api)
    sched_id = met["schedules"][0]["id"]
    r = await api.post(
        "/doses/log",
        json={"schedule_id": sched_id, "scheduled_at": "2026-09-11T14:31:00Z", "status": "taken"},
    )
    assert r.status_code == 422
    r = await api.post(
        "/doses/log",
        json={"schedule_id": sched_id, "scheduled_at": "2026-09-11T02:30:00Z", "status": "taken"},
    )
    assert r.status_code == 422  # 08:00 today was before the schedule started


async def test_log_rejects_doses_far_in_the_future(api):
    met, _ = await seed(api)
    sched_id = met["schedules"][0]["id"]
    r = await api.post(
        "/doses/log",
        json={"schedule_id": sched_id, "scheduled_at": "2026-09-12T14:30:00Z", "status": "taken"},
    )
    assert r.status_code == 422


async def test_other_users_schedules_cannot_be_logged(api, as_user):
    met, _ = await seed(api)
    as_user(USER_B)
    r = await api.post(
        "/doses/log",
        json={
            "schedule_id": met["schedules"][0]["id"],
            "scheduled_at": "2026-09-11T14:30:00Z",
            "status": "taken",
        },
    )
    assert r.status_code == 404
    assert (await api.get("/doses", params=ist_window("2026-09-11"))).json() == []


async def test_unknown_schedule_is_404(api):
    r = await api.post(
        "/doses/log",
        json={"schedule_id": new_id(), "scheduled_at": "2026-09-11T14:30:00Z", "status": "taken"},
    )
    assert r.status_code == 404


async def test_history_survives_a_schedule_edit(api, clock):
    met, _ = await seed(api)
    old_id = met["schedules"][0]["id"]
    clock.now = FROZEN_NOW.replace(hour=14, minute=35)
    await api.post(
        "/doses/log",
        json={"schedule_id": old_id, "scheduled_at": "2026-09-11T14:30:00Z", "status": "taken"},
    )

    clock.now = FROZEN_NOW + timedelta(days=2)
    new = (await api.put(f"/schedules/{old_id}", json=daily(["09:00"]))).json()

    # The 11th still shows the old version's dose, taken; the 14th follows the new version.
    assert summary((await api.get("/doses", params=ist_window("2026-09-11"))).json()) == [
        ("Metformin", "2026-09-11T14:30:00Z", "taken")
    ]
    later = (await api.get("/doses", params=ist_window("2026-09-14"))).json()
    assert [
        (d["scheduled_at"], d["schedule_id"]) for d in later if d["medication_name"] == "Metformin"
    ] == [("2026-09-14T03:30:00Z", new["id"])]


async def test_archived_medication_has_no_doses(api):
    met, _ = await seed(api)
    await api.delete(f"/medications/{met['id']}")
    assert [
        d["medication_name"]
        for d in (await api.get("/doses", params=ist_window("2026-09-12"))).json()
    ] == []


async def test_window_validation(api):
    base = ist_window("2026-09-11")
    assert (
        await api.get("/doses", params={"from": base["to"], "to": base["from"]})
    ).status_code == 422
    assert (
        await api.get("/doses", params={"from": base["from"], "to": "2026-12-31T00:00:00+05:30"})
    ).status_code == 422
    assert (
        await api.get("/doses", params={"from": "2026-09-11T00:00:00", "to": "2026-09-12T00:00:00"})
    ).status_code == 422
