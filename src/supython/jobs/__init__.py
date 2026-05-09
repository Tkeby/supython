"""Jobs module — durable job queue with cron scheduling."""

from .backends import get_backend
from .context import JobCtx
from .decorators import job
from .registry import get_registry
from .router import router
from .schemas import EnqueueResult, JobResponse
from .service import JobError, enqueue
from .worker import Worker


def get_worker() -> Worker:
    from ..settings import get_settings

    return Worker(get_settings())


__all__ = [
    "Worker",
    "enqueue",
    "get_backend",
    "get_registry",
    "get_worker",
    "job",
    "JobCtx",
    "JobError",
    "JobResponse",
    "EnqueueResult",
    "router",
]
