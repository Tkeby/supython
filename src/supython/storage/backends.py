"""Storage backends.

A backend is the *bytes* layer. Object metadata (ownership, RLS, mime) lives
in `storage.objects` in Postgres; the backend only knows about opaque keys.

Two implementations:

- ``LocalBackend`` writes files under a configurable root using the stdlib.
- ``S3Backend`` proxies to S3-compatible object storage via the optional
  ``aioboto3`` dependency (``pip install supython[s3]``).

Both stream bytes — nothing is ever fully buffered in memory.
"""

import contextlib
import hashlib
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from ..settings import get_settings


@dataclass
class ObjectStat:
    key: str
    size: int
    etag: str
    content_type: str | None


@dataclass
class ObjectStream:
    iterator: AsyncIterator[bytes]
    content_length: int
    content_type: str | None
    etag: str
    status_code: int
    content_range: str | None


class BackendError(Exception):
    """Raised for backend-level failures (missing key, IO error, etc.)."""


class StorageBackend(Protocol):
    async def put(
        self,
        key: str,
        data: AsyncIterator[bytes],
        content_type: str | None,
    ) -> ObjectStat: ...

    async def get(
        self,
        key: str,
        *,
        byte_range: tuple[int, int | None] | None = None,
    ) -> ObjectStream: ...

    async def stat(self, key: str) -> ObjectStat | None: ...

    async def delete(self, key: str) -> None: ...


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------


_CHUNK = 64 * 1024


