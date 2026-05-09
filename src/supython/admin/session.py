import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

SESSION_COOKIE = "supython_admin"
SESSION_PATH = "/admin"
SESSION_TTL = timedelta(hours=8)


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


async def issue(
    conn: asyncpg.Connection, *, admin_id: UUID, ip: str | None, ua: str | None
) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + SESSION_TTL
    await conn.execute(
        """
        insert into admin.admin_sessions (admin_id, token_hash, expires_at, ip, user_agent)
        values ($1, $2, $3, $4, $5)
        """,
        admin_id, _hash(raw), expires, ip, ua,
    )
    return raw, expires


async def resolve(
    conn: asyncpg.Connection, raw: str
) -> tuple[UUID, datetime] | None:
    row = await conn.fetchrow(
        """
        select admin_id, expires_at
        from admin.admin_sessions
        where token_hash = $1
          and revoked_at is null
          and expires_at > now()
        """,
        _hash(raw),
    )
    return (row["admin_id"], row["expires_at"]) if row else None


async def revoke(conn: asyncpg.Connection, raw: str) -> None:
    await conn.execute(
        "update admin.admin_sessions set revoked_at = now() where token_hash = $1",
        _hash(raw),
    )