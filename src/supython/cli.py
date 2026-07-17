"""supython CLI."""

import asyncio
import concurrent.futures
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import asyncpg
import httpx
import typer
import uvicorn

from . import jwks, keyset, secretset, tokens
from . import migrate as migrate_mod
from .db_admin import rotate_role_password
from .gen import render_types_py, render_types_ts
from .logging_config import configure_logging
from .scaffold import scaffold
from .settings import Settings, export_env_file, get_settings

app = typer.Typer(
    help="supython — lightweight Postgres-first BaaS for Python",
    no_args_is_help=True,
)

functions_cli = typer.Typer(help="Manage edge functions.")
app.add_typer(functions_cli, name="functions")

gen_cli = typer.Typer(help="Code generation (types, SDKs, ...).")
app.add_typer(gen_cli, name="gen")

realtime_cli = typer.Typer(help="Manage the realtime change-data-capture surface.")
app.add_typer(realtime_cli, name="realtime")

worker_cli = typer.Typer(help="Run and manage the background job worker.")
app.add_typer(worker_cli, name="worker")

jobs_cli = typer.Typer(help="Manage background jobs.")
app.add_typer(jobs_cli, name="jobs")

cron_cli = typer.Typer(help="Manage cron schedules.")
app.add_typer(cron_cli, name="cron")

