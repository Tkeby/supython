import json
from typing import Any
from uuid import UUID

import asyncpg


async def write(
    conn: asyncpg.Connection,
    *,
    admin_id: UUID | None,
    action: str,
    target: str | None,
    payload: dict[str, Any],
    ip: str | None,
    ua: str | None,
) -> None:
    await conn.execute(
        """
        insert into admin.admin_audit (admin_id, action, target, payload, ip, user_agent)
        values ($1, $2, $3, $4::jsonb, $5, $6)
        """,
        admin_id,
        action,
        target,
        json.dumps(payload),
        ip,
        ua,
    )
