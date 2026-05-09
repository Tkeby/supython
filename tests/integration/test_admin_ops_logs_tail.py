"""Smoke tests for the admin ops live log tail.

GET /admin/api/v1/ops/logs/tail — SSE stream of in-memory log ring buffer.

Integration suite: tests the ``tail_logs`` async generator directly rather
than going through HTTP, because httpx's ``ASGITransport`` buffers the
entire response body — it cannot stream an infinite SSE connection.

The HTTP 401 guard is tested via a standard request.
"""

import asyncio
import json
import logging
import uuid

import pytest

from supython.admin import session as admin_session
from supython.admin.api.service_ops import tail_logs

_logger = logging.getLogger("supython.test.logs_tail")


def _human_readable_large(n: int) -> str:
    # Never return the raw integer so output has no privacy concern.
    if n == 0:
        return "zero"
    if n < 20:
        return "a few"
    if n < 100:
        return "some"
    if n < 300:
        return "many"
    return "a large number"


async def _collect_snapshot(**filters) -> list[dict]:
    """Read from ``tail_logs()`` until the snapshot event, then disconnect."""
    gen = tail_logs(**filters)
    try:
        async for frame in gen:
            if not frame.strip() or frame.startswith(":"):
                continue
            # Parse SSE frame
            for line in frame.strip().split("\n"):
                if line.startswith("event: logs:snapshot"):
                    continue
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    break
            else:
                continue
            return data if isinstance(data, list) else [data]
    finally:
        await gen.aclose()
    return []


async def _collect_append_until(predicate, timeout_s=10.0, **filters) -> list[dict]:
    """Read from ``tail_logs()`` until *predicate* matches an append event."""
    collected: list[dict] = []
    gen = tail_logs(**filters)
    try:
        while True:
            frame = await asyncio.wait_for(gen.__anext__(), timeout=timeout_s)
            if not frame.strip() or frame.startswith(":"):
                continue
            for line in frame.strip().split("\n"):
                if line.startswith("event: logs:append") or line.startswith("event: logs:snapshot"):
                    continue
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, list):
                        collected.extend(data)
                        for entry in data:
                            if predicate(entry):
                                return collected
                    elif isinstance(data, dict):
                        collected.append(data)
                        if predicate(data):
                            return collected
    except asyncio.TimeoutError:
        pass
    finally:
        await gen.aclose()
    return collected


@pytest.fixture
async def admin_user(pool):
    """Create a root admin user for the log tail tests."""
    from supython import passwords

    password = "correct horse battery staple"
    email = f"{uuid.uuid4().hex[:8]}@test.example"
    pw_hash = passwords.hash_password(password)
    async with pool.acquire() as conn:
        await conn.execute("delete from admin.admin_sessions")
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
        await conn.execute("delete from admin.admin_users where id = $1", admin_id)


# ── Smoke tests ───────────────────────────────────────────────────


async def test_logs_tail_401_without_session(client):
    """SSE endpoint returns 401 without admin session."""
    resp = await client.get("/admin/api/v1/ops/logs/tail")
    assert resp.status_code == 401


async def test_logs_tail_snapshot_has_entries(client, admin_user):
    """Snapshot contains log entries emitted before the tail connection."""
    await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )

    # Emit a known log line before connecting.
    marker = f"snapshot_marker_{uuid.uuid4().hex[:8]}"
    _logger.info(marker)

    snapshot = await _collect_snapshot()
    messages = [e.get("message", "") for e in snapshot]

    # Ring buffer is shared process-wide; the marker we just logged
    # must appear in the snapshot.
    assert any(marker in m for m in messages), (
        f"snapshot missing marker {marker!r}; got {_human_readable_large(len(messages))} entries"
    )


async def test_logs_tail_new_log_appends(client, admin_user):
    """A log emitted while tailing appears as an append event."""
    await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )

    marker = f"append_marker_{uuid.uuid4().hex[:8]}"

    # Emit the marker in 200ms so the generator is already polling.
    async def emit_later():
        await asyncio.sleep(0.2)
        _logger.info(marker)

    asyncio.create_task(emit_later())

    collected = await _collect_append_until(
        predicate=lambda e: marker in str(e.get("message", "")),
        timeout_s=10.0,
    )

    assert any(marker in str(e.get("message", "")) for e in collected), (
        f"never saw append with marker {marker!r}"
    )


async def test_logs_tail_level_filter(client, admin_user):
    """Level=ERROR filter excludes INFO messages."""
    await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )

    info_marker = f"info_filter_{uuid.uuid4().hex[:8]}"
    error_marker = f"error_filter_{uuid.uuid4().hex[:8]}"
    _logger.info(info_marker)
    _logger.error(error_marker)

    snapshot = await _collect_snapshot(level="ERROR")
    for entry in snapshot:
        msg = entry.get("message", "")
        assert info_marker not in msg, f"INFO message {info_marker!r} leaked through ERROR filter"


async def test_logs_tail_substring_filter(client, admin_user):
    """Substring filter returns only entries matching the needle."""
    await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )

    needle = f"needle_{uuid.uuid4().hex[:8]}"
    _logger.info(needle)

    snapshot = await _collect_snapshot(substring=needle)
    for entry in snapshot:
        msg = entry.get("message", "")
        assert needle.lower() in msg.lower(), f"substring filter missed: {msg!r}"


async def test_logs_tail_request_id_filter(client, admin_user):
    """Request ID filter returns only entries matching that exact request_id."""
    await client.post(
        "/admin/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )

    fake_rid = f"fake_{uuid.uuid4().hex}"

    snapshot = await _collect_snapshot(request_id=fake_rid)
    for entry in snapshot:
        rid = entry.get("request_id", "")
        assert rid == fake_rid, f"request_id filter failed: got {rid!r}, expected {fake_rid!r}"
    # With a fake request_id we expect zero entries from the snapshot
    assert len(snapshot) == 0, (
        f"expected zero entries for fake request_id, got {_human_readable_large(len(snapshot))}"
    )
