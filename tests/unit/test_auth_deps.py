"""Tests for the public FastAPI auth dependencies — pure Python, no DB."""

import uuid

import pytest
from fastapi import HTTPException, status

from supython.auth import current_claims, current_user_id
from tests._keys import make_token


async def test_current_claims_decodes_bearer_token():
    uid = uuid.uuid4()
    token = make_token(user_id=uid, email="alice@test.com")
    claims = await current_claims(authorization=f"Bearer {token}")
    assert claims["sub"] == str(uid)
    assert claims["email"] == "alice@test.com"
    assert claims["role"] == "authenticated"


async def test_current_claims_accepts_lowercase_bearer():
    token = make_token()
    claims = await current_claims(authorization=f"bearer {token}")
    assert "sub" in claims


async def test_current_claims_missing_header_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await current_claims(authorization=None)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing bearer token" in exc_info.value.detail


async def test_current_claims_wrong_scheme_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await current_claims(authorization="Basic abc123")
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


async def test_current_claims_invalid_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await current_claims(authorization="Bearer not-a-real-jwt")
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid token" in exc_info.value.detail


async def test_current_user_id_extracts_uuid():
    uid = uuid.uuid4()
    out = await current_user_id(claims={"sub": str(uid)})
    assert out == uid


async def test_current_user_id_missing_sub_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await current_user_id(claims={})
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "sub" in exc_info.value.detail


async def test_current_user_id_malformed_sub_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await current_user_id(claims={"sub": "not-a-uuid"})
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
