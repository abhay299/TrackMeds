from datetime import timedelta

from tests.api.conftest import FROZEN_NOW, USER_B, daily, every_n_days, medication, new_id


async def test_create_returns_medication_with_its_schedule(api):
    r = await api.post("/medications", json=medication("Metformin", daily(["08:00", "20:00"])))
    assert r.status_code == 201, r.text
    med = r.json()
    assert med["name"] == "Metformin"
    assert len(med["schedules"]) == 1
    s = med["schedules"][0]
    assert s["kind"] == "daily"
    assert s["times_of_day"] == ["08:00:00", "20:00:00"]
    # created "now": effective immediately, never from the start of the day
    assert s["starts_at"] == FROZEN_NOW.isoformat().replace("+00:00", "Z")
    assert s["ends_at"] is None


async def test_future_start_date_becomes_local_midnight(api):
    r = await api.post(
        "/medications", json=medication("Later", daily(["09:00"], start_date="2026-09-15"))
    )
    assert r.status_code == 201
    assert r.json()["schedules"][0]["starts_at"] == "2026-09-14T18:30:00Z"  # 00:00 IST


async def test_end_date_is_inclusive(api):
    r = await api.post(
        "/medications", json=medication("Course", daily(["09:00"], end_date="2026-09-20"))
    )
    assert r.status_code == 201
    assert (
        r.json()["schedules"][0]["ends_at"] == "2026-09-20T18:30:00Z"
    )  # midnight after the 20th, IST


async def test_list_orders_by_name_and_hides_archived(api):
    await api.post("/medications", json=medication("Vitamin D3", every_n_days(2, ["09:00"])))
    await api.post("/medications", json=medication("Metformin", daily(["08:00"])))
    names = [m["name"] for m in (await api.get("/medications")).json()]
    assert names == ["Metformin", "Vitamin D3"]

    med_id = (await api.get("/medications")).json()[0]["id"]
    assert (await api.delete(f"/medications/{med_id}")).status_code == 204
    assert [m["name"] for m in (await api.get("/medications")).json()] == ["Vitamin D3"]
    archived = (await api.get("/medications", params={"archived": "true"})).json()
    assert [m["name"] for m in archived] == ["Metformin"]
    assert archived[0]["schedules"] == []


async def test_patch_changes_details_but_not_schedules(api):
    med = (await api.post("/medications", json=medication("Metfromin", daily(["08:00"])))).json()
    r = await api.patch(
        f"/medications/{med['id']}", json={"name": "Metformin", "notes": "with food"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Metformin"
    assert r.json()["notes"] == "with food"
    assert r.json()["schedules"] == med["schedules"]


async def test_other_users_medications_are_invisible(api, as_user):
    med = (await api.post("/medications", json=medication("Metformin", daily(["08:00"])))).json()
    as_user(USER_B)
    assert (await api.get("/medications")).json() == []
    assert (await api.get(f"/medications/{med['id']}")).status_code == 404
    assert (await api.patch(f"/medications/{med['id']}", json={"name": "x"})).status_code == 404
    assert (await api.delete(f"/medications/{med['id']}")).status_code == 404
    sched_id = med["schedules"][0]["id"]
    assert (await api.delete(f"/schedules/{sched_id}")).status_code == 404


async def test_unknown_medication_is_404(api):
    assert (await api.get(f"/medications/{new_id()}")).status_code == 404


async def test_second_schedule_for_the_same_medicine(api):
    med = (await api.post("/medications", json=medication("Insulin", daily(["08:00"])))).json()
    night = {**daily(["21:00"]), "dose_amount": 2, "dose_unit": "unit"}
    r = await api.post(f"/medications/{med['id']}/schedules", json=night)
    assert r.status_code == 201
    med = (await api.get(f"/medications/{med['id']}")).json()
    assert [(s["times_of_day"], s["dose_amount"]) for s in med["schedules"]] == [
        (["08:00:00"], "1.000"),
        (["21:00:00"], "2.000"),
    ]


async def test_replace_ends_old_version_and_links_new_one(api, clock):
    med = (await api.post("/medications", json=medication("Metformin", daily(["08:00"])))).json()
    old = med["schedules"][0]
    clock.now = FROZEN_NOW + timedelta(days=3)  # the old version has produced doses by now

    r = await api.put(f"/schedules/{old['id']}", json=daily(["08:00", "20:00"]))
    assert r.status_code == 200
    new = r.json()
    assert new["replaces_schedule_id"] == old["id"]
    assert new["starts_at"] == clock.now.isoformat().replace("+00:00", "Z")

    current = (await api.get(f"/medications/{med['id']}")).json()["schedules"]
    assert [s["id"] for s in current] == [new["id"]]  # old one is ended, not listed

    # replacing an ended version again is refused
    assert (await api.put(f"/schedules/{old['id']}", json=daily(["09:00"]))).status_code == 409


async def test_replacing_a_schedule_that_never_started_leaves_no_trace(api):
    med = (
        await api.post(
            "/medications", json=medication("Later", daily(["09:00"], start_date="2026-10-01"))
        )
    ).json()
    old = med["schedules"][0]
    new = (
        await api.put(f"/schedules/{old['id']}", json=daily(["10:00"], start_date="2026-10-01"))
    ).json()
    assert new["replaces_schedule_id"] is None  # nothing to point back to: it was deleted
    assert (await api.delete(f"/schedules/{old['id']}")).status_code == 404


async def test_end_schedule(api, clock):
    med = (await api.post("/medications", json=medication("Metformin", daily(["08:00"])))).json()
    clock.now = FROZEN_NOW + timedelta(days=1)
    assert (await api.delete(f"/schedules/{med['schedules'][0]['id']}")).status_code == 204
    assert (await api.get(f"/medications/{med['id']}")).json()["schedules"] == []


async def test_invalid_schedules_are_422(api):
    bad = [
        {**daily([]), "kind": "daily"},  # no times
        {**daily(["09:00"]), "kind": "weekly"},  # weekly without days
        {**daily(["09:00"]), "tz": "Mars/Olympus"},
        {**daily(["09:00"]), "dose_amount": 0},
        {**daily(["09:00"]), "end_date": "2026-09-01"},  # ends before it starts
        {**daily(["09:00", "09:00"])},  # duplicate time
    ]
    for schedule in bad:
        r = await api.post("/medications", json=medication("X", schedule))
        assert r.status_code == 422, schedule
