"""Database administration helpers."""

import asyncpg


async def rotate_role_password(conn: asyncpg.Connection, role: str, password: str) -> None:
    quoted = "'" + password.replace("'", "''") + "'"
    await conn.execute(f"alter role {role} with password {quoted}")
