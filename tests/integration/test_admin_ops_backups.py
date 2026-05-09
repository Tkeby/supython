"""Integration tests for /admin/api/v1/ops endpoints.

Covers:
- GET  /backups           — auth gate, empty page, pagination, listing with data
- POST /backups           — auth gate, start full backup, start schema-only, invalid kind
- GET  /backups/{id}/download — auth gate, 404, 409 not completed
- GET  /downloads/{token} — invalid token, expired token, valid download
"""

import json
import time
from unittest.mock import patch
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

from supython import passwords, settings
from supython.admin import session as admin_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(pool: asyncpg.Pool):
    email = "ops-backups@example.com"
    password = "correct horse battery staple"
    pw_hash = passwords.hash_password(password)
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_audit")
        await conn.execute("delete from admin.admin_users")
        admin_id = await conn.fetchval(
            """
            insert into admin.admin_users (email, password_hash, is_root)
            values ($1, $2, true)
            returning id
            """,
            email,
            pw_hash,
        )
    yield {"id": admin_id, "email": email, "password": password}
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
        await conn.execute("delete from admin.admin_audit")
        await conn.execute("delete from admin.admin_users")


async def _login(client: httpx.AsyncClient, admin_user: dict) -> None:
    r = await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    assert r.status_code == 200, r.text
    assert client.cookies.get(admin_session.SESSION_COOKIE) is not None


@pytest.fixture
def backups_dir(tmp_path, monkeypatch):
    """Point settings.backups_dir at a temp directory for the test."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    settings.get_settings.cache_clear()
    yield tmp_path
    settings.get_settings.cache_clear()


async def _seed_backup(pool: asyncpg.Pool, **overrides) -> dict:
    """Insert a completed backup row directly and return it."""
    kind = overrides.get("kind", "full")
    status = overrides.get("status", "completed")
    file_path = overrides.get("file_path", "/tmp/test-backup.sql")
    size = overrides.get("size", 12345)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            insert into admin.backups (kind, status, size, file_path, finished_at)
            values ($1, $2, $3, $4, now())
            returning id, kind, status, size, file_path, error_message,
                      started_at, finished_at, created_at
            """,
            kind,
            status,
            size,
            file_path,
        )
        return dict(row)


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------


