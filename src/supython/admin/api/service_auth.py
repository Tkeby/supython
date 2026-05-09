from datetime import datetime
from uuid import UUID

import asyncpg

from ..errors import AdminError


async def authenticate(
    conn: asyncpg.Connection, email: str, password: str
) -> tuple[UUID, str]:
    """Verify credentials and return (admin_id, email).

    Raises AdminError("invalid_credentials", 401) on bad email/password.
    """
    from ... import passwords

    row = await conn.fetchrow(
        """
        select id, email, password_hash
        from admin.admin_users
        where email = $1
        """,
        email,
    )
    if not row or not passwords.verify_password(row["password_hash"], password):
        raise AdminError("invalid_credentials", "Invalid credentials", 401)
    return row["id"], row["email"]


async def touch_last_login(conn: asyncpg.Connection, admin_id: UUID) -> None:
    await conn.execute(
        "update admin.admin_users set last_login_at = now() where id = $1",
        admin_id,
    )


async def fetch_admin(
    conn: asyncpg.Connection, admin_id: UUID
) -> tuple[str, datetime | None] | None:
    row = await conn.fetchrow(
        """
        select email, last_login_at
        from admin.admin_users
        where id = $1
        """,
        admin_id,
    )
    return (row["email"], row["last_login_at"]) if row else None
