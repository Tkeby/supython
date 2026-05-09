"""Backups module — pg_dump-based database backups, executed via the jobs queue."""

from . import _backup_job  # noqa: F401  — registers the @job handler at import time
from .schemas import BackupRecord
from .service import (
    BackupError,
    count_backups,
    generate_download_token,
    get_backup,
    list_backups,
    start_backup,
    verify_download_token,
)

__all__ = [
    "BackupError",
    "BackupRecord",
    "count_backups",
    "generate_download_token",
    "get_backup",
    "list_backups",
    "start_backup",
    "verify_download_token",
]
