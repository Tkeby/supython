from typing import Literal
from uuid import UUID

import asyncpg

from ... import db
from ...storage import service as storage_service
from ...storage.backends import BackendError, StorageBackend, make_object_key
from ..errors import AdminError
from ..schemas import (
    AdminBucket,
    AdminObject,
    AdminObjectsPage,
    AdminSignedUrlResponse,
)
from .service_db import preview_claims


def _row_to_bucket(row: asyncpg.Record) -> AdminBucket:
    return AdminBucket(
        id=row["id"],
        name=row["name"],
        owner=row["owner"],
        public=row["public"],
        object_count=row["object_count"],
        total_size=row["total_size"],
        file_size_limit=row["file_size_limit"],
        allowed_mime_types=row["allowed_mime_types"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_object(row: asyncpg.Record) -> AdminObject:
    return AdminObject(
        id=row["id"],
        bucket=row["bucket_name"],
        name=row["name"],
        owner=row["owner"],
        size=row["size"],
        mime_type=row["mime_type"],
        etag=row["etag"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def list_buckets(conn: asyncpg.Connection) -> list[AdminBucket]:
    rows = await conn.fetch(
        """
        select b.id, b.name, b.owner, b.public,
               b.file_size_limit, b.allowed_mime_types,
               b.created_at, b.updated_at,
               coalesce(o.count, 0)::bigint as object_count,
               coalesce(o.total_size, 0)::bigint as total_size
        from storage.buckets b
        left join (
            select bucket_id,
                   count(*) as count,
                   sum(size) as total_size
            from storage.objects
            group by bucket_id
        ) o on o.bucket_id = b.id
        order by b.name
        """
    )
    return [_row_to_bucket(r) for r in rows]


async def list_bucket_objects(
    conn: asyncpg.Connection,
    bucket: str,
    prefix: str | None,
    limit: int,
    offset: int,
) -> AdminObjectsPage:
    if limit <= 0 or limit > 500:
        raise AdminError("invalid_limit", "limit must be between 1 and 500", 422)
    if offset < 0:
        raise AdminError("invalid_offset", "offset must be >= 0", 422)
    bucket_row = await conn.fetchrow(
        "select id from storage.buckets where name = $1",
        bucket,
    )
    if bucket_row is None:
        raise AdminError("bucket_not_found", f"Bucket {bucket!r} not found", 404)
    bucket_id = bucket_row["id"]
    rows = await conn.fetch(
        """
        select o.id, o.bucket_id, o.name, o.owner, o.size, o.mime_type,
               o.etag, o.created_at, o.updated_at,
               $1::text as bucket_name
        from storage.objects o
        where o.bucket_id = $2
          and ($3::text is null or o.name like $3 || '%')
        order by o.name
        limit $4 offset $5
        """,
        bucket,
        bucket_id,
        prefix,
        limit,
        offset,
    )
    total = await conn.fetchval(
        """
        select count(*)
        from storage.objects
        where bucket_id = $1
          and ($2::text is null or name like $2 || '%')
        """,
        bucket_id,
        prefix,
    )
    return AdminObjectsPage(
        rows=[_row_to_object(r) for r in rows],
        total=total or 0,
        prefix=prefix,
    )


async def _resolve_object(
    conn: asyncpg.Connection, object_id: UUID
) -> tuple[str, str]:
    row = await conn.fetchrow(
        """
        select b.name as bucket_name, o.name
        from storage.objects o
        join storage.buckets b on b.id = o.bucket_id
        where o.id = $1
        """,
        object_id,
    )
    if row is None:
        raise AdminError("object_not_found", "Object not found", 404)
    return row["bucket_name"], row["name"]


async def sign_object(
    object_id: UUID,
    expires_in: int | None,
    role: Literal["service_role", "authenticated", "anon"],
    impersonate_sub: UUID | None,
) -> tuple[AdminSignedUrlResponse, str, str]:
    """Sign a download URL for ``object_id``.

    Resolution happens under ``service_role`` so the admin can always find the
    object. The signing call itself runs under ``role`` so RLS gates whether
    that role would have been able to issue the URL — the disclosed
    ``signed_under_role`` tells the operator which surface they granted
    access through.
    """
    async with db.as_service_role() as conn:
        bucket_name, path = await _resolve_object(conn, object_id)

    if role == "service_role":
        async with db.as_service_role() as conn:
            try:
                signed = await storage_service.issue_signed_url(
                    conn,
                    bucket_name=bucket_name,
                    path=path,
                    expires_in=expires_in,
                )
            except storage_service.StorageError as exc:
                raise AdminError(exc.code, exc.message, exc.status) from exc
    else:
        claims = preview_claims(role, impersonate_sub)
        async with db.as_role(role, claims) as conn:
            try:
                signed = await storage_service.issue_signed_url(
                    conn,
                    bucket_name=bucket_name,
                    path=path,
                    expires_in=expires_in,
                )
            except storage_service.StorageError as exc:
                raise AdminError(exc.code, exc.message, exc.status) from exc

    response = AdminSignedUrlResponse(
        signed_url=signed.signed_url,
        token=signed.token,
        expires_at=signed.expires_at,
        expires_in=signed.expires_in,
        signed_under_role=role,
    )
    return response, bucket_name, path


async def delete_object(
    backend: StorageBackend, object_id: UUID
) -> tuple[str, str]:
    """Delete object metadata + bytes. Returns ``(bucket_name, path)`` for audit."""
    async with db.as_service_role() as conn:
        row = await conn.fetchrow(
            """
            select b.name as bucket_name, o.name
            from storage.objects o
            join storage.buckets b on b.id = o.bucket_id
            where o.id = $1
            """,
            object_id,
        )
        if row is None:
            raise AdminError("object_not_found", "Object not found", 404)
        bucket_name = row["bucket_name"]
        path = row["name"]
        await conn.execute(
            "delete from storage.objects where id = $1",
            object_id,
        )

    try:
        await backend.delete(make_object_key(bucket_name, path))
    except BackendError:
        # Orphaned bytes after a successful metadata delete are acceptable per
        # the storage contract. Metadata is the authority.
        pass

    return bucket_name, path
