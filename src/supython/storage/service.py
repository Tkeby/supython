"""Storage business logic.

Pure async functions. Take a role-scoped ``conn`` (from ``db.as_role(...)``)
plus a ``StorageBackend``. The metadata layer is the authority for who may
do what — every request first hits Postgres for an RLS-checked
SELECT/INSERT, then touches backend bytes. Orphaned bytes after a crash are
acceptable; orphaned metadata is not.
"""

import logging
from collections.abc import AsyncIterator

import asyncpg

from ..settings import get_settings
from . import signing
from .backends import BackendError, ObjectStream, StorageBackend, make_object_key
from .schemas import BucketResponse, ObjectResponse, SignedUrlResponse

logger = logging.getLogger(__name__)


class StorageError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------


def _row_to_bucket(row: asyncpg.Record) -> BucketResponse:
    return BucketResponse(
        id=row["id"],
        name=row["name"],
        owner=row["owner"],
        public=row["public"],
        file_size_limit=row["file_size_limit"],
        allowed_mime_types=row["allowed_mime_types"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_object(row: asyncpg.Record) -> ObjectResponse:
    return ObjectResponse(
        id=row["id"],
        bucket_id=row["bucket_id"],
        bucket=row["bucket_name"],
        name=row["name"],
        owner=row["owner"],
        size=row["size"],
        mime_type=row["mime_type"],
        etag=row["etag"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------


async def create_bucket(
    conn: asyncpg.Connection,
    *,
    name: str,
    public: bool,
    file_size_limit: int | None,
    allowed_mime_types: list[str] | None,
) -> BucketResponse:
    try:
        row = await conn.fetchrow(
            """
            insert into storage.buckets
                (name, owner, public, file_size_limit, allowed_mime_types)
            values ($1, auth.uid(), $2, $3, $4)
            returning id, name, owner, public, file_size_limit,
                      allowed_mime_types, created_at, updated_at
            """,
            name,
            public,
            file_size_limit,
            allowed_mime_types,
        )
    except asyncpg.UniqueViolationError as exc:
        raise StorageError("bucket_exists", f"Bucket {name!r} already exists", 409) from exc
    except asyncpg.InsufficientPrivilegeError as exc:
        raise StorageError("forbidden", "Not allowed to create buckets", 403) from exc

    if row is None:
        raise StorageError("forbidden", "Not allowed to create buckets", 403)
    return _row_to_bucket(row)


async def list_buckets(conn: asyncpg.Connection) -> list[BucketResponse]:
    rows = await conn.fetch(
        """
        select id, name, owner, public, file_size_limit,
               allowed_mime_types, created_at, updated_at
        from storage.buckets
        order by name
        """
    )
    return [_row_to_bucket(r) for r in rows]


async def get_bucket(conn: asyncpg.Connection, name: str) -> BucketResponse:
    row = await conn.fetchrow(
        """
        select id, name, owner, public, file_size_limit,
               allowed_mime_types, created_at, updated_at
        from storage.buckets
        where name = $1
        """,
        name,
    )
    if row is None:
        raise StorageError("bucket_not_found", f"Bucket {name!r} not found", 404)
    return _row_to_bucket(row)


async def delete_bucket(
    conn: asyncpg.Connection,
    backend: StorageBackend,
    name: str,
) -> None:
    bucket = await get_bucket(conn, name)
    keys = await conn.fetch(
        "select name from storage.objects where bucket_id = $1",
        bucket.id,
    )
    result = await conn.execute(
        "delete from storage.buckets where name = $1",
        name,
    )
    if result.endswith(" 0"):
        raise StorageError("bucket_not_found", f"Bucket {name!r} not found", 404)

    for k in keys:
        try:
            await backend.delete(make_object_key(name, k["name"]))
        except BackendError:
            logger.warning(
                "orphaned bytes after bucket delete: bucket=%s key=%s",
                name,
                k["name"],
            )


# ---------------------------------------------------------------------------
# Objects
# ---------------------------------------------------------------------------


async def _fetch_bucket_for_object(
    conn: asyncpg.Connection, bucket_name: str
) -> BucketResponse:
    """Fetch a bucket by name, raising ``bucket_not_found`` consistently."""
    return await get_bucket(conn, bucket_name)


def _check_mime(bucket: BucketResponse, mime_type: str | None) -> None:
    if not bucket.allowed_mime_types:
        return
    if mime_type is None or mime_type not in bucket.allowed_mime_types:
        raise StorageError(
            "mime_not_allowed",
            f"Mime type {mime_type!r} is not allowed in bucket {bucket.name!r}",
            415,
        )


async def _enforce_max_size(
    it: AsyncIterator[bytes], max_bytes: int
) -> AsyncIterator[bytes]:
    total = 0
    async for chunk in it:
        total += len(chunk)
        if total > max_bytes:
            raise StorageError(
                "file_too_large",
                f"Upload exceeds {max_bytes} bytes",
                413,
            )
        yield chunk


async def upload_object(
    conn: asyncpg.Connection,
    backend: StorageBackend,
    *,
    bucket_name: str,
    path: str,
    data: AsyncIterator[bytes],
    content_type: str | None,
) -> ObjectResponse:
    settings = get_settings()
    bucket = await _fetch_bucket_for_object(conn, bucket_name)
    _check_mime(bucket, content_type)

    max_bytes = settings.storage_max_upload_bytes
    if bucket.file_size_limit is not None:
        max_bytes = min(max_bytes, bucket.file_size_limit)

    key = make_object_key(bucket_name, path)
    try:
        stat = await backend.put(key, _enforce_max_size(data, max_bytes), content_type)
    except StorageError:
        # size limit raised mid-stream; backend wrote a partial file — try to clean up.
        try:
            await backend.delete(key)
        except BackendError:
            logger.warning("failed to clean up partial upload at %s", key)
        raise
    except BackendError as exc:
        raise StorageError("backend_error", str(exc), 500) from exc

    try:
        row = await conn.fetchrow(
            """
            insert into storage.objects
                (bucket_id, name, owner, size, mime_type, etag)
            values ($1, $2, auth.uid(), $3, $4, $5)
            returning id, bucket_id, name, owner, size, mime_type, etag,
                      created_at, updated_at, $6::text as bucket_name
            """,
            bucket.id,
            path,
            stat.size,
            content_type,
            stat.etag,
            bucket_name,
        )
    except asyncpg.UniqueViolationError as exc:
        await _safe_delete(backend, key)
        raise StorageError(
            "object_exists",
            f"Object {bucket_name}/{path} already exists",
            409,
        ) from exc
    except asyncpg.InsufficientPrivilegeError as exc:
        await _safe_delete(backend, key)
        raise StorageError("forbidden", "Not allowed to write here", 403) from exc

    if row is None:
        await _safe_delete(backend, key)
        raise StorageError("forbidden", "Not allowed to write here", 403)

    return _row_to_object(row)


async def _safe_delete(backend: StorageBackend, key: str) -> None:
    try:
        await backend.delete(key)
    except BackendError:
        logger.warning("orphaned bytes at %s after metadata insert failed", key)


async def _select_object_row(
    conn: asyncpg.Connection, bucket_name: str, path: str
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        select o.id, o.bucket_id, o.name, o.owner, o.size, o.mime_type,
               o.etag, o.created_at, o.updated_at,
               b.name as bucket_name
        from storage.objects o
        join storage.buckets b on b.id = o.bucket_id
        where b.name = $1 and o.name = $2
        """,
        bucket_name,
        path,
    )
    if row is None:
        raise StorageError(
            "object_not_found",
            f"Object {bucket_name}/{path} not found",
            404,
        )
    return row


async def get_object_metadata(
    conn: asyncpg.Connection, bucket_name: str, path: str
) -> ObjectResponse:
    row = await _select_object_row(conn, bucket_name, path)
    return _row_to_object(row)


async def download_object(
    conn: asyncpg.Connection,
    backend: StorageBackend,
    *,
    bucket_name: str,
    path: str,
    byte_range: tuple[int, int | None] | None = None,
) -> tuple[ObjectResponse, ObjectStream]:
    row = await _select_object_row(conn, bucket_name, path)
    obj = _row_to_object(row)
    key = make_object_key(bucket_name, path)
    try:
        stream = await backend.get(key, byte_range=byte_range)
    except BackendError as exc:
        raise StorageError("object_not_found", str(exc), 404) from exc

    if not stream.content_type and obj.mime_type:
        stream.content_type = obj.mime_type
    if not stream.etag and obj.etag:
        stream.etag = obj.etag
    return obj, stream


async def delete_object(
    conn: asyncpg.Connection,
    backend: StorageBackend,
    *,
    bucket_name: str,
    path: str,
) -> None:
    row = await _select_object_row(conn, bucket_name, path)
    bucket_id = row["bucket_id"]
    result = await conn.execute(
        "delete from storage.objects where bucket_id = $1 and name = $2",
        bucket_id,
        path,
    )
    if result.endswith(" 0"):
        raise StorageError(
            "object_not_found",
            f"Object {bucket_name}/{path} not found",
            404,
        )
    try:
        await backend.delete(make_object_key(bucket_name, path))
    except BackendError:
        logger.warning(
            "orphaned bytes after object delete: %s/%s", bucket_name, path
        )


# ---------------------------------------------------------------------------
# Signed URLs
# ---------------------------------------------------------------------------


def _build_signed_url(bucket: str, path: str, token: str) -> str:
    site = get_settings().site_url.rstrip("/")
    return f"{site}/storage/v1/object/signed/{bucket}/{path}?token={token}"


async def issue_signed_url(
    conn: asyncpg.Connection,
    *,
    bucket_name: str,
    path: str,
    expires_in: int | None,
) -> SignedUrlResponse:
    # RLS-bound read confirms the caller is allowed to share this object.
    await _select_object_row(conn, bucket_name, path)
    settings = get_settings()
    ttl = expires_in or settings.storage_signed_url_default_ttl
    token, expires_at = signing.sign(bucket_name, path, ttl)
    return SignedUrlResponse(
        signed_url=_build_signed_url(bucket_name, path, token),
        token=token,
        expires_at=expires_at,
        expires_in=ttl,
    )


async def verify_signed_download(
    conn: asyncpg.Connection,
    backend: StorageBackend,
    *,
    bucket_name: str,
    path: str,
    token: str,
    byte_range: tuple[int, int | None] | None = None,
) -> tuple[ObjectResponse, ObjectStream]:
    """Verify ``token``, then stream from backend.

    ``conn`` should be a service-role connection — the JWT is absent here, the
    signature is the entire authorization story.
    """
    try:
        signing.verify(token, bucket_name, path)
    except signing.ExpiredSignature as exc:
        raise StorageError("signature_expired", "Signed URL has expired", 400) from exc
    except signing.SignatureError as exc:
        raise StorageError("invalid_signature", str(exc), 400) from exc

    return await download_object(
        conn,
        backend,
        bucket_name=bucket_name,
        path=path,
        byte_range=byte_range,
    )


async def download_public_object(
    conn: asyncpg.Connection,
    backend: StorageBackend,
    *,
    bucket_name: str,
    path: str,
    byte_range: tuple[int, int | None] | None = None,
) -> tuple[ObjectResponse, ObjectStream]:
    """Fetch an object from a ``public=true`` bucket.

    Caller is anonymous; ``conn`` should be ``role=anon`` so the policy
    ``objects: public bucket read`` is the only thing that lets the SELECT
    succeed. A non-public bucket returns 404 here without leaking that the
    object exists.
    """
    return await download_object(
        conn,
        backend,
        bucket_name=bucket_name,
        path=path,
        byte_range=byte_range,
    )


# Re-export for `from .service import *` convenience
__all__ = [
    "StorageError",
    "create_bucket",
    "list_buckets",
    "get_bucket",
    "delete_bucket",
    "upload_object",
    "download_object",
    "delete_object",
    "get_object_metadata",
    "issue_signed_url",
    "verify_signed_download",
    "download_public_object",
]
