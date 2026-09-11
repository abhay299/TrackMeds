"""Who is calling? — verification of Supabase-issued JWTs.

The app signs in against Supabase Auth directly and sends the resulting access
token as `Authorization: Bearer <jwt>`. We never ask Supabase whether a token is
valid: it is signed with the project's private key, and Supabase publishes the
matching *public* keys at a JWKS URL. Verifying locally means one cached HTTP
fetch per key rotation, zero network calls per request, and auth that keeps
working even if Supabase Auth is briefly down.

Checks performed: signature (the token's `kid` header selects the JWKS key),
expiry, audience ("authenticated" = a signed-in user) and issuer (this
project's Auth URL — a token from someone else's Supabase project must fail).
Any failure → 401. The `sub` claim is the user's UUID and is the only identity
the rest of the API ever uses.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None


# auto_error=False so a missing header is *our* 401 (with WWW-Authenticate),
# not FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(jwks_url: str) -> PyJWKClient:
    # One per process. PyJWKClient caches the key set for `lifespan` seconds and
    # only refetches when it meets an unknown `kid`, i.e. after a key rotation.
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=600)


def get_jwks(settings: Annotated[Settings, Depends(get_settings)]) -> PyJWKClient:
    # A dependency rather than a direct call so tests can inject a fake key set.
    return _jwks_client(settings.jwks_url)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def verify_token(token: str, settings: Settings, jwks: PyJWKClient) -> AuthUser:
    try:
        key = jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            # Supabase's asymmetric keys are ES256 (P-256) by default, RS256 if you
            # pick RSA. The legacy HS256 shared secret is deliberately not accepted.
            algorithms=["ES256", "RS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        # Reason stays out of the response on purpose; it's in the server log.
        raise _unauthorized("invalid or expired token") from exc
    return AuthUser(id=claims["sub"], email=claims.get("email"))


def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
    jwks: Annotated[PyJWKClient, Depends(get_jwks)],
) -> AuthUser:
    # Deliberately a plain `def`: FastAPI runs sync dependencies in a thread pool,
    # so the (rare) blocking JWKS fetch inside PyJWKClient can't stall the event loop.
    if creds is None:
        raise _unauthorized("missing bearer token")
    return verify_token(creds.credentials, settings, jwks)


CurrentUser = Annotated[AuthUser, Depends(current_user)]
