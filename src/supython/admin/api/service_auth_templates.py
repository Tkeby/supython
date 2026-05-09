"""Raw SQL helpers for email template CRUD — no Pydantic, no FastAPI."""

from datetime import datetime, timezone

import asyncpg

from ..errors import AdminError
from ..schemas import EmailTemplate


async def list_templates(conn: asyncpg.Connection) -> list[EmailTemplate]:
    rows = await conn.fetch(
        """
        select name, subject, text_body, updated_at
        from admin.email_templates
        order by name
        """
    )
    return [
        EmailTemplate(
            name=row["name"],
            subject=row["subject"],
            text_body=row["text_body"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


async def get_template(conn: asyncpg.Connection, name: str) -> EmailTemplate:
    row = await conn.fetchrow(
        """
        select name, subject, text_body, updated_at
        from admin.email_templates
        where name = $1
        """,
        name,
    )
    if row is None:
        raise AdminError("not_found", f"template {name!r} not found", 404)
    return EmailTemplate(
        name=row["name"],
        subject=row["subject"],
        text_body=row["text_body"],
        updated_at=row["updated_at"],
    )


async def update_template(
    conn: asyncpg.Connection,
    name: str,
    subject: str | None,
    text_body: str | None,
) -> EmailTemplate:
    """Patch one or both fields. Returns the updated row."""
    existing = await conn.fetchrow(
        "select subject, text_body from admin.email_templates where name = $1",
        name,
    )
    if existing is None:
        raise AdminError("not_found", f"template {name!r} not found", 404)

    new_subject = subject if subject is not None else existing["subject"]
    new_body = text_body if text_body is not None else existing["text_body"]

    row = await conn.fetchrow(
        """
        update admin.email_templates
        set subject = $2, text_body = $3, updated_at = $4
        where name = $1
        returning name, subject, text_body, updated_at
        """,
        name,
        new_subject,
        new_body,
        datetime.now(tz=timezone.utc),
    )
    return EmailTemplate(
        name=row["name"],
        subject=row["subject"],
        text_body=row["text_body"],
        updated_at=row["updated_at"],
    )
