"""Shared email dispatcher.

Routes email through the jobs queue when jobs are enabled and a caller
connection is available, otherwise falls back to synchronous send.
"""

import asyncpg

from .mailer import EmailMessage, get_mailer
from .settings import get_settings


async def dispatch(
    conn: asyncpg.Connection | None,
    msg: EmailMessage,
    *,
    job_name: str = "send_email",
) -> None:
    """Send an email, via the jobs queue when enabled and a conn is available.

    Falls back to synchronous ``mailer.send()`` otherwise.
    """
    s = get_settings()
    if s.jobs_enabled and conn is not None:
        from .jobs import service as _jobs_svc

        await _jobs_svc.enqueue(
            conn,
            name=job_name,
            payload=msg.model_dump(),
        )
        return
    await get_mailer().send(msg)
