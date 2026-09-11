import os

import pytest


async def test_health_is_public(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_health_db_requires_auth(client):
    r = await client.get("/health/db")
    assert r.status_code == 401


@pytest.mark.skipif(
    not os.environ.get("TRACKMEDS_INTEGRATION"),
    reason="needs a real DATABASE_URL; run with TRACKMEDS_INTEGRATION=1",
)
async def test_health_db_reaches_supabase(client, make_token):
    # Integration check for Phase 0's exit criterion: pooler host, TLS, credentials.
    r = await client.get("/health/db", headers={"Authorization": f"Bearer {make_token()}"})
    assert r.status_code == 200, r.text
    assert r.json()["database"] == "reachable"


async def test_cors_allows_expo_web_dev_origin(client):
    r = await client.options(
        "/me",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-timezone",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8081"


async def test_cors_rejects_unknown_origin(client):
    r = await client.options(
        "/me",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers
