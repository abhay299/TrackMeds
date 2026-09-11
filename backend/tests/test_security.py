import time

from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import get_settings
from app.core.security import verify_token
from tests.conftest import USER_ID, FakeJWKS


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_yields_the_user_identity(signing_key, make_token):
    # The verify step is exercised directly: no HTTP, no database. The endpoints
    # that consume the identity are covered by the API tests.
    user = verify_token(make_token(), get_settings(), FakeJWKS(signing_key.public_key()))
    assert user.id == USER_ID
    assert user.email == "abhay@example.com"


async def test_missing_token_is_401_with_challenge(client):
    r = await client.get("/me")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_expired_token_rejected(client, make_token):
    r = await client.get("/me", headers=auth(make_token(exp=int(time.time()) - 60)))
    assert r.status_code == 401


async def test_wrong_audience_rejected(client, make_token):
    # e.g. an "anon" token, or one minted for some other purpose
    r = await client.get("/me", headers=auth(make_token(aud="anon")))
    assert r.status_code == 401


async def test_token_from_another_project_rejected(client, make_token):
    r = await client.get(
        "/me", headers=auth(make_token(iss="https://someone-else.supabase.co/auth/v1"))
    )
    assert r.status_code == 401


async def test_forged_signature_rejected(client, make_token):
    # Right claims, wrong private key — the signature check must catch it.
    r = await client.get(
        "/me", headers=auth(make_token(key=ec.generate_private_key(ec.SECP256R1())))
    )
    assert r.status_code == 401


async def test_garbage_token_rejected(client):
    r = await client.get("/me", headers=auth("not.a.jwt"))
    assert r.status_code == 401
