from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
from fastapi import Header, HTTPException
from jose import jwt  # type: ignore[import-untyped]
from jose.exceptions import JWTError  # type: ignore[import-untyped]


@dataclass(frozen=True)
class AuthUser:
    clerk_user_id: str
    email: str


@lru_cache(maxsize=1)
def _jwks() -> dict[str, Any]:
    """Fetch and cache Clerk's JWKS for token verification.

    Clerk rotates rarely; cache once per process. For long-running prod with
    rotation, add a TTL refresh — fine for v1.
    """
    from glass.config import settings

    resp = httpx.get(settings.clerk_jwks_url, timeout=5.0)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


_DEV_USER = AuthUser(clerk_user_id="dev-user", email="dev@local")


def verify_token(authorization: str | None) -> AuthUser:
    from glass.config import settings

    # Dev bypass: accept any non-empty bearer string and return a fixed user.
    # Only safe because the backend is bound to a non-public interface when
    # this flag is set. Strip this for production.
    if settings.dev_mode:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing or malformed bearer token")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(status_code=401, detail="missing or malformed bearer token")
        return _DEV_USER

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing or malformed bearer token")

    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        jwks = _jwks()
        key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
        if not key:
            raise HTTPException(status_code=401, detail="unknown signing key")
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc

    sub = claims.get("sub")
    email = claims.get("email") or claims.get("primary_email_address") or ""
    if not sub:
        raise HTTPException(status_code=401, detail="token missing sub claim")
    return AuthUser(clerk_user_id=sub, email=email)


def current_user(authorization: str | None = Header(None)) -> AuthUser:
    """FastAPI dependency."""
    return verify_token(authorization)
