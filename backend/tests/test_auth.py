import pytest
from fastapi import HTTPException

from glass.auth import AuthUser, verify_token


def test_verify_token_rejects_missing_header() -> None:
    with pytest.raises(HTTPException) as exc:
        verify_token(None)
    assert exc.value.status_code == 401


def test_verify_token_rejects_empty_string() -> None:
    with pytest.raises(HTTPException) as exc:
        verify_token("")
    assert exc.value.status_code == 401


def test_verify_token_rejects_malformed_header() -> None:
    with pytest.raises(HTTPException) as exc:
        verify_token("NotBearer abc")
    assert exc.value.status_code == 401


def test_verify_token_rejects_bearer_without_token() -> None:
    with pytest.raises(HTTPException) as exc:
        verify_token("Bearer ")
    assert exc.value.status_code == 401


def test_authuser_dataclass() -> None:
    u = AuthUser(clerk_user_id="user_abc", email="o@example.com")
    assert u.clerk_user_id == "user_abc"
    assert u.email == "o@example.com"
