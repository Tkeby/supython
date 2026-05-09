"""Job execution context — mirrors ``functions.context.Ctx`` for worker jobs.

``HookCtx`` and ``build_hook_ctx`` used to live here; they moved to
``supython.hooks`` so feature modules (auth, storage, ...) can fire hooks
without importing the jobs package. This file now only owns the job-side
context.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from ..functions.context import PostgrestClient, StorageClient, _make_send_email
from ..mailer import EmailBackend, get_mailer
from ..settings import Settings, get_settings
from ..storage.backends import StorageBackend, get_backend


@dataclass
class JobCtx:
    db: asyncpg.Connection
    settings: Settings
    send_email: Callable[..., Awaitable[None]]
    storage: StorageClient
    postgrest: PostgrestClient
    logger: logging.Logger
    job_id: UUID | None = None
    attempt: int = 0
    name: str = ""


def build_job_ctx(
    *,
    conn: asyncpg.Connection,
    job_id: UUID | None = None,
    attempt: int = 0,
    name: str = "",
    backend: StorageBackend | None = None,
    mailer: EmailBackend | None = None,
    settings: Settings | None = None,
) -> JobCtx:
    s = settings or get_settings()
    return JobCtx(
        db=conn,
        settings=s,
        send_email=_make_send_email(mailer or get_mailer()),
        storage=StorageClient(conn, backend or get_backend()),
        postgrest=PostgrestClient(s.postgrest_url, None),
        logger=logging.getLogger(f"supython.jobs.{name}"),
        job_id=job_id,
        attempt=attempt,
        name=name,
    )