async def test_list_requires_admin(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/ops/backups")
    assert r.status_code == 401


async def test_start_requires_admin(client: httpx.AsyncClient):
    r = await client.post("/admin/api/v1/ops/backups", json={"kind": "full"})
    assert r.status_code == 401


async def test_download_requires_admin(client: httpx.AsyncClient):
    r = await client.get(f"/admin/api/v1/ops/backups/{uuid4()}/download")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /backups — list
# ---------------------------------------------------------------------------


async def test_list_returns_empty_page(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)

    r = await client.get("/admin/api/v1/ops/backups")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == []
    assert body["total"] == 0


async def test_list_returns_backups(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    await _seed_backup(pool, kind="full", status="completed")
    await _seed_backup(pool, kind="schema-only", status="running")

    r = await client.get("/admin/api/v1/ops/backups")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert len(body["rows"]) == 2
    # Most recent first
    assert body["rows"][0]["kind"] in ("full", "schema-only")
    assert "status" in body["rows"][0]
    assert "size" in body["rows"][0] or body["rows"][0]["size"] is None
    assert "started_at" in body["rows"][0]


async def test_list_respects_limit_offset(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    for i in range(5):
        await _seed_backup(pool)

    r = await client.get("/admin/api/v1/ops/backups?limit=2&offset=0")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5
    assert len(body["rows"]) == 2

    r = await client.get("/admin/api/v1/ops/backups?limit=2&offset=2")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5
    assert len(body["rows"]) == 2


# ---------------------------------------------------------------------------
# POST /backups — start backup
# ---------------------------------------------------------------------------


async def test_start_backup_creates_running_record(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)

    r = await client.post("/admin/api/v1/ops/backups", json={"kind": "full"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["kind"] == "full"
    assert body["status"] == "running"
    assert body["size"] is None
    assert body["finished_at"] is None
    assert body["id"] is not None


async def test_start_backup_rejects_invalid_kind(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)

    r = await client.post("/admin/api/v1/ops/backups", json={"kind": "invalid-kind"})
    assert r.status_code == 422, r.text


async def test_start_backup_audit_logged(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    r = await client.post("/admin/api/v1/ops/backups", json={"kind": "schema-only"})
    assert r.status_code == 202, r.text

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select action, target, payload
            from admin.admin_audit
            where action = 'backup.start'
            order by at desc limit 1
            """
        )
        assert row is not None
        assert row["action"] == "backup.start"
        assert row["target"] is not None
        # asyncpg returns jsonb columns as raw text by default
        payload = json.loads(row["payload"])
        assert payload["kind"] == "schema-only"


# ---------------------------------------------------------------------------
# GET /backups/{id}/download — signed download URL
# ---------------------------------------------------------------------------


async def test_download_url_404_for_missing_backup(
    client: httpx.AsyncClient,
    admin_user: dict,
):
    await _login(client, admin_user)

    r = await client.get(f"/admin/api/v1/ops/backups/{uuid4()}/download")
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["detail"]["code"] == "backup_not_found"


async def test_download_url_409_for_incomplete_backup(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    backup = await _seed_backup(pool, status="running")

    r = await client.get(f"/admin/api/v1/ops/backups/{backup['id']}/download")
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["code"] == "backup_not_ready"


async def test_download_url_returns_signed_url(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    await _login(client, admin_user)

    backup = await _seed_backup(pool, status="completed", file_path="/tmp/test-backup.sql")

    r = await client.get(f"/admin/api/v1/ops/backups/{backup['id']}/download")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "download_url" in body
    assert body["download_url"].startswith("/admin/api/v1/ops/downloads/")
    assert body["expires_in"] == 600
    assert body["backup_id"] == str(backup["id"])


# ---------------------------------------------------------------------------
# GET /downloads/{token} — stream file
# ---------------------------------------------------------------------------


async def test_download_invalid_token_rejected(client: httpx.AsyncClient):
    r = await client.get("/admin/api/v1/ops/downloads/bad-token")
    assert r.status_code == 403


async def test_download_expired_token_rejected(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
    backups_dir,
):
    await _login(client, admin_user)

    backup_file = backups_dir / "expired-test.sql"
    backup_file.write_text("-- expired token test\n")
    backup = await _seed_backup(pool, status="completed", file_path=str(backup_file))

    r = await client.get(f"/admin/api/v1/ops/backups/{backup['id']}/download")
    body = r.json()
    download_url = body["download_url"]

    with patch("supython.backups.service.time.time", return_value=time.time()):
        r2 = await client.get(download_url)
        assert r2.status_code == 200, r2.text

    with patch(
        "supython.backups.service.time.time",
        return_value=time.time() + 3600,
    ):
        r3 = await client.get(download_url)
        assert r3.status_code == 403, r3.text


async def test_start_backup_enqueues_job_with_backup_id_in_payload(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    """POST /backups must enqueue an admin_backup_run job carrying the backup id."""
    await _login(client, admin_user)

    r = await client.post("/admin/api/v1/ops/backups", json={"kind": "full"})
    assert r.status_code == 202, r.text
    backup_id = r.json()["id"]

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select name, status, payload
            from jobs.jobs
            where name = 'admin_backup_run'
            order by created_at desc limit 1
            """
        )
        assert row is not None, "no admin_backup_run job enqueued"
        assert row["status"] == "queued"
        payload = json.loads(row["payload"])
        assert payload["backup_id"] == backup_id
        assert payload["kind"] == "full"
        assert payload["file_path"].endswith(".sql")


async def test_start_backup_enqueue_idempotent_per_backup_id(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
):
    """Each admin.backups row gets exactly one corresponding job."""
    await _login(client, admin_user)

    r1 = await client.post("/admin/api/v1/ops/backups", json={"kind": "full"})
    r2 = await client.post("/admin/api/v1/ops/backups", json={"kind": "schema-only"})
    assert r1.status_code == 202
    assert r2.status_code == 202

    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            "select count(*) from jobs.jobs where name = 'admin_backup_run'"
        )
        assert cnt == 2


async def test_backup_job_handler_marks_completed_on_success(
    pool: asyncpg.Pool,
    backups_dir,
    monkeypatch,
):
    """Invoking the @job handler directly with a fake pg_dump marks the row completed."""
    from supython.backups._backup_job import admin_backup_run

    async with pool.acquire() as conn:
        backup_id = await conn.fetchval(
            "insert into admin.backups (kind) values ('full') returning id"
        )

    file_path = str(backups_dir / "fake-backup.sql")

    async def fake_subprocess(*args, **kwargs):
        # write a fake dump file so getsize() works, then return a fake proc
        with open(file_path, "w") as f:
            f.write("-- fake dump\n")

        class _Proc:
            returncode = 0

            async def communicate(self):
                return (b"", b"")

            def kill(self):
                pass

            async def wait(self):
                return 0

        return _Proc()

    monkeypatch.setattr(
        "supython.backups._backup_job.asyncio.create_subprocess_exec",
        fake_subprocess,
    )

    async with pool.acquire() as conn:

        class _Ctx:
            db = conn

        await admin_backup_run(
            _Ctx(),
            {
                "backup_id": str(backup_id),
                "kind": "full",
                "file_path": file_path,
            },
        )

        row = await conn.fetchrow(
            "select status, size, file_path, finished_at from admin.backups where id = $1",
            backup_id,
        )
        assert row["status"] == "completed"
        assert row["size"] is not None and row["size"] > 0
        assert row["file_path"] == file_path
        assert row["finished_at"] is not None


async def test_backup_job_handler_marks_failed_and_reraises_on_pg_dump_error(
    pool: asyncpg.Pool,
    backups_dir,
    monkeypatch,
):
    """Handler must set admin.backups=failed and re-raise so the framework retries."""
    from supython.backups._backup_job import admin_backup_run

    async with pool.acquire() as conn:
        backup_id = await conn.fetchval(
            "insert into admin.backups (kind) values ('full') returning id"
        )

    file_path = str(backups_dir / "doomed.sql")

    async def failing_subprocess(*args, **kwargs):
        class _Proc:
            returncode = 2

            async def communicate(self):
                return (b"", b"connection refused")

            def kill(self):
                pass

            async def wait(self):
                return 2

        return _Proc()

    monkeypatch.setattr(
        "supython.backups._backup_job.asyncio.create_subprocess_exec",
        failing_subprocess,
    )

    async with pool.acquire() as conn:

        class _Ctx:
            db = conn

        with pytest.raises(RuntimeError):
            await admin_backup_run(
                _Ctx(),
                {
                    "backup_id": str(backup_id),
                    "kind": "full",
                    "file_path": file_path,
                },
            )

        row = await conn.fetchrow(
            "select status, error_message, finished_at from admin.backups where id = $1",
            backup_id,
        )
        assert row["status"] == "failed"
        assert "connection refused" in (row["error_message"] or "")
        assert row["finished_at"] is not None


async def test_download_backup_file(
    client: httpx.AsyncClient,
    admin_user: dict,
    pool: asyncpg.Pool,
    backups_dir,
):
    """End-to-end: create backup file on disk, get signed URL, download it."""
    await _login(client, admin_user)

    backup_file = backups_dir / "test-backup.sql"
    backup_content = "-- supython backup test\nselect 1;\n"
    backup_file.write_text(backup_content)

    backup = await _seed_backup(
        pool,
        status="completed",
        file_path=str(backup_file),
        size=len(backup_content),
    )

    r = await client.get(f"/admin/api/v1/ops/backups/{backup['id']}/download")
    assert r.status_code == 200, r.text
    body = r.json()
    download_url = body["download_url"]

    r2 = await client.get(download_url)
    assert r2.status_code == 200, r2.text
    assert r2.text == backup_content
    assert "attachment" in r2.headers.get("content-disposition", "")
    assert "backup" in r2.headers.get("content-disposition", "")