keygen_cli = typer.Typer(
    help="Manage JWT signing keys (generate, rotate, activate, prune).",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(keygen_cli, name="keygen")

test_cli = typer.Typer(
    help="Manage the integration test database (isolated from `supython up`).",
    no_args_is_help=True,
)
app.add_typer(test_cli, name="test")

secret_cli = typer.Typer(
    help="Manage symmetric secrets (storage signed URLs, OAuth state).",
    no_args_is_help=True,
)
app.add_typer(secret_cli, name="secret")

password_cli = typer.Typer(
    help="Rotate Postgres role passwords.",
    no_args_is_help=True,
)
app.add_typer(password_cli, name="password")

admin_cli = typer.Typer(
    help="Manage admin users (the operator surface for /admin/api/*).",
    no_args_is_help=True,
)
app.add_typer(admin_cli, name="admin")

_ASYMMETRIC_ALGS = {"RS256", "ES256"}
_PRIVATE_JWK_MEMBERS = frozenset({"d", "p", "q", "dp", "dq", "qi", "k"})
_REQUIRED_ROLES = ("anon", "authenticated", "service_role", "authenticator")
_REQUIRED_EXTENSIONS = ("pgcrypto", "citext")
_RECOMMENDED_EXTENSIONS = ("pg_cron",)
_MIN_PG_VERSION = 14
_ROLE_ATTRIBUTES: dict[str, dict[str, bool]] = {
    "authenticator": {"rolcanlogin": True},
    "service_role": {"rolbypassrls": True},
    "anon": {"rolcanlogin": False},
    "authenticated": {"rolcanlogin": False},
}
_FRAMEWORK_SCHEMAS = ("auth", "storage", "realtime", "jobs", "supython")


@dataclass
class _DoctorReport:
    ok: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def merge(self, other: "_DoctorReport") -> None:
        self.ok.extend(other.ok)
        self.warnings.extend(other.warnings)
        self.failures.extend(other.failures)


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run a coroutine, working around an already-running event loop (e.g. pytest-asyncio)."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


def _bootstrap_user_modules() -> None:
    """Import the user's settings module + extensions so decorators register.

    Mirrors ``worker_run`` and ``create_app``. CLI subcommands that read the
    in-process registry (e.g. ``cron list``, ``cron sync``) must call this
    first, otherwise the registry is empty and a ``cron sync`` would wipe
    every row from ``jobs.cron_schedules``.
    """
    from .extensions import load_extensions
    from .settings_module import UserSettings, load_user_settings

    export_env_file()
    s = get_settings()
    user = load_user_settings(s.settings_module) if s.settings_module else UserSettings()
    load_extensions([*s.extensions, *user.extensions])


@gen_cli.command("types")
def gen_types(
    lang: str = typer.Option("py", "--lang", help="Target language (`py` or `ts`)."),
    schema: list[str] = typer.Option(  # noqa: B008  (typer reads call at decoration time)
        ["public"],
        "--schema",
        help="Schema to introspect. Repeatable: --schema public --schema auth.",
    ),
    out: Path | None = typer.Option(  # noqa: B008
        None,
        "--out",
        help="Output file path. Defaults to db_schema.py (py) or types.ts (ts).",
    ),
) -> None:
    """Emit typed code mirroring the live Postgres schema."""
    if lang == "py":
        out_path = out or Path("db_schema.py")
        renderer = render_types_py
    elif lang == "ts":
        out_path = out or Path("types.ts")
        renderer = render_types_ts
    else:
        raise typer.BadParameter("--lang must be 'py' or 'ts'")

    try:
        src = _run_async(renderer(schemas=schema))
    except (OSError, asyncpg.PostgresError) as exc:
        typer.echo(f"error: could not connect to database: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if out_path.parent and str(out_path.parent) not in ("", "."):
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(src)
    typer.echo(f"wrote {out_path} ({len(src.splitlines())} lines) for schemas {schema}")


@realtime_cli.command("enable")
def realtime_enable(
    table: str = typer.Argument(
        ...,
        help="Fully qualified table name, e.g. `public.todos`.",
        metavar="SCHEMA.TABLE",
    ),
    owner_column: str = typer.Option(
        "user_id",
        "--owner-column",
        help=(
            "Column whose value identifies the row's owner. Used to gate "
            "DELETE events (the row is gone, so we fall back to matching "
            "old_record.<owner_column> against auth.uid())."
        ),
    ),
    no_owner_column: bool = typer.Option(
        False,
        "--no-owner-column",
        help=(
            "Disable the DELETE owner-column fallback. DELETE events on this "
            "table will only fan out to service_role listeners."
        ),
    ),
) -> None:
    """Opt a table into realtime change feeds (wraps `realtime.enable(...)`)."""
    from .realtime.schemas import EnabledTable, EnableTableRequest
    from .realtime.service import RealtimeError, enable_table

    try:
        payload = EnableTableRequest(
            table=table,
            owner_column=None if no_owner_column else owner_column,
        )
    except ValueError as exc:
        typer.echo(f"error: invalid table name {table!r}: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    s = get_settings()

    async def _run() -> EnabledTable:
        conn = await asyncpg.connect(s.database_url)
        try:
            return await enable_table(conn, payload)
        finally:
            await conn.close()

    try:
        enabled = _run_async(_run())
    except RealtimeError as exc:
        typer.echo(f"error: {exc.code}: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc
    except (OSError, asyncpg.PostgresError) as exc:
        typer.echo(f"error: could not connect to database: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    pk = ",".join(enabled.pk_columns) or "<none>"
    owner = enabled.owner_column or "<none>"
    typer.echo(
        f"enabled {enabled.schema_name}.{enabled.table_name} (pk={pk}, owner_column={owner})"
    )


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


@worker_cli.command("run")
def worker_run(
    queue: str = typer.Option("default", "--queue", help="Queue to consume."),
    concurrency: int = typer.Option(5, "--concurrency", help="Max concurrent jobs."),
    batch_size: int = typer.Option(10, "--batch-size", help="Poll batch size."),
) -> None:
    """Start the background job worker (blocks until SIGTERM)."""
    import signal

    from . import db
    from .extensions import load_extensions
    from .jobs.worker import Worker
    from .settings_module import UserSettings, load_user_settings

    export_env_file()
    s = get_settings()
    configure_logging(s.log_level, json_format=s.log_json)
    s.jobs_queue_default = queue
    s.jobs_concurrency = concurrency
    user = load_user_settings(s.settings_module) if s.settings_module else UserSettings()
    load_extensions([*s.extensions, *user.extensions])
    worker = Worker(s)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(signum, frame):
        loop.create_task(worker.stop())

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    typer.echo(f"worker {worker.worker_id} starting (queue={queue})")
    try:
        loop.run_until_complete(db.init_pool())
        try:
            loop.run_until_complete(worker.start())
        except KeyboardInterrupt:
            loop.run_until_complete(worker.stop())
    finally:
        try:
            loop.run_until_complete(db.close_pool())
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Jobs CLI
# ---------------------------------------------------------------------------


@jobs_cli.command("list")
def jobs_list(
    status: str | None = typer.Option(None, "--status", help="Filter by status."),
    queue: str | None = typer.Option(None, "--queue", help="Filter by queue."),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List queued/running/finished jobs."""
    from .jobs.service import list_jobs

    s = get_settings()

    async def _run():
        conn = await asyncpg.connect(s.database_url)
        try:
            await conn.execute("set role service_role")
            return await list_jobs(conn, status=status, queue=queue, limit=limit)
        finally:
            await conn.close()

    records = _run_async(_run())
    if not records:
        typer.echo("no jobs found.")
        return
    for r in records:
        typer.echo(f"  {r.id}  {r.name:<30} {r.status:<12} attempts={r.attempts}")


@jobs_cli.command("show")
def jobs_show(
    job_id: str = typer.Argument(..., help="Job UUID."),
) -> None:
    """Show details for a single job."""
    from uuid import UUID

    from .jobs.service import get_job

    s = get_settings()

    async def _run():
        conn = await asyncpg.connect(s.database_url)
        try:
            await conn.execute("set role service_role")
            return await get_job(conn, UUID(job_id))
        finally:
            await conn.close()

    record = _run_async(_run())
    if record is None:
        typer.echo(f"job {job_id} not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"  id:         {record.id}")
    typer.echo(f"  name:       {record.name}")
    typer.echo(f"  version:    {record.version}")
    typer.echo(f"  status:     {record.status}")
    typer.echo(f"  attempts:   {record.attempts}/{record.max_attempts}")
    typer.echo(f"  queue:      {record.queue}")
    typer.echo(f"  payload:    {record.payload}")
    typer.echo(f"  created_at: {record.created_at}")


@jobs_cli.command("cancel")
def jobs_cancel(
    job_id: str = typer.Argument(..., help="Job UUID."),
) -> None:
    """Cancel a queued or running job."""
    from uuid import UUID

    from .jobs.service import JobError, cancel

    s = get_settings()

    async def _run():
        conn = await asyncpg.connect(s.database_url)
        try:
            await conn.execute("set role service_role")
            await cancel(conn, UUID(job_id))
        finally:
            await conn.close()

    try:
        _run_async(_run())
        typer.echo(f"cancelled {job_id}")
    except JobError as exc:
        typer.echo(f"error: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc


@jobs_cli.command("retry")
def jobs_retry(
    job_id: str = typer.Argument(..., help="Job UUID."),
) -> None:
    """Re-queue a failed job for retry."""
    from uuid import UUID

    from .jobs.service import JobError
    from .jobs.service import retry as retry_job

    s = get_settings()

    async def _run():
        conn = await asyncpg.connect(s.database_url)
        try:
            await conn.execute("set role service_role")
            await retry_job(conn, UUID(job_id))
        finally:
            await conn.close()

    try:
        _run_async(_run())
        typer.echo(f"re-queued {job_id}")
    except JobError as exc:
        typer.echo(f"error: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc


@jobs_cli.command("enqueue")
def jobs_enqueue(
    name: str = typer.Argument(..., help="Job name."),
    payload: str = typer.Option("{}", "--payload", help="JSON payload."),
    queue: str = typer.Option("default", "--queue"),
) -> None:
    """Enqueue a job manually."""
    import json as _json

    from .jobs.service import enqueue

    s = get_settings()

    async def _run():
        conn = await asyncpg.connect(s.database_url)
        try:
            await conn.execute("set role service_role")
            return await enqueue(conn, name=name, payload=_json.loads(payload), queue=queue)
        finally:
            await conn.close()

    result = _run_async(_run())
    typer.echo(f"enqueued {result.job.id} (is_new={result.is_new})")


# ---------------------------------------------------------------------------
# Cron CLI
# ---------------------------------------------------------------------------


@cron_cli.command("list")
def cron_list() -> None:
    """List registered cron schedules."""
    from .jobs.registry import get_registry

    _bootstrap_user_modules()
    crons = list(get_registry().iter_crons())
    if not crons:
        typer.echo("no crons registered.")
        return
    for c in crons:
        typer.echo(f"  {c.name:<30} {c.cron_expr:<20} → {c.job_name}")


@cron_cli.command("sync")
def cron_sync(
    allow_empty: bool = typer.Option(
        False,
        "--allow-empty",
        help=(
            "Allow sync to proceed when the in-process registry has no @cron "
            "definitions but `jobs.cron_schedules` has rows. Without this "
            "flag the sync refuses, because it would otherwise wipe every "
            "row and unschedule every pg_cron entry."
        ),
    ),
) -> None:
    """Sync registered crons with pg_cron."""
    from .jobs.cron import sync_pg_cron

    _bootstrap_user_modules()
    s = get_settings()

    async def _run():
        conn = await asyncpg.connect(s.database_url)
        try:
            await conn.execute("set role service_role")
            await sync_pg_cron(conn, allow_empty=allow_empty)
        finally:
            await conn.close()

    try:
        _run_async(_run())
        typer.echo("cron schedules synced.")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def init(
    name: str = typer.Argument(
        ..., help="Project package name — the importable Python package for the app."
    ),
    directory: str | None = typer.Argument(
        None,
        help="Target directory ('.' for the current directory). Defaults to ./<name>.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Scaffold a new supython project.

    \b
    Examples:
      supython init myapp          create ./myapp/ and scaffold into it
      supython init myapp .        scaffold into the current directory
      supython init myapp ./srv    scaffold into ./srv
    """
    into_existing = directory is not None
    target = Path.cwd() / name if directory is None else Path(directory).resolve()
    try:
        written = scaffold(
            name=name, target=target, force=force, allow_existing=into_existing
        )
    except FileExistsError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for p in written:
        try:
            shown = p.relative_to(Path.cwd())
        except ValueError:
            shown = p
        typer.echo(f"  wrote {shown}")
    typer.echo("")
    typer.echo("next steps:")
    if target != Path.cwd():
        try:
            typer.echo(f"  cd {target.relative_to(Path.cwd())}")
        except ValueError:
            typer.echo(f"  cd {target}")
    typer.echo("  supython up && supython dev   # .env and JWT keys were generated for you")


def _keygen_init_impl(
    *,
    alg: str,
    out_private: Path,
    out_jwks: Path,
    kid: str | None,
    force: bool,
) -> None:
    try:
        jwt_alg = _asymmetric_alg(alg)
        signer = _generate_jwt_files(
            alg=jwt_alg,
            out_private=out_private,
            out_jwks=out_jwks,
            kid=kid,
            force=force,
        )
    except (FileExistsError, OSError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"wrote private key: {out_private}")
    typer.echo(f"wrote JWKS:        {out_jwks}")
    typer.echo(f"kid:               {signer.kid}")
    typer.echo("")
    typer.echo("set these env vars:")
    typer.echo(f"  JWT_ALG={signer.alg}")
    typer.echo(f"  JWT_PRIVATE_KEY_PATH={out_private}")
    typer.echo(f"  JWT_KID={signer.kid}")
    typer.echo(f"  JWT_JWKS_PATH={out_jwks}")


@keygen_cli.callback()
def keygen_root(
    ctx: typer.Context,
    alg: str = typer.Option("RS256", "--alg", help="JWT algorithm: RS256 or ES256."),
    out_private: Path = typer.Option(  # noqa: B008
        Path("./.supython/jwt_private.pem"),
        "--out-private",
        help="Private key output path (init/back-compat only).",
    ),
    out_jwks: Path = typer.Option(  # noqa: B008
        Path("./.supython/jwks.json"),
        "--out-jwks",
        help="Public JWKS output path (init/back-compat only).",
    ),
    kid: str | None = typer.Option(None, "--kid", help="Key ID. Defaults to JWK thumbprint."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Generate a JWT signing keypair and public JWKS.

    Calling `supython keygen` with no subcommand runs the legacy single-key
    behavior (alias for `supython keygen init`). Use the `rotate`, `activate`,
    and `prune` subcommands for zero-downtime key rotation.
    """
    if ctx.invoked_subcommand is not None:
        return
    _keygen_init_impl(
        alg=alg,
        out_private=out_private,
        out_jwks=out_jwks,
        kid=kid,
        force=force,
    )


@keygen_cli.command("init")
def keygen_init(
    alg: str = typer.Option("RS256", "--alg", help="JWT algorithm: RS256 or ES256."),
    out_private: Path = typer.Option(  # noqa: B008
        Path("./.supython/jwt_private.pem"),
        "--out-private",
        help="Private key output path.",
    ),
    out_jwks: Path = typer.Option(  # noqa: B008
        Path("./.supython/jwks.json"),
        "--out-jwks",
        help="Public JWKS output path.",
    ),
    kid: str | None = typer.Option(None, "--kid", help="Key ID. Defaults to JWK thumbprint."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Generate a single JWT signing keypair + public JWKS (legacy layout)."""
    _keygen_init_impl(
        alg=alg,
        out_private=out_private,
        out_jwks=out_jwks,
        kid=kid,
        force=force,
    )


@keygen_cli.command("rotate")
def keygen_rotate(
    alg: str = typer.Option("RS256", "--alg", help="JWT algorithm: RS256 or ES256."),
    no_reload: bool = typer.Option(
        False,
        "--no-reload",
        help="Skip the best-effort `docker compose kill -s SIGUSR2 postgrest`.",
    ),
) -> None:
    """Add a new kid in `verifying` status; do NOT change the active signer.

    On the first run after a legacy single-key setup, the existing private key
    is imported into the keyset directory + manifest.
    """
    try:
        jwt_alg = _asymmetric_alg(alg)
        legacy = keyset.import_legacy_single_key()
        if legacy is not None:
            typer.echo(f"imported legacy single key as kid={legacy.kid} (status=active)")
        entry = keyset.add_key(jwt_alg, status="verifying")
        jwks.clear_cache()
        s = get_settings()
        jwks_doc = jwks.write_current_jwks(s.jwt_jwks_path)
    except (FileExistsError, OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    kids = ", ".join(key["kid"] for key in jwks_doc["keys"])
    typer.echo(f"added kid={entry.kid} ({entry.alg}, status=verifying)")
    typer.echo(f"wrote JWKS: {s.jwt_jwks_path} (kids={kids})")
    if not no_reload:
        _postgrest_reload()
    typer.echo(
        f"next: wait for PostgREST replicas to reload JWKS (>=30s), then "
        f"`supython keygen activate {entry.kid}`"
    )


@keygen_cli.command("activate")
def keygen_activate(
    kid: str = typer.Argument(..., help="Kid to make the active signing key."),
    no_reload: bool = typer.Option(
        False,
        "--no-reload",
        help="Skip the best-effort `docker compose kill -s SIGUSR2 postgrest`.",
    ),
) -> None:
    """Flip the active signing kid; previous active becomes `retired`."""
    try:
        keyset.activate(kid)
        jwks.clear_cache()
        s = get_settings()
        jwks_doc = jwks.write_current_jwks(s.jwt_jwks_path)
    except (FileNotFoundError, KeyError, OSError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    kids = ", ".join(key["kid"] for key in jwks_doc["keys"])
    typer.echo(f"active kid is now {kid}")
    typer.echo(f"wrote JWKS: {s.jwt_jwks_path} (kids={kids})")
    if not no_reload:
        _postgrest_reload()
    typer.echo(
        "supython service must be restarted (or `JWT_KID` set in the environment) "
        f"to begin signing under {kid}"
    )


@keygen_cli.command("prune")
def keygen_prune(
    force: bool = typer.Option(
        False,
        "--force",
        help="Drop all retired kids regardless of `JWT_ROTATION_GRACE_SECONDS`.",
    ),
    no_reload: bool = typer.Option(
        False,
        "--no-reload",
        help="Skip the best-effort `docker compose kill -s SIGUSR2 postgrest`.",
    ),
) -> None:
    """Drop retired kids whose grace window has elapsed."""
    try:
        removed = keyset.prune(force_all=force)
        jwks.clear_cache()
        s = get_settings()
        jwks_doc = jwks.write_current_jwks(s.jwt_jwks_path)
    except (OSError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not removed:
        typer.echo("no retired kids past the grace window; nothing pruned")
        return
    for kid in removed:
        typer.echo(f"pruned kid={kid}")
    kids = ", ".join(key["kid"] for key in jwks_doc["keys"]) or "(none)"
    typer.echo(f"wrote JWKS: {s.jwt_jwks_path} (kids={kids})")
    if not no_reload:
        _postgrest_reload()


def _postgrest_reload() -> None:
    """Best-effort SIGUSR2 to PostgREST so it reloads JWKS. Non-fatal on failure."""
    files = [None]
    if Path("docker-compose.prod.yml").exists():
        files.append("docker-compose.prod.yml")

    for compose_file in files:
        cmd = ["docker", "compose"]
        if compose_file:
            cmd += ["-f", compose_file]
        cmd += ["kill", "-s", "SIGUSR2", "postgrest"]
        try:
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        except FileNotFoundError:
            typer.echo(
                "warn: docker not found; skipped PostgREST reload (verify with `supython doctor`)"
            )
            return
        if result.returncode == 0:
            typer.echo("sent SIGUSR2 to postgrest (JWKS hot-reload)")
            return

    typer.echo(
        "warn: PostgREST reload failed; verify with `supython doctor` "
        "(or pass --no-reload if PostgREST runs outside Docker)"
    )


# ---------------------------------------------------------------------------
# Secret CLI
# ---------------------------------------------------------------------------


def _secret_name(value: str) -> secretset.SecretName:
    if value == "storage":
        return "storage_signed_url"
    if value == "oauth":
        return "oauth_state"
    raise typer.BadParameter("must be 'storage' or 'oauth'")


@secret_cli.command("status")
def secret_status() -> None:
    """Show symmetric secret manifest state."""
    try:
        manifest = secretset.load_manifest()
    except (OSError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if manifest is None:
        typer.echo("no manifest found")
        return

    for name in ("storage_signed_url", "oauth_state"):
        section = manifest.get(name)
        if section is None:
            typer.echo(f"{name}: (not in manifest)")
            continue
        active_kid = section.get("active")
        for key in section.get("keys", []):
            prefix = "* " if key["kid"] == active_kid else "  "
            retired = f"  retired_at={key.get('retired_at')}" if key.get("retired_at") else ""
            typer.echo(
                f"{prefix}{name}  kid={key['kid']}  status={key['status']}"
                f"  created_at={key.get('created_at')}{retired}"
            )


@secret_cli.command("rotate")
def secret_rotate(
    name: str = typer.Argument(..., help="Secret to rotate: storage | oauth"),
) -> None:
    """Add a new verifying secret."""
    secret_name = _secret_name(name)
    try:
        entry = secretset.rotate(secret_name)
        secretset.clear_cache()
    except (OSError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"added kid={entry.kid} ({secret_name}, status=verifying)")
    typer.echo(f"next: `supython secret activate {name} {entry.kid}`")


@secret_cli.command("activate")
def secret_activate(
    name: str = typer.Argument(..., help="Secret to activate: storage | oauth"),
    kid: str = typer.Argument(..., help="Kid to promote to active."),
) -> None:
    """Promote verifying secret to active."""
    secret_name = _secret_name(name)
    try:
        secretset.activate(secret_name, kid)
        secretset.clear_cache()
    except (FileNotFoundError, KeyError, OSError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"active kid is now {kid} for {secret_name}")
    typer.echo(f"next: restart supython replicas so new payloads are signed under {kid}")


@secret_cli.command("prune")
def secret_prune(
    name: str = typer.Argument(..., help="Secret to prune: storage | oauth"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Drop all retired secrets regardless of grace window.",
    ),
) -> None:
    """Drop retired secrets past the grace window."""
    secret_name = _secret_name(name)
    try:
        removed = secretset.prune(secret_name, force_all=force)
        secretset.clear_cache()
    except (OSError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not removed:
        typer.echo("no retired secrets past the grace window; nothing pruned")
        return
    for kid in removed:
        typer.echo(f"pruned kid={kid}")


# ---------------------------------------------------------------------------
# Password rotate CLI
# ---------------------------------------------------------------------------


def _update_dotenv_key(key: str, value: str) -> bool:
    """Update a key in ``.env`` if the file exists. Returns whether modified."""
    env_path = Path(".env")
    if not env_path.exists():
        return False
    lines = env_path.read_text().splitlines()
    modified = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            modified = True
            break
    if modified:
        env_path.write_text("\n".join(lines) + "\n")
    return modified


@password_cli.command("rotate")
def password_rotate(
    role: str = typer.Argument(..., help="Postgres role to rotate."),
    db_url: str | None = typer.Option(
        None, "--db-url", help="Privileged Postgres URL. Defaults to settings.database_url."
    ),
    generate: bool = typer.Option(True, help="Generate a strong random password."),
    password: str | None = typer.Option(None, help="Explicit new password (skips generation)."),
    no_confirm: bool = typer.Option(False, "--no-confirm", help="Skip confirmation prompt for CI."),
) -> None:
    """Rotate a Postgres role password."""
    if password is None and generate:
        if not no_confirm:
            confirm = typer.confirm(f"Generate and set a new password for role '{role}'?")
            if not confirm:
                raise typer.Abort()
        password = __import__("secrets").token_urlsafe(48)

    if password is None:
        typer.echo("error: pass --password or use default --generate", err=True)
        raise typer.Exit(code=1)

    url = db_url or get_settings().database_url

    async def _run() -> None:
        conn = await asyncpg.connect(url)
        try:
            await rotate_role_password(conn, role, password)
        finally:
            await conn.close()

    try:
        _run_async(_run())
    except (OSError, asyncpg.PostgresError) as exc:
        typer.echo(f"error: could not rotate password: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"rotated password for role '{role}'")

    if role == "authenticator":
        updated = _update_dotenv_key("AUTHENTICATOR_PASSWORD", password)
        if updated:
            typer.echo("updated AUTHENTICATOR_PASSWORD in .env")
        else:
            typer.echo("warn: .env not found; update AUTHENTICATOR_PASSWORD manually")
        typer.echo(
            "reminder: update docker-compose.yml (or docker-compose.prod.yml) / "
            "PostgREST env to match"
        )

    # Detect if role matches the user in DATABASE_URL
    db_url_setting = get_settings().database_url
    if f"//{role}:" in db_url_setting or f"/{role}@" in db_url_setting:
        updated = _update_dotenv_key("DATABASE_URL", db_url_setting)
        if updated:
            typer.echo("updated DATABASE_URL in .env")
        typer.echo("reminder: restart supython replicas to pick up the new password")

    typer.echo("")
    typer.echo("new password (store in your secret manager; it will not be shown again):")
    typer.echo(password)


# ---------------------------------------------------------------------------
# Admin user CLI
# ---------------------------------------------------------------------------


@admin_cli.command("create-user")
def admin_create_user(
    email: str = typer.Argument(..., help="Admin email address."),
    password: str | None = typer.Option(
        None,
        "--password",
        help="Password (>=12 chars). Prompted securely if omitted.",
    ),
    is_root: bool = typer.Option(False, "--root", help="Mark this admin as root (is_root = true)."),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="Privileged Postgres URL. Defaults to settings.database_url.",
    ),
) -> None:
    """Create an admin user. Run once to bootstrap the first admin."""
    from email_validator import EmailNotValidError, validate_email

    from . import passwords

    try:
        normalized = validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        typer.echo(f"error: invalid email: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if password is None:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    if len(password) < 12:
        typer.echo("error: password must be at least 12 characters", err=True)
        raise typer.Exit(code=1)

    hashed = passwords.hash_password(password)
    url = db_url or get_settings().database_url

    async def _run() -> uuid.UUID:
        conn = await asyncpg.connect(url)
        try:
            return await conn.fetchval(
                """
                insert into admin.admin_users (email, password_hash, is_root)
                values ($1, $2, $3)
                returning id
                """,
                normalized,
                hashed,
                is_root,
            )
        finally:
            await conn.close()

    try:
        admin_id = _run_async(_run())
    except asyncpg.UniqueViolationError as exc:
        typer.echo(f"error: admin with email {normalized!r} already exists", err=True)
        raise typer.Exit(code=1) from exc
    except (OSError, asyncpg.PostgresError) as exc:
        typer.echo(f"error: could not create admin user: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    suffix = " [root]" if is_root else ""
    typer.echo(f"created admin user id={admin_id} email={normalized}{suffix}")


@app.command()
def doctor() -> None:
    """Health check: Postgres, JWT keys, PostgREST."""
    configure_logging("INFO", json_format=False)
    try:
        s = get_settings()
    except Exception as exc:
        typer.echo(f"error: settings failed to load: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    report = _DoctorReport()
    report.merge(_check_database(s.database_url))
    report.merge(_check_migration_drift(s.database_url))
    jwt_report = _check_jwt(s)
    report.merge(jwt_report)
    report.merge(_check_symmetric_secrets(s))
    if not jwt_report.failures:
        report.merge(_check_postgrest(s))

    for line in report.ok:
        typer.echo(f"ok: {line}")
    for line in report.warnings:
        typer.echo(f"warn: {line}")
    for line in report.failures:
        typer.echo(f"fail: {line}", err=True)
    if report.failures:
        raise typer.Exit(code=1)


async def _check_database_async(database_url: str) -> _DoctorReport:
    report = _DoctorReport()
    try:
        conn = await asyncpg.connect(database_url, timeout=2.0)
    except (OSError, TimeoutError, asyncpg.PostgresError) as exc:
        report.failures.append(f"Postgres unreachable at {database_url}: {exc}")
        return report

    try:
        version_num = await conn.fetchval("show server_version_num")
        try:
            major = int(version_num) // 10000
        except (TypeError, ValueError):
            report.failures.append(f"could not parse Postgres server_version_num: {version_num}")
        else:
            if major < _MIN_PG_VERSION:
                report.failures.append(
                    f"Postgres {major} is below minimum supported {_MIN_PG_VERSION}"
                )
            else:
                report.ok.append(f"Postgres reachable (server_version_num={version_num})")

        roles = {
            row["rolname"]
            for row in await conn.fetch(
                """
                select rolname
                from pg_roles
                where rolname = any($1::text[])
                """,
                list(_REQUIRED_ROLES),
            )
        }
        missing_roles = sorted(set(_REQUIRED_ROLES) - roles)
        if missing_roles:
            report.failures.append(
                f"missing Postgres roles: {', '.join(missing_roles)} (run `supython up`)"
            )
        else:
            report.ok.append(f"required roles present: {', '.join(_REQUIRED_ROLES)}")

        present_extensions = {
            row["extname"]
            for row in await conn.fetch(
                """
                select extname
                from pg_extension
                where extname = any($1::text[])
                """,
                list(_REQUIRED_EXTENSIONS) + list(_RECOMMENDED_EXTENSIONS),
            )
        }
        missing_required = sorted(set(_REQUIRED_EXTENSIONS) - present_extensions)
        if missing_required:
            report.failures.append(
                f"missing required Postgres extensions: {', '.join(missing_required)}"
            )
        else:
            report.ok.append(f"required extensions present: {', '.join(_REQUIRED_EXTENSIONS)}")

        missing_recommended = sorted(set(_RECOMMENDED_EXTENSIONS) - present_extensions)
        for extension in missing_recommended:
            report.warnings.append(
                f"recommended extension missing: {extension} "
                "(used by jobs cron + auth rate-limit prune)"
            )

        wal_level = await conn.fetchval("show wal_level")
        if wal_level != "logical":
            report.warnings.append(
                f"wal_level={wal_level!r}, but 'logical' is required for realtime (v0.8+)"
            )
        else:
            report.ok.append("wal_level=logical")

        for role_name, expected_attrs in _ROLE_ATTRIBUTES.items():
            if role_name not in roles:
                continue
            for attr, expected_val in expected_attrs.items():
                actual = await conn.fetchval(
                    f"select {attr} from pg_roles where rolname = $1",
                    role_name,
                )
                if actual != expected_val:
                    label = "can login" if attr == "rolcanlogin" else attr
                    msg = f"role {role_name!r} {label}={actual}, expected {expected_val}"
                    if attr == "rolcanlogin" and role_name in ("anon", "authenticated"):
                        report.warnings.append(msg)
                    else:
                        report.failures.append(msg)
                else:
                    label = "can login" if attr == "rolcanlogin" else attr
                    report.ok.append(f"role {role_name!r} {label}={expected_val}")

        granted_rows = await conn.fetch(
            """
            select r1.rolname as roleid, r2.rolname as member
            from pg_auth_members m
            join pg_roles r1 on r1.oid = m.roleid
            join pg_roles r2 on r2.oid = m.member
            where r1.rolname = any($1::text[])
            """,
            ["anon", "authenticated", "service_role"],
        )
        granted_to_authenticator = {
            r["roleid"] for r in granted_rows if r["member"] == "authenticator"
        }
        for child in ("anon", "authenticated", "service_role"):
            if child not in granted_to_authenticator:
                report.failures.append(f"role {child!r} is not granted to 'authenticator'")
            else:
                report.ok.append(f"role {child!r} granted to 'authenticator'")

        schema_owners = {
            r["nspname"]: r["owner"]
            for r in await conn.fetch(
                """
                select nspname, rolname as owner
                from pg_namespace n
                join pg_roles r on r.oid = n.nspowner
                where nspname = any($1::text[])
                """,
                list(_FRAMEWORK_SCHEMAS),
            )
        }
        for schema in _FRAMEWORK_SCHEMAS:
            if schema in schema_owners and schema_owners[schema] != "service_role":
                report.warnings.append(
                    f"schema {schema!r} owned by {schema_owners[schema]!r}, expected 'service_role'"
                )
    finally:
        await conn.close()

    return report


def _check_database(database_url: str) -> _DoctorReport:
    try:
        return _run_async(_check_database_async(database_url))
    except Exception as exc:
        report = _DoctorReport()
        report.failures.append(f"database check raised unexpectedly: {exc}")
        return report


async def _check_migration_drift_async(database_url: str) -> _DoctorReport:
    report = _DoctorReport()

    if not migrate_mod.DEFAULT_MIGRATIONS_DIR.exists():
        report.warnings.append(
            f"migrations directory not found at {migrate_mod.DEFAULT_MIGRATIONS_DIR}; "
            "skipping drift check"
        )
        return report

    disk_files = {p.name for p in sorted(migrate_mod.DEFAULT_MIGRATIONS_DIR.glob("*.sql"))}

    try:
        conn = await asyncpg.connect(database_url, timeout=2.0)
    except (OSError, TimeoutError, asyncpg.PostgresError):
        report.warnings.append("cannot reach DB for migration drift check; skipping")
        return report

    try:
        has_table = await conn.fetchval(
            "select exists(select 1 from information_schema.tables "
            "where table_schema='supython' and table_name='migrations')"
        )
        if not has_table:
            report.warnings.append(
                "supython.migrations table not found; run `supython migrate` first"
            )
            return report

        db_rows = {r["name"] for r in await conn.fetch("select name from supython.migrations")}
    finally:
        await conn.close()

    unapplied = sorted(disk_files - db_rows)
    orphaned = sorted(db_rows - disk_files)

    if unapplied:
        report.warnings.append(f"{len(unapplied)} unapplied migration(s): {', '.join(unapplied)}")
    if orphaned:
        report.warnings.append(
            f"{len(orphaned)} migration(s) in DB but not on disk: {', '.join(orphaned)}"
        )
    if not unapplied and not orphaned:
        report.ok.append(f"all {len(disk_files)} migrations applied, no drift")

    return report


def _check_migration_drift(database_url: str) -> _DoctorReport:
    try:
        return _run_async(_check_migration_drift_async(database_url))
    except Exception as exc:
        report = _DoctorReport()
        report.warnings.append(f"migration drift check raised unexpectedly: {exc}")
        return report


def _check_jwt(s: Settings) -> _DoctorReport:
    report = _DoctorReport()
    if s.jwt_alg not in _ASYMMETRIC_ALGS:
        report.failures.append(f"JWT_ALG must be RS256 or ES256 for JWKS mode (got {s.jwt_alg})")

    if s.jwt_private_key is None and s.jwt_private_key_path is None:
        report.failures.append("set JWT_PRIVATE_KEY or JWT_PRIVATE_KEY_PATH")

    if s.jwt_private_key_path is not None:
        if not s.jwt_private_key_path.exists():
            report.failures.append(f"private key file does not exist: {s.jwt_private_key_path}")
        elif os.name == "posix":
            mode = s.jwt_private_key_path.stat().st_mode & 0o777
            if mode & 0o077:
                report.failures.append(
                    f"private key file must not be group/world-readable: "
                    f"{s.jwt_private_key_path} mode {mode:03o}"
                )

    if not report.failures:
        try:
            signer = jwks.load_signing_key()
            jwks_doc = jwks.dump_jwks(jwks.load_verification_keyset())
            _assert_public_jwks(jwks_doc)
        except Exception as exc:
            report.failures.append(f"JWT key/JWKS check failed: {exc}")
        else:
            report.ok.append(f"JWT signing key loads ({signer.alg}, kid={signer.kid})")
            report.ok.append("JWKS export contains public key material only")

    return report


def _check_postgrest(s: Settings) -> _DoctorReport:
    report = _DoctorReport()
    postgrest_result = _check_postgrest_accepts_token(s.postgrest_url)
    if postgrest_result == "unreachable":
        report.warnings.append(f"PostgREST not reachable at {s.postgrest_url}; skipped token check")
    elif postgrest_result:
        report.failures.append(postgrest_result)
    else:
        report.ok.append("PostgREST accepted a freshly-issued token")
    return report


def _check_symmetric_secrets(s: Settings) -> _DoctorReport:
    report = _DoctorReport()
    for name, legacy_attr in (
        ("storage_signed_url", "storage_signed_url_secret"),
        ("oauth_state", "oauth_state_secret"),
    ):
        manifest = secretset.load_manifest()
        section = manifest.get(name) if manifest else None
        legacy = getattr(s, legacy_attr)

        if section is not None:
            active_kid = section.get("active")
            keys = {k["kid"]: k for k in section.get("keys", [])}

            if active_kid is None:
                report.failures.append(f"{name}: manifest exists but has no active kid")
                continue

            if active_kid not in keys:
                report.failures.append(f"{name}: active kid {active_kid!r} not found in keys list")
                continue

            secret_path = secretset.secrets_dir() / f"{name}.{active_kid}.secret"
            if not secret_path.exists():
                report.failures.append(f"{name}: active secret file missing: {secret_path}")
                continue

            value = secret_path.read_text().strip()
            if len(value) < 32:
                report.failures.append(f"{name}: active secret value is shorter than 32 characters")
                continue

            if os.name == "posix":
                mode = secret_path.stat().st_mode & 0o777
                if mode & 0o077:
                    report.warnings.append(
                        f"{name}: secret file should not be group/world-readable: "
                        f"{secret_path} mode {mode:03o}"
                    )

            report.ok.append(f"{name}: active kid={active_kid} secret file readable")
        else:
            if not legacy or len(legacy) < 32:
                report.failures.append(
                    f"{name}: no manifest and no valid legacy env var "
                    f"({legacy_attr}); run `supython secret rotate {name.replace('_signed_url', '')}` "
                    f"or set {legacy_attr.upper()}"
                )
            else:
                report.ok.append(f"{name}: using legacy env var ({legacy_attr})")

    if s.secret_rotation_grace_seconds < s.storage_signed_url_default_ttl:
        report.warnings.append(
            f"SECRET_ROTATION_GRACE_SECONDS ({s.secret_rotation_grace_seconds}) "
            f"is shorter than STORAGE_SIGNED_URL_DEFAULT_TTL ({s.storage_signed_url_default_ttl}); "
            f"signed URLs may expire before rotation grace window"
        )

    return report


@functions_cli.command("list")
def functions_list() -> None:
    """List all discovered edge functions with their methods and auth mode."""
    from .functions.loader import FunctionRegistry

    s = get_settings()
    reg = FunctionRegistry(Path(s.functions_dir), hot_reload=False)
    reg.discover()
    metas = reg.list()
    if not metas:
        typer.echo("no functions found in " + s.functions_dir)
        return
    for meta in metas:
        typer.echo(f"  {meta.name:<30} methods={','.join(meta.methods)} auth={meta.auth}")


@app.command()
def dev(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(True, help="Reload on code change."),
    slow_callback_warn_ms: int = typer.Option(
        100,
        "--slow-callback-warn-ms",
        help=(
            "Warn when an event-loop task blocks for longer than this many ms. "
            "Catches sync I/O (time.sleep, blocking requests) inside async "
            "functions. Set 0 to disable. Dev only — adds asyncio debug overhead."
        ),
    ),
) -> None:
    """Run the supython API service for local development."""
    s = get_settings()
    configure_logging(s.log_level, json_format=s.log_json)
    if slow_callback_warn_ms > 0:
        os.environ["SUPYTHON_SLOW_CALLBACK_MS"] = str(slow_callback_warn_ms)
    uvicorn.run("supython.app:app", host=host, port=port, reload=reload)


@app.command()
def migrate() -> None:
    """Apply pending framework SQL migrations bundled with the supython package."""
    configure_logging("INFO", json_format=False)
    applied = migrate_mod.run_sync()
    if not applied:
        typer.echo("nothing to apply — database is up to date.")
        return
    for name in applied:
        typer.echo(f"applied {name}")


def _resolve_compose_file(prod: bool = False) -> str | None:
    if prod:
        return "docker-compose.prod.yml"
    if Path("docker-compose.yml").exists():
        return None
    if Path("docker-compose.prod.yml").exists():
        return "docker-compose.prod.yml"
    return None


@app.command()
def up(
    timeout: int = typer.Option(30, help="Seconds to wait for Postgres."),
    prod: bool = typer.Option(False, "--prod", help="Use docker-compose.prod.yml."),
    worker: bool = typer.Option(False, "--worker", help="Also start the worker (prod only)."),
    profile: list[str] = typer.Option(
        [],
        "--profile",
        help="Compose profile(s) to enable. Repeatable; user-defined extension services gated by a profile come up via a final sweep.",
    ),
) -> None:
    """Start Postgres + PostgREST and apply migrations.

    Brings the DB up first, runs migrations (which create the roles
    PostgREST needs), rotates the authenticator password, then starts PostgREST.
    Any user-added services gated behind a compose profile come up after the
    core services when `--profile <name>` is passed.
    """
    compose_file = _resolve_compose_file(prod)
    is_prod = compose_file == "docker-compose.prod.yml"
    user_profiles = tuple(profile)
    configure_logging("INFO", json_format=False)
    _compose_with(compose_file, "up", "-d", "db")
    typer.echo("waiting for Postgres ...")
    _wait_for_db(timeout)
    typer.echo("applying migrations ...")
    applied = migrate_mod.run_sync()
    for name in applied:
        typer.echo(f"  applied {name}")
    s = get_settings()
    typer.echo("rotating authenticator password ...")
    asyncio.run(_rotate_authenticator_password(s.database_url, s.authenticator_password))
    _ensure_jwks_for_postgrest(s)
    if is_prod:
        _compose_with(compose_file, "up", "-d", "postgrest", "supython")
        if worker:
            _compose_with(compose_file, "--profile", "worker", "up", "-d", "worker")
        if user_profiles:
            _compose_with(compose_file, "up", "-d", profiles=user_profiles)
        typer.echo("")
        typer.echo("ready.")
        typer.echo("  postgres   localhost:54322  (bind 127.0.0.1 only)")
        typer.echo("  postgrest  (internal only — routed via Caddy when --profile tls)")
        typer.echo("  supython   http://localhost:8000")
        if worker:
            typer.echo("  worker     running (profile=worker)")
        for p in user_profiles:
            typer.echo(f"  profile    {p}   # user-defined services")
    else:
        _compose_with(compose_file, "up", "-d", "postgrest")
        if user_profiles:
            _compose_with(compose_file, "up", "-d", profiles=user_profiles)
        typer.echo("")
        typer.echo("ready.")
        typer.echo("  postgres   localhost:54322  (user/db: supython)")
        typer.echo(f"  postgrest  {s.postgrest_url}")
        for p in user_profiles:
            typer.echo(f"  profile    {p}   # user-defined services")
        typer.echo("  next       supython dev   # start the auth/API service")


@app.command()
def down(
    prod: bool = typer.Option(False, "--prod", help="Use docker-compose.prod.yml."),
) -> None:
    """Stop the docker-compose stack (keeps data)."""
    _compose_with(_resolve_compose_file(prod), "down")


@app.command()
def reset(
    prod: bool = typer.Option(False, "--prod", help="Use docker-compose.prod.yml."),
) -> None:
    """Stop the stack AND drop all data. Destructive."""
    confirm = typer.confirm("This will delete all Postgres data. Continue?")
    if not confirm:
        raise typer.Abort()
    _compose_with(_resolve_compose_file(prod), "down", "-v")


def _bootstrap_test_db(timeout: int) -> None:
    """Bring the test DB up, wait for healthcheck, then apply migrations.

    Idempotent: compose `up -d --wait` is a no-op when the container is
    already healthy, and the migration runner skips already-applied files.
    The named volume in `docker-compose.test.yml` makes the second call
    cheap — schema survives between pytest sessions.
    """
    _compose_with(_TEST_COMPOSE_FILE, "up", "-d", "--wait", "db", project_directory=".")

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
    get_settings.cache_clear()
    try:
        applied = migrate_mod.run_sync()
        for name in applied:
            typer.echo(f"  applied {name}")
        if not applied:
            typer.echo("  (no pending migrations)")
        s = get_settings()
        asyncio.run(_rotate_authenticator_password(s.database_url, s.authenticator_password))
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()
    _ = timeout  # `--wait` already enforces the healthcheck retries.


@test_cli.command("up")
def test_up(
    timeout: int = typer.Option(60, help="Seconds to wait for Postgres health."),
) -> None:
    """Start the integration-test Postgres and apply pending migrations.

    The test stack runs on host port 54323 (vs 54322 for `supython up`) so
    it cannot collide with the dev DB. Data lives in a named volume, so
    the schema persists between pytest sessions; use `supython test reset`
    to throw it away.
    """
    configure_logging("INFO", json_format=False)
    _bootstrap_test_db(timeout)
    typer.echo("")
    typer.echo("ready.")
    typer.echo("  postgres   localhost:54323  (user/db: supython)")
    typer.echo("  next       supython test run   # run pytest")


@test_cli.command("down")
def test_down() -> None:
    """Stop the test DB container. Keeps the volume (and migrations)."""
    _compose_with(_TEST_COMPOSE_FILE, "down", project_directory=".")


@test_cli.command("reset")
def test_reset() -> None:
    """Stop the test DB container AND delete its data volume. Destructive."""
    confirm = typer.confirm("This will delete the test DB volume. Continue?")
    if not confirm:
        raise typer.Abort()
    _compose_with(_TEST_COMPOSE_FILE, "down", "-v", project_directory=".")


@test_cli.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def test_run(ctx: typer.Context) -> None:
    """Run pytest against the test DB. Extra args are forwarded to pytest.

    Ensures the test stack is up + migrated, then exec's pytest with
    DATABASE_URL pointing at the test container. Examples:

        supython test run                 # full suite
        supython test run tests/unit      # unit-only (fast, no fixtures)
        supython test run -k auth_signup  # forward -k to pytest
    """
    configure_logging("INFO", json_format=False)
    _bootstrap_test_db(timeout=60)

    env = os.environ.copy()
    env["DATABASE_URL"] = _TEST_DATABASE_URL
    pytest_args = list(ctx.args) if ctx.args else ["tests"]
    cmd = [sys.executable, "-m", "pytest", *pytest_args]
    try:
        result = subprocess.run(cmd, env=env, check=False)
    except FileNotFoundError as exc:
        typer.echo(f"error: pytest not found ({exc})", err=True)
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=result.returncode)


@app.command()
def info() -> None:
    """Print resolved settings."""
    s = get_settings()
    typer.echo(f"database_url      {s.database_url}")
    typer.echo(f"postgrest_url     {s.postgrest_url}")
    typer.echo(f"jwt_alg           {s.jwt_alg}")
    typer.echo(f"jwt_aud           {s.jwt_aud}")
    typer.echo(f"access_token_ttl  {s.access_token_ttl}s")
    typer.echo(f"refresh_token_ttl {s.refresh_token_ttl}s")
    typer.echo(f"cors_origins      {s.cors_origins or '(none)'}")


def _asymmetric_alg(alg: str) -> Literal["RS256", "ES256"]:
    normalized = alg.upper()
    if normalized not in _ASYMMETRIC_ALGS:
        raise ValueError(f"JWT algorithm must be RS256 or ES256, got {alg!r}")
    return normalized  # type: ignore[return-value]


def _assert_public_jwks(jwks_doc: dict) -> None:  # type: ignore[type-arg]
    for key in jwks_doc.get("keys", []):
        leaked = sorted(_PRIVATE_JWK_MEMBERS.intersection(key))
        if leaked:
            raise ValueError(f"JWKS contains private/symmetric members: {', '.join(leaked)}")


def _check_postgrest_accepts_token(postgrest_url: str) -> str | None:
    try:
        token, _ = tokens.issue_access_token(uuid.uuid4(), "doctor@supython.local")
        with httpx.Client(base_url=postgrest_url, timeout=2.0) as client:
            response = client.get("/", headers={"authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        return "unreachable"
    except Exception as exc:
        return f"PostgREST token check failed: {exc}"

    if response.status_code in {200, 300, 304}:
        return None
    if response.status_code >= 500:
        return "unreachable"
    return f"PostgREST rejected a freshly-issued token: {response.status_code} {response.text}"


def _generate_jwt_files(
    *,
    alg: Literal["RS256", "ES256"],
    out_private: Path,
    out_jwks: Path,
    kid: str | None,
    force: bool,
) -> jwks.SigningKey:
    if out_private == out_jwks:
        raise ValueError("--out-private and --out-jwks must be different paths")
    if not force:
        for path in (out_private, out_jwks):
            if path.exists():
                raise FileExistsError(f"{path} exists; pass --force to overwrite")

    key = jwks.generate_private_key(alg)
    signer = jwks.signing_key_from_private_key(key, alg, kid)
    jwks.write_private_key_pem(out_private, jwks.private_key_to_pem(key), force=force)
    jwks.write_jwks_file(out_jwks, jwks.jwks_for_signing_key(signer))
    return signer


def _ensure_jwks_for_postgrest(s: Settings) -> None:
    if s.jwt_alg in _ASYMMETRIC_ALGS and (
        s.jwt_private_key is not None or s.jwt_private_key_path is not None
    ):
        jwks_doc = jwks.write_current_jwks(s.jwt_jwks_path)
        kids = ", ".join(key["kid"] for key in jwks_doc["keys"])
        typer.echo(f"wrote JWKS for PostgREST: {s.jwt_jwks_path} (kids={kids})")
        return

    if s.jwt_jwks_path.exists():
        typer.echo(f"using existing JWKS for PostgREST: {s.jwt_jwks_path}")
        return

    out_private = Path("./.supython/jwt_private.pem")
    signer = _generate_jwt_files(
        alg="RS256",
        out_private=out_private,
        out_jwks=s.jwt_jwks_path,
        kid=None,
        force=False,
    )
    typer.echo(f"generated RS256 keypair for PostgREST: {s.jwt_jwks_path}")
    typer.echo("add these env vars before running `supython dev`:")
    typer.echo("  JWT_ALG=RS256")
    typer.echo(f"  JWT_PRIVATE_KEY_PATH={out_private}")
    typer.echo(f"  JWT_KID={signer.kid}")
    typer.echo(f"  JWT_JWKS_PATH={s.jwt_jwks_path}")


_TEST_COMPOSE_FILE = "tests/docker-compose.test.yml"
_TEST_DATABASE_URL = "postgresql://supython:supython@localhost:54323/supython"


def _compose(*args: str) -> None:
    _compose_with(None, *args)


def _compose_with(
    file: str | None,
    *args: str,
    profiles: tuple[str, ...] = (),
    project_directory: str | None = None,
) -> None:
    """Run `docker compose [-f <file>] [--profile <p>]... <args...>`, surfacing common errors."""
    cmd = ["docker", "compose"]
    if file:
        cmd += ["-f", file]
    if project_directory:
        cmd += ["--project-directory", project_directory]
    for p in profiles:
        cmd += ["--profile", p]
    cmd += list(args)
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        typer.echo(f"error: docker not found ({exc})", err=True)
        raise typer.Exit(code=1) from exc
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(code=exc.returncode) from exc


def _wait_for_db(timeout_s: int) -> None:
    s = get_settings()
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            asyncio.run(_ping(s.database_url))
            return
        except Exception as exc:
            last_err = exc
            time.sleep(1)
    typer.echo(f"timed out waiting for Postgres: {last_err}", err=True)
    raise typer.Exit(code=1)


async def _ping(url: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.fetchval("select 1")
    finally:
        await conn.close()


async def _rotate_authenticator_password(db_url: str, password: str) -> None:
    """Idempotent: set the authenticator role password to the configured value."""
    conn = await asyncpg.connect(db_url)
    try:
        await rotate_role_password(conn, "authenticator", password)
    finally:
        await conn.close()


def main() -> None:
    sys.exit(app() or 0)


if __name__ == "__main__":
    main()
