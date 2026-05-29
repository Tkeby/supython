"""Decorators for registering jobs and cron schedules."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from enum import StrEnum
from typing import Any

from .registry import CronDefinition, JobDefinition, get_registry

Handler = Callable[..., Coroutine[Any, Any, None]]


class Backoff(StrEnum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    CONSTANT = "constant"


def job(
    name: str,
    *,
    version: int = 1,
    max_attempts: int = 3,
    backoff: Backoff | str = Backoff.EXPONENTIAL,
    backoff_base_s: float = 5.0,
    backoff_max_s: float = 300.0,
    queue: str = "default",
    role: str = "service_role",
    claims_from: str | None = None,
    accepts_payload: bool = True,
) -> Callable[..., Any]:
    def decorator(fn: Handler) -> Handler:
        get_registry().register_job(
            JobDefinition(
                name=name,
                version=version,
                handler=fn,
                max_attempts=max_attempts,
                backoff=backoff if isinstance(backoff, str) else backoff.value,
                backoff_base_s=backoff_base_s,
                backoff_max_s=backoff_max_s,
                queue=queue,
                role=role,
                claims_from=claims_from,
                accepts_payload=accepts_payload,
            )
        )
        return fn

    return decorator


def cron(
    cron_expr: str,
    *,
    name: str,
    job_name: str | None = None,
    job_version: int = 1,
    payload: dict | None = None,
    queue: str = "default",
    register_handler: bool = True,
    max_attempts: int = 3,
    backoff: Backoff | str = Backoff.EXPONENTIAL,
    backoff_base_s: float = 5.0,
    backoff_max_s: float = 300.0,
    role: str = "service_role",
    claims_from: str | None = None,
    accepts_payload: bool = True,
) -> Callable[..., Any]:
    """Schedule the decorated function on a cron expression.

    By default the decorated function is also registered as the handler for
    ``job_name`` so pg_cron's tick → ``jobs.enqueue`` → worker dispatch
    round-trip works without a separate ``@job`` declaration. Pass
    ``register_handler=False`` when the schedule should fire a job whose
    handler lives elsewhere (declared with ``@job``).
    """
    resolved_job_name = job_name or name

    def decorator(fn: Handler) -> Handler:
        registry = get_registry()
        registry.register_cron(
            CronDefinition(
                name=name,
                cron_expr=cron_expr,
                job_name=resolved_job_name,
                job_version=job_version,
                payload=payload or {},
                queue=queue,
            )
        )
        if register_handler:
            registry.register_job(
                JobDefinition(
                    name=resolved_job_name,
                    version=job_version,
                    handler=fn,
                    max_attempts=max_attempts,
                    backoff=backoff if isinstance(backoff, str) else backoff.value,
                    backoff_base_s=backoff_base_s,
                    backoff_max_s=backoff_max_s,
                    queue=queue,
                    role=role,
                    claims_from=claims_from,
                    accepts_payload=accepts_payload,
                )
            )
        return fn

    return decorator
