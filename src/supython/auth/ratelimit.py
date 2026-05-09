"""Postgres-backed fixed-window rate limiter shared by auth endpoints."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


def _window_start(window_seconds: int, *, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % window_seconds), tz=UTC)


async def hit(
    conn: asyncpg.Connection, *, bucket: str, rule: RateLimit
) -> tuple[bool, int]:
    """Increment the counter for ``bucket``. Returns ``(blocked, count)``."""
    count = await conn.fetchval(
        """
        insert into auth.rate_limit_buckets as b (bucket, window_start, count)
        values ($1, $2, 1)
        on conflict (bucket, window_start) do update
            set count = b.count + 1
        returning b.count
        """,
        bucket,
        _window_start(rule.window_seconds),
    )
    return count > rule.limit, count
