"""Job and cron definitions registry (process-global singleton)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobDefinition:
    name: str
    handler: Callable[..., Coroutine[Any, Any, None]] = field(repr=False)
    version: int = 1
    max_attempts: int = 3
    backoff: str = "exponential"
    backoff_base_s: float = 5.0
    backoff_max_s: float = 300.0
    queue: str = "default"
    role: str = "service_role"
    claims_from: str | None = None
    accepts_payload: bool = True


@dataclass
class CronDefinition:
    name: str
    cron_expr: str
    job_name: str
    job_version: int = 1
    payload: dict = field(default_factory=dict)
    queue: str = "default"


class Registry:
    def __init__(self) -> None:
        self._jobs: dict[tuple[str, int], JobDefinition] = {}
        self._crons: dict[str, CronDefinition] = {}

    def register_job(self, defn: JobDefinition) -> None:
        key = (defn.name, defn.version)
        if key in self._jobs:
            raise ValueError(f"job {defn.name!r} v{defn.version} already registered")
        self._jobs[key] = defn

    def register_cron(self, defn: CronDefinition) -> None:
        if defn.name in self._crons:
            raise ValueError(f"cron {defn.name!r} already registered")
        self._crons[defn.name] = defn

    def get(self, name: str, version: int) -> JobDefinition | None:
        return self._jobs.get((name, version))

    def get_latest(self, name: str) -> JobDefinition | None:
        versions = [v for (n, v) in self._jobs if n == name]
        if not versions:
            return None
        return self._jobs[(name, max(versions))]

    def iter_jobs(self):
        return iter(self._jobs.values())

    def iter_crons(self):
        return iter(self._crons.values())


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None
