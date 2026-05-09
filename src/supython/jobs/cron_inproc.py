"""Optional in-process cron scheduler (``croniter``-based).

Loaded only when ``jobs_cron_backend == 'inproc'``. ``croniter`` is an
optional extra — users opt in with ``pip install supython[cron-inproc]``
per the 2026-04-21 decision log row and §15.5 dependency budget.

Two bugs in the pre-grooming implementation were fixed here:

1. **Firing condition** — ``croniter.get_next(datetime)`` returns the next
   fire time strictly after its anchor, so the old ``next_fire <= now``
   test was never true. We now track a per-schedule ``_last_fire`` anchor
   and compare ``next_fire`` against the current ``now`` after the sleep.
2. **Advisory lock lifetime** — ``pg_advisory_lock`` is session-scoped, so
   acquiring on one pool connection and releasing on another leaks the
   lock forever. Both now happen on the same connection for a single
   cron tick.

   Every worker tries; one wins; the rest no-op. Belt-and-braces idempotency key
   `{cron_name}:{tick}` blocks duplicates even if the lock check races. Works,
   but every replica wakes up and contends every minute — fine for 2-5 workers,
   wasteful past that.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from .. import db
from ..settings import Settings
from .registry import CronDefinition, get_registry
from .service import enqueue

logger = logging.getLogger(__name__)


def _require_croniter() -> Any:
    try:
        import croniter  # type: ignore[import-not-found]

        return croniter
    except ImportError as exc:  # pragma: no cover — depends on extras
        raise ImportError(
            "croniter is required for in-process cron scheduling. "
            "Install with: pip install supython[cron-inproc]"
        ) from exc


class InProcScheduler:
    """croniter-based fallback scheduler.

    One tick per minute; at each tick, every registered cron expression that
    has moved past its next scheduled fire time enqueues a single job.
    Advisory-lock + idempotency-key form a belt-and-braces guard against
    duplicate enqueues across replicas.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._running = False
        self._last_fire: dict[str, datetime] = {}

    async def start(self) -> None:
        croniter_mod = _require_croniter()
        self._running = True

        registry = get_registry()

        # Seed the ``_last_fire`` map so that the first tick does not
        # retroactively fire schedules that would otherwise look "overdue"
        # after a process restart.
        now = datetime.now(UTC)
        for cron_defn in registry.iter_crons():
            if cron_defn.name not in self._last_fire:
                self._last_fire[cron_defn.name] = now

        while self._running:
            now = datetime.now(UTC)
            for cron_defn in registry.iter_crons():
                try:
                    anchor = self._last_fire.get(cron_defn.name, now)
                    cron = croniter_mod.croniter(cron_defn.cron_expr, anchor)
                    next_fire = cron.get_next(datetime)
                    if next_fire <= now:
                        fired = await self._try_fire(cron_defn, next_fire)
                        if fired:
                            self._last_fire[cron_defn.name] = next_fire
                except Exception:
                    logger.exception(
                        "jobs.cron.tick_error",
                        extra={"cron_name": cron_defn.name},
                    )

            await asyncio.sleep(60)

    async def stop(self) -> None:
        self._running = False

    async def _try_fire(self, cron_defn: CronDefinition, tick: datetime) -> bool:
        """Acquire-enqueue-release on one connection; skip if another worker has it."""
        async with db.as_service_role() as conn:
            locked = await conn.fetchval(
                "select pg_try_advisory_lock(hashtext($1))", cron_defn.name
            )
            if not locked:
                return False
            try:
                await enqueue(
                    conn,
                    name=cron_defn.job_name,
                    payload=cron_defn.payload,
                    queue=cron_defn.queue,
                    idempotency_key=f"{cron_defn.name}:{tick.isoformat()}",
                )
                return True
            finally:
                await conn.execute("select pg_advisory_unlock(hashtext($1))", cron_defn.name)
