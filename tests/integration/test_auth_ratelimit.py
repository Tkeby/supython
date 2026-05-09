"""Tests for auth endpoint rate limiting."""

from datetime import UTC, datetime, timedelta

import pytest

from supython import db
from supython.auth import ratelimit
from supython.settings import get_settings


def test_window_start_is_stable_within_window() -> None:
    first = datetime(2026, 4, 25, 12, 0, 1, tzinfo=UTC)
    second = first + timedelta(seconds=58)

    assert ratelimit._window_start(60, now=first) == ratelimit._window_start(
        60, now=second
    )


def test_window_start_advances_across_boundary() -> None:
    first = datetime(2026, 4, 25, 12, 0, 59, tzinfo=UTC)
    second = first + timedelta(seconds=1)

    assert ratelimit._window_start(60, now=second) > ratelimit._window_start(
        60, now=first
    )


@pytest.mark.usefixtures("pool")
async def test_hit_counts_and_blocks_after_limit(monkeypatch: pytest.MonkeyPatch):
    starts = [
        datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        datetime(2026, 4, 25, 12, 1, tzinfo=UTC),
    ]

    def fake_window_start(_window_seconds: int) -> datetime:
        return starts.pop(0)

    monkeypatch.setattr(ratelimit, "_window_start", fake_window_start)
    rule = ratelimit.RateLimit(limit=2, window_seconds=60)

    async with db.as_service_role() as conn:
        assert await ratelimit.hit(conn, bucket="test:127.0.0.1", rule=rule) == (
            False,
            1,
        )
        assert await ratelimit.hit(conn, bucket="test:127.0.0.1", rule=rule) == (
            False,
            2,
        )
        assert await ratelimit.hit(conn, bucket="test:127.0.0.1", rule=rule) == (
            True,
            3,
        )
        assert await ratelimit.hit(conn, bucket="test:127.0.0.1", rule=rule) == (
            False,
            1,
        )


async def test_token_endpoint_returns_429_after_threshold(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "auth_rate_limit_token_per_window", 2)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 60)

    payload = {"email": "missing@example.com", "password": "wrongpassword"}
    first = await client.post("/auth/v1/token", json=payload)
    second = await client.post("/auth/v1/token", json=payload)
    third = await client.post("/auth/v1/token", json=payload)

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.headers["retry-after"] == "60"
    assert third.json()["detail"]["code"] == "rate_limited"
