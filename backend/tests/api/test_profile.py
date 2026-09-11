async def test_profile_is_created_on_first_contact_with_device_timezone(api):
    r = await api.get("/me")
    assert r.status_code == 200
    body = r.json()
    assert body["tz"] == "Asia/Kolkata"
    assert body["missed_grace_minutes"] == 120


async def test_profile_can_be_updated(api):
    r = await api.patch("/me", json={"display_name": "Abhay", "missed_grace_minutes": 90})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Abhay"
    assert r.json()["missed_grace_minutes"] == 90
    assert (await api.get("/me")).json()["missed_grace_minutes"] == 90


async def test_unknown_timezone_is_rejected(api):
    r = await api.patch("/me", json={"tz": "Mars/Olympus"})
    assert r.status_code == 422
