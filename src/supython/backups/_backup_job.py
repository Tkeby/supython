"""Job handler for admin database backups.

Registered with the jobs framework so backups inherit retries, backoff,
visibility timeout, and observability instead of running as one-shot
asyncio tasks tied to the FastAPI process lifetime.

Two execution modes (selected via ``settings.backup_via``):

* ``host``   — invoke ``pg_dump`` from the worker's PATH and use ``-f file``.
               Suitable for production where ``postgresql-client`` is bundled
               in the worker image.
* ``docker`` — ``docker exec`` into the running postgres container and stream
               pg_dump's stdout into a host-side file. Suitable for the
               bundled docker-compose dev setup; no host install required and
               the pg_dump version always matches the server.

Payload shape:
    {"backup_id": "<uuid>", "kind": "full" | "schema-only", "file_path": "<abs path>"}
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from uuid import UUID

from ..jobs.decorators import job
from ..settings import get_settings
from .service import _parse_db_url

JOB_NAME = "admin_backup_run"


def _build_args(*, kind: str, file_path: str) -> tuple[list[str], dict[str, str], bool]:
    """Compose the argv, env, and "stream stdout to file?" flag.

    Returns (args, env, stream_stdout). When ``stream_stdout`` is True the
    caller must capture stdout into ``file_path`` itself (used for the
    docker-exec path, where ``-f`` would write inside the container).
    """
    settings = get_settings()
    db_info = _parse_db_url(settings.database_url)
    env = os.environ.copy()

    if settings.backup_via == "docker":
        container = settings.backup_docker_container
        if not container:
            raise RuntimeError(
                "BACKUP_DOCKER_CONTAINER is required when BACKUP_VIA=docker. "
                "Set it to the name of your postgres container (for scaffolded "
                "projects this is typically '<project>-db', e.g. 'igo-db'), or "
                "switch to BACKUP_VIA=host."
            )
        args = [
            "docker",
            "exec",
            "-i",
            "-e",
            f"PGPASSWORD={db_info['password']}",
            container,
            "pg_dump",
            "-U",
            db_info["user"],
            "-d",
            db_info["dbname"],
            "--no-owner",
            "--no-acl",
        ]
        if kind == "schema-only":
            args.append("--schema-only")
        return args, env, True

    args = [
        "pg_dump",
        "-h",
        db_info["host"],
        "-p",
        db_info["port"],
        "-U",
        db_info["user"],
        "-d",
        db_info["dbname"],
        "--no-owner",
        "--no-acl",
        "-f",
        file_path,
    ]
    if kind == "schema-only":
        args.append("--schema-only")
    env["PGPASSWORD"] = db_info["password"]
    return args, env, False


@job(
    JOB_NAME,
    max_attempts=2,
    backoff="exponential",
    backoff_base_s=30.0,
    backoff_max_s=300.0,
)
async def admin_backup_run(ctx, payload: dict) -> None:
    backup_id = UUID(payload["backup_id"])
    kind: str = payload["kind"]
    file_path: str = payload["file_path"]

    timeout_s = get_settings().backup_timeout_s

    await ctx.db.execute(
        """
        update admin.backups
        set status = 'running', error_message = null
        where id = $1
        """,
        backup_id,
    )

    try:
        args, env, stream_stdout = _build_args(kind=kind, file_path=file_path)

        with contextlib.ExitStack() as stack:
            out_file = stack.enter_context(open(file_path, "wb")) if stream_stdout else None
            proc = await asyncio.create_subprocess_exec(
                *args,
                env=env,
                stdout=out_file if out_file is not None else asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except TimeoutError as exc:
                proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
                raise RuntimeError(f"pg_dump timed out after {timeout_s}s") from exc

        if proc.returncode != 0:
            error_text = stderr.decode(errors="replace")[:2000] or "pg_dump failed"
            raise RuntimeError(error_text)

        file_size = os.path.getsize(file_path)
        await ctx.db.execute(
            """
            update admin.backups
            set status = 'completed',
                size = $2,
                file_path = $3,
                finished_at = now()
            where id = $1
            """,
            backup_id,
            file_size,
            file_path,
        )

    except Exception as exc:
        with contextlib.suppress(OSError):
            os.unlink(file_path)
        await ctx.db.execute(
            """
            update admin.backups
            set status = 'failed',
                error_message = $2,
                finished_at = now()
            where id = $1
            """,
            backup_id,
            str(exc)[:2000],
        )
        raise
