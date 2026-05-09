import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg

from ..errors import AdminError
from ..schemas import (
    AdminAuditPage,
    AdminUser,
    AdminUserDetail,
    AdminUsersPage,
    AuditEvent,
    Identity,
    RefreshToken,
    RefreshTokensPage,
)

DEFAULT_BAN_SECONDS = 24 * 60 * 60
RECENT_AUDIT_LIMIT = 20


def _row_to_admin_user(row: asyncpg.Record) -> AdminUser:
    return AdminUser(
        id=row["id"],
        email=row["email"],
        created_at=row["created_at"],
        last_sign_in_at=row["last_sign_in_at"],
        banned_until=row["banned_until"],
        email_confirmed_at=row["email_confirmed_at"],
    )


def _row_to_identity(row: asyncpg.Record) -> Identity:
    raw = row["identity_data"]
    data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return Identity(
        id=row["id"],
        user_id=row["user_id"],
        provider=row["provider"],
        provider_user_id=row["provider_user_id"],
        identity_data=data,
        created_at=row["created_at"],
    )


def _row_to_audit(row: asyncpg.Record) -> AuditEvent:
    raw = row["payload"]
    payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return AuditEvent(
        id=row["id"],
        user_id=row["user_id"],
        event=row["event"],
        ip=str(row["ip"]) if row["ip"] is not None else None,
        ua=row["ua"],
        payload=payload,
        created_at=row["created_at"],
    )


async def search_users(
    conn: asyncpg.Connection,
    search: str | None,
    confirmed: bool | None,
    banned: bool | None,
    limit: int,
    offset: int,
) -> AdminUsersPage:
    if limit <= 0 or limit > 200:
        raise AdminError("invalid_limit", "limit must be between 1 and 200", 422)
    if offset < 0:
        raise AdminError("invalid_offset", "offset must be >= 0", 422)
    pattern = f"%{search}%" if search else None
    where_sql = """
        ($1::text is null or email ilike $1)
        and ($2::bool is null or (email_confirmed_at is not null) = $2)
        and ($3::bool is null or (banned_until is not null and banned_until > now()) = $3)
    """
    rows = await conn.fetch(
        f"""
        select id, email, created_at, last_sign_in_at, banned_until, email_confirmed_at
        from auth.users
        where {where_sql}
        order by created_at desc
        limit $4 offset $5
        """,
        pattern,
        confirmed,
        banned,
        limit,
        offset,
    )
    total = await conn.fetchval(
        f"""
        select count(*)
        from auth.users
        where {where_sql}
        """,
        pattern,
        confirmed,
        banned,
    )
    return AdminUsersPage(
        rows=[_row_to_admin_user(r) for r in rows],
        total=total or 0,
    )


async def get_user_detail(conn: asyncpg.Connection, user_id: UUID) -> AdminUserDetail:
    row = await conn.fetchrow(
        """
        select id, email, created_at, last_sign_in_at, banned_until, email_confirmed_at
        from auth.users
        where id = $1
        """,
        user_id,
    )
    if row is None:
        raise AdminError("not_found", "user not found", 404)
    identities = await conn.fetch(
        """
        select id, user_id, provider, provider_user_id, identity_data, created_at
        from auth.identities
        where user_id = $1
        order by created_at desc
        """,
        user_id,
    )
    audit = await conn.fetch(
        """
        select id, user_id, event, ip, ua, payload, created_at
        from auth.audit_log
        where user_id = $1
        order by created_at desc
        limit $2
        """,
        user_id,
        RECENT_AUDIT_LIMIT,
    )
    return AdminUserDetail(
        user=_row_to_admin_user(row),
        identities=[_row_to_identity(r) for r in identities],
        recent_audit=[_row_to_audit(r) for r in audit],
    )


async def ban_user(
    conn: asyncpg.Connection, user_id: UUID, duration_seconds: int | None
) -> datetime:
    seconds = duration_seconds if duration_seconds is not None else DEFAULT_BAN_SECONDS
    if seconds <= 0:
        raise AdminError("invalid_duration", "duration_seconds must be > 0", 422)
    banned_until = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
    updated = await conn.fetchval(
        """
        update auth.users
        set banned_until = $2, updated_at = now()
        where id = $1
        returning banned_until
        """,
        user_id,
        banned_until,
    )
    if updated is None:
        raise AdminError("not_found", "user not found", 404)
    return updated


