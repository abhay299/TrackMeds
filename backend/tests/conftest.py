"""Test fixtures.

Auth is tested for real: we generate an ES256 key pair, mint tokens exactly the
way Supabase would (same claims, same header), and hand the API a fake JWKS
client that serves the public key. Nothing touches the network, and every check
in `verify_token` (signature, exp, aud, iss) is exercised against genuine
cryptography rather than mocked away.
"""

import os
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

# Settings are read lazily, so this runs before the app ever instantiates them.
# Unit tests get placeholders; environment variables outrank `.env`, so in
# integration mode we leave them unset and let Settings read the real `.env`.
if not os.environ.get("TRACKMEDS_INTEGRATION"):
    os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@localhost:5432/test")

from app.core.config import get_settings  # noqa: E402
from app.core.security import get_jwks  # noqa: E402
from app.main import app  # noqa: E402

USER_ID = "00000000-0000-0000-0000-000000000001"


class FakeJWKS:
    """Stands in for PyJWKClient: always returns our test public key."""

    def __init__(self, public_key) -> None:
        self._key = public_key

    def get_signing_key_from_jwt(self, token: str):  # noqa: ARG002
        return SimpleNamespace(key=self._key)


@pytest.fixture(scope="session")
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def make_token(signing_key):
    def _make(key=None, **overrides) -> str:
        s = get_settings()
        now = int(time.time())
        claims = {
            "sub": USER_ID,
            "email": "abhay@example.com",
            "role": "authenticated",
            "aud": s.jwt_audience,
            "iss": s.jwt_issuer,
            "iat": now,
            "exp": now + 3600,
        }
        claims.update(overrides)
        return jwt.encode(claims, key or signing_key, algorithm="ES256", headers={"kid": "test"})

    return _make


@pytest.fixture
async def client(signing_key) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_jwks] = lambda: FakeJWKS(signing_key.public_key())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