class LocalBackend:
    """Bytes on the local filesystem under ``root``.

    Keys are joined with ``root`` and resolved; any key that escapes the root
    (via ``..`` or absolute paths) is rejected.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise BackendError(f"Invalid key: {key!r}")
        candidate = (self._root / key).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise BackendError(f"Key escapes root: {key!r}") from exc
        return candidate

    async def put(
        self,
        key: str,
        data: AsyncIterator[bytes],
        content_type: str | None,
    ) -> ObjectStat:
        import asyncio

        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha256()
        size = 0

        def _open() -> IO[bytes]:
            return open(path, "wb")

        f = await asyncio.to_thread(_open)
        try:
            async for chunk in data:
                if not chunk:
                    continue
                hasher.update(chunk)
                size += len(chunk)
                await asyncio.to_thread(f.write, chunk)
        except BaseException:
            await asyncio.to_thread(f.close)
            with contextlib.suppress(FileNotFoundError):
                await asyncio.to_thread(path.unlink)
            raise
        else:
            await asyncio.to_thread(f.close)

        return ObjectStat(
            key=key,
            size=size,
            etag=hasher.hexdigest(),
            content_type=content_type,
        )

    async def get(
        self,
        key: str,
        *,
        byte_range: tuple[int, int | None] | None = None,
    ) -> ObjectStream:
        import asyncio

        path = self._resolve(key)
        if not path.exists():
            raise BackendError(f"Object not found: {key!r}")

        total = path.stat().st_size
        start = 0
        end = total - 1
        status = 200
        content_range: str | None = None

        if byte_range is not None:
            start, end_opt = byte_range
            end = total - 1 if end_opt is None else min(end_opt, total - 1)
            if start < 0 or start > end:
                raise BackendError(f"Invalid range {byte_range} for size {total}")
            status = 206
            content_range = f"bytes {start}-{end}/{total}"

        length = end - start + 1

        async def _iter() -> AsyncIterator[bytes]:
            remaining = length

            def _open() -> IO[bytes]:
                fh = open(path, "rb")  # noqa: SIM115 — closed in finally below
                fh.seek(start)
                return fh

            fh = await asyncio.to_thread(_open)
            try:
                while remaining > 0:
                    to_read = min(_CHUNK, remaining)
                    chunk = await asyncio.to_thread(fh.read, to_read)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            finally:
                await asyncio.to_thread(fh.close)

        return ObjectStream(
            iterator=_iter(),
            content_length=length,
            content_type=None,
            etag="",
            status_code=status,
            content_range=content_range,
        )

    async def stat(self, key: str) -> ObjectStat | None:
        path = self._resolve(key)
        if not path.exists():
            return None
        return ObjectStat(
            key=key,
            size=path.stat().st_size,
            etag="",
            content_type=None,
        )

    async def delete(self, key: str) -> None:
        import asyncio

        path = self._resolve(key)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            return


# ---------------------------------------------------------------------------
# S3 backend (optional)
# ---------------------------------------------------------------------------


class S3Backend:
    """S3-compatible backend.

    All logical buckets are prefixed into a single physical bucket configured
    via ``storage_s3_bucket``. ``aioboto3`` is imported lazily so the cost is
    only paid when the backend is actually selected.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        if not bucket:
            raise BackendError("S3Backend requires storage_s3_bucket")
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._session = None

    def _client(self):
        try:
            import aioboto3
        except ImportError as exc:
            raise BackendError(
                "S3Backend requires aioboto3. Install with `pip install supython[s3]`."
            ) from exc
        if self._session is None:
            self._session = aioboto3.Session(
                aws_access_key_id=self._access_key_id or None,
                aws_secret_access_key=self._secret_access_key or None,
                region_name=self._region,
            )
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
        )

    async def put(
        self,
        key: str,
        data: AsyncIterator[bytes],
        content_type: str | None,
    ) -> ObjectStat:
        hasher = hashlib.sha256()
        chunks: list[bytes] = []
        size = 0
        async for chunk in data:
            if not chunk:
                continue
            hasher.update(chunk)
            chunks.append(chunk)
            size += len(chunk)
        body = b"".join(chunks)

        kwargs: dict = {"Bucket": self._bucket, "Key": key, "Body": body}
        if content_type:
            kwargs["ContentType"] = content_type

        async with self._client() as s3:
            resp = await s3.put_object(**kwargs)

        etag = (resp.get("ETag") or "").strip('"') or hasher.hexdigest()
        return ObjectStat(key=key, size=size, etag=etag, content_type=content_type)

    async def get(
        self,
        key: str,
        *,
        byte_range: tuple[int, int | None] | None = None,
    ) -> ObjectStream:
        kwargs: dict = {"Bucket": self._bucket, "Key": key}
        status = 200
        content_range: str | None = None
        if byte_range is not None:
            start, end_opt = byte_range
            end_part = "" if end_opt is None else str(end_opt)
            kwargs["Range"] = f"bytes={start}-{end_part}"
            status = 206

        client_ctx = self._client()
        s3 = await client_ctx.__aenter__()
        try:
            resp = await s3.get_object(**kwargs)
        except Exception:
            await client_ctx.__aexit__(None, None, None)
            raise

        body = resp["Body"]
        length = int(resp.get("ContentLength", 0))
        content_type = resp.get("ContentType")
        etag = (resp.get("ETag") or "").strip('"')
        content_range = resp.get("ContentRange")
        if status == 206 and content_range and not content_range.startswith("bytes "):
            content_range = f"bytes {content_range}"

        async def _iter() -> AsyncIterator[bytes]:
            try:
                async for chunk in body.iter_chunks(_CHUNK):
                    yield chunk
            finally:
                await client_ctx.__aexit__(None, None, None)

        return ObjectStream(
            iterator=_iter(),
            content_length=length,
            content_type=content_type,
            etag=etag,
            status_code=status,
            content_range=content_range,
        )

    async def stat(self, key: str) -> ObjectStat | None:
        async with self._client() as s3:
            try:
                resp = await s3.head_object(Bucket=self._bucket, Key=key)
            except Exception:
                return None
        return ObjectStat(
            key=key,
            size=int(resp.get("ContentLength", 0)),
            etag=(resp.get("ETag") or "").strip('"'),
            content_type=resp.get("ContentType"),
        )

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


_backend: StorageBackend | None = None


def get_backend() -> StorageBackend:
    """Return the process-wide backend chosen by settings."""
    global _backend
    if _backend is not None:
        return _backend
    s = get_settings()
    if s.storage_backend == "local":
        _backend = LocalBackend(s.storage_local_root)
    elif s.storage_backend == "s3":
        _backend = S3Backend(
            bucket=s.storage_s3_bucket,
            endpoint_url=s.storage_s3_endpoint,
            region=s.storage_s3_region,
            access_key_id=s.storage_s3_access_key_id,
            secret_access_key=s.storage_s3_secret_access_key,
        )
    else:
        raise BackendError(f"Unknown storage backend: {s.storage_backend!r}")
    return _backend


def reset_backend() -> None:
    """Drop the cached backend; tests re-init with overridden settings."""
    global _backend
    _backend = None


def make_object_key(bucket_name: str, path: str) -> str:
    """Compose the backend key for a logical (bucket, path) pair."""
    return f"{bucket_name}/{path.lstrip('/')}"
