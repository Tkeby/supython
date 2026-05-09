"""HTTP surface for storage. Thin: parse, delegate, translate, stream."""

from collections.abc import AsyncIterator
from typing import Annotated, Any

import jwt
from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from .. import db, tokens
from . import service
from .backends import ObjectStream, get_backend
from .schemas import (
    BucketResponse,
    CreateBucketRequest,
    ObjectResponse,
    SignedUrlRequest,
    SignedUrlResponse,
)

router = APIRouter(prefix="/storage/v1", tags=["storage"])


_UPLOAD_CHUNK = 64 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _storage_error(exc: service.StorageError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": exc.message},
    )


async def _current_claims(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return the decoded JWT claims so we can pump them into ``as_role``."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        return tokens.decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}"
        ) from exc


def _claims_role(claims: dict[str, Any]) -> str:
    role = claims.get("role")
    if not isinstance(role, str) or not role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing role claim")
    return role


def _parse_range(header: str | None, total_unknown: bool = True) -> tuple[int, int | None] | None:
    """Parse an HTTP ``Range: bytes=START-END`` header. Returns None if absent.

    Only single-range, byte-unit requests are supported. Multi-range requests
    are intentionally rejected — they materially complicate streaming and are
    rare in practice.
    """
    if not header:
        return None
    if not header.lower().startswith("bytes="):
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            "Only byte ranges are supported",
        )
    spec = header.split("=", 1)[1].strip()
    if "," in spec:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            "Multi-range requests are not supported",
        )
    if "-" not in spec:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            "Malformed range",
        )
    start_s, end_s = spec.split("-", 1)
    try:
        start = int(start_s) if start_s else 0
        end: int | None = int(end_s) if end_s else None
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            "Malformed range",
        ) from exc
    return start, end


def _stream_response(stream: ObjectStream, *, filename: str | None = None) -> StreamingResponse:
    headers: dict[str, str] = {
        "content-length": str(stream.content_length),
        "accept-ranges": "bytes",
    }
    if stream.etag:
        headers["etag"] = stream.etag
    if stream.content_range:
        headers["content-range"] = stream.content_range
    if filename:
        headers["content-disposition"] = f'inline; filename="{filename}"'
    media_type = stream.content_type or "application/octet-stream"
    return StreamingResponse(
        stream.iterator,
        status_code=stream.status_code,
        headers=headers,
        media_type=media_type,
    )


async def _file_iterator(file: UploadFile) -> AsyncIterator[bytes]:
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        yield chunk


# ---------------------------------------------------------------------------
# Bucket endpoints
# ---------------------------------------------------------------------------


@router.post("/bucket", response_model=BucketResponse, status_code=201)
async def create_bucket(
    payload: CreateBucketRequest,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
) -> BucketResponse:
    try:
        async with db.as_role(_claims_role(claims), claims) as conn:
            return await service.create_bucket(
                conn,
                name=payload.name,
                public=payload.public,
                file_size_limit=payload.file_size_limit,
                allowed_mime_types=payload.allowed_mime_types,
            )
    except service.StorageError as exc:
        raise _storage_error(exc) from exc


@router.get("/bucket", response_model=list[BucketResponse])
async def list_buckets(
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
) -> list[BucketResponse]:
    async with db.as_role(_claims_role(claims), claims) as conn:
        return await service.list_buckets(conn)


@router.get("/bucket/{name}", response_model=BucketResponse)
async def get_bucket(
    name: str,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
) -> BucketResponse:
    try:
        async with db.as_role(_claims_role(claims), claims) as conn:
            return await service.get_bucket(conn, name)
    except service.StorageError as exc:
        raise _storage_error(exc) from exc


@router.delete("/bucket/{name}", status_code=204)
async def delete_bucket(
    name: str,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
) -> None:
    backend = get_backend()
    try:
        async with db.as_role(_claims_role(claims), claims) as conn:
            await service.delete_bucket(conn, backend, name)
    except service.StorageError as exc:
        raise _storage_error(exc) from exc


# ---------------------------------------------------------------------------
# Signed URLs  (registered before generic /{bucket}/{path} to avoid shadowing)
# ---------------------------------------------------------------------------