async def unban_user(conn: asyncpg.Connection, user_id: UUID) -> None:
    updated = await conn.fetchval(
        """
        update auth.users
        set banned_until = null, updated_at = now()
        where id = $1
        returning id
        """,
        user_id,
    )
    if updated is None:
        raise AdminError("not_found", "user not found", 404)


async def force_logout(conn: asyncpg.Connection, user_id: UUID) -> int:
    exists = await conn.fetchval(
        "select 1 from auth.users where id = $1",
        user_id,
    )
    if exists is None:
        raise AdminError("not_found", "user not found", 404)
    revoked = await conn.fetch(
        """
        update auth.refresh_tokens
        set revoked = true
        where user_id = $1 and revoked = false
        returning id
        """,
        user_id,
    )
    return len(revoked)


async def write_user_audit(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    event: str,
    payload: dict[str, Any],
    ip: str | None,
    ua: str | None,
) -> None:
    await conn.execute(
        """
        insert into auth.audit_log (user_id, event, ip, ua, payload)
        values ($1, $2, $3::inet, $4, $5::jsonb)
        """,
        user_id,
        event,
        ip,
        ua,
        json.dumps(payload),
    )


def _row_to_refresh_token(row: asyncpg.Record) -> RefreshToken:
    return RefreshToken(
        id=row["id"],
        user_id=row["user_id"],
        token=row["token"],
        parent=row["parent"],
        revoked=row["revoked"],
        created_at=row["created_at"],
    )


async def list_refresh_tokens(
    conn: asyncpg.Connection,
    user_id: UUID | None,
    limit: int,
    offset: int,
) -> RefreshTokensPage:
    if limit <= 0 or limit > 200:
        raise AdminError("invalid_limit", "limit must be between 1 and 200", 422)
    if offset < 0:
        raise AdminError("invalid_offset", "offset must be >= 0", 422)

    rows = await conn.fetch(
        """
        select id, user_id, token, parent, revoked, created_at
        from auth.refresh_tokens
        where ($1::uuid is null or user_id = $1)
        order by created_at desc
        limit $2 offset $3
        """,
        user_id,
        limit,
        offset,
    )
    total = await conn.fetchval(
        """
        select count(*)
        from auth.refresh_tokens
        where ($1::uuid is null or user_id = $1)
        """,
        user_id,
    )
    return RefreshTokensPage(
        rows=[_row_to_refresh_token(r) for r in rows],
        total=total or 0,
    )


async def revoke_refresh_token(conn: asyncpg.Connection, token_id: int) -> UUID:
    """Revoke a single refresh token. Returns the owning user_id for audit."""
    row = await conn.fetchrow(
        """
        update auth.refresh_tokens
        set revoked = true
        where id = $1
        returning id, user_id
        """,
        token_id,
    )
    if row is None:
        raise AdminError("not_found", "refresh token not found", 404)
    return row["user_id"]


async def list_audit_log(
    conn: asyncpg.Connection,
    event: str | None,
    ip: str | None,
    from_date: str | None,
    to_date: str | None,
    limit: int,
    offset: int,
) -> AdminAuditPage:
    if limit <= 0 or limit > 200:
        raise AdminError("invalid_limit", "limit must be between 1 and 200", 422)
    if offset < 0:
        raise AdminError("invalid_offset", "offset must be >= 0", 422)

    try:
        from_date_d = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else None
        to_date_d = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else None
    except ValueError as exc:
        raise AdminError("invalid_date", "dates must be YYYY-MM-DD", 422) from exc

    ip_pattern = f"%{ip}%" if ip else None

    rows = await conn.fetch(
        """
        select id, user_id, event, ip, ua, payload, created_at
        from auth.audit_log
        where ($1::text is null or event = $1)
          and ($2::text is null or ip::text ilike $2)
          and ($3::date is null or created_at::date >= $3)
          and ($4::date is null or created_at::date <= $4)
        order by created_at desc
        limit $5 offset $6
        """,
        event,
        ip_pattern,
        from_date_d,
        to_date_d,
        limit,
        offset,
    )
    total = await conn.fetchval(
        """
        select count(*)
        from auth.audit_log
        where ($1::text is null or event = $1)
          and ($2::text is null or ip::text ilike $2)
          and ($3::date is null or created_at::date >= $3)
          and ($4::date is null or created_at::date <= $4)
        """,
        event,
        ip_pattern,
        from_date_d,
        to_date_d,
    )
    return AdminAuditPage(
        rows=[_row_to_audit(r) for r in rows],
        total=total or 0,
    )