@router.post(
    "/object/sign/{bucket}/{path:path}",
    response_model=SignedUrlResponse,
)
async def sign_object(
    bucket: str,
    path: str,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
    payload: SignedUrlRequest | None = None,
) -> SignedUrlResponse:
    expires_in = payload.expires_in if payload else None
    try:
        async with db.as_role(_claims_role(claims), claims) as conn:
            return await service.issue_signed_url(
                conn,
                bucket_name=bucket,
                path=path,
                expires_in=expires_in,
            )
    except service.StorageError as exc:
        raise _storage_error(exc) from exc


@router.get("/object/signed/{bucket}/{path:path}")
async def fetch_signed_object(
    bucket: str,
    path: str,
    token: Annotated[str, Query(description="HMAC token from /object/sign/...")],
    range_header: Annotated[str | None, Header(alias="range")] = None,
) -> StreamingResponse:
    byte_range = _parse_range(range_header)
    backend = get_backend()
    try:
        async with db.acquire() as conn:
            obj, stream = await service.verify_signed_download(
                conn,
                backend,
                bucket_name=bucket,
                path=path,
                token=token,
                byte_range=byte_range,
            )
    except service.StorageError as exc:
        raise _storage_error(exc) from exc
    return _stream_response(stream, filename=obj.name.rsplit("/", 1)[-1])


# ---------------------------------------------------------------------------
# Public buckets  (registered before generic /{bucket}/{path} to avoid shadowing)
# ---------------------------------------------------------------------------


@router.get("/object/public/{bucket}/{path:path}")
async def fetch_public_object(
    bucket: str,
    path: str,
    range_header: Annotated[str | None, Header(alias="range")] = None,
) -> StreamingResponse:
    byte_range = _parse_range(range_header)
    backend = get_backend()
    try:
        async with db.as_role("anon", {"role": "anon"}) as conn:
            obj, stream = await service.download_public_object(
                conn,
                backend,
                bucket_name=bucket,
                path=path,
                byte_range=byte_range,
            )
    except service.StorageError as exc:
        raise _storage_error(exc) from exc
    return _stream_response(stream, filename=obj.name.rsplit("/", 1)[-1])


# ---------------------------------------------------------------------------
# Object endpoints  (generic wildcard routes registered last)
# ---------------------------------------------------------------------------


@router.post(
    "/object/{bucket}/{path:path}",
    response_model=ObjectResponse,
    status_code=201,
)
async def upload_object(
    bucket: str,
    path: str,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
    file: Annotated[UploadFile, File(description="The file to upload")],
) -> ObjectResponse:
    backend = get_backend()
    content_type = file.content_type
    try:
        async with db.as_role(_claims_role(claims), claims) as conn:
            return await service.upload_object(
                conn,
                backend,
                bucket_name=bucket,
                path=path,
                data=_file_iterator(file),
                content_type=content_type,
            )
    except service.StorageError as exc:
        raise _storage_error(exc) from exc


@router.get("/object/{bucket}/{path:path}")
async def download_object(
    bucket: str,
    path: str,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
    range_header: Annotated[str | None, Header(alias="range")] = None,
) -> StreamingResponse:
    byte_range = _parse_range(range_header)
    backend = get_backend()
    try:
        async with db.as_role(_claims_role(claims), claims) as conn:
            obj, stream = await service.download_object(
                conn,
                backend,
                bucket_name=bucket,
                path=path,
                byte_range=byte_range,
            )
    except service.StorageError as exc:
        raise _storage_error(exc) from exc
    return _stream_response(stream, filename=obj.name.rsplit("/", 1)[-1])


@router.delete("/object/{bucket}/{path:path}", status_code=204)
async def delete_object(
    bucket: str,
    path: str,
    claims: Annotated[dict[str, Any], Depends(_current_claims)],
) -> None:
    backend = get_backend()
    try:
        async with db.as_role(_claims_role(claims), claims) as conn:
            await service.delete_object(
                conn,
                backend,
                bucket_name=bucket,
                path=path,
            )
    except service.StorageError as exc:
        raise _storage_error(exc) from exc
