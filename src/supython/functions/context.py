"""Per-request context object passed to every user function.

This is the *one* module in supython that is allowed to import across feature
packages: it composes ``storage``, ``mailer``, and ``postgrest`` into the
``Ctx`` value that handlers receive. Functions are the edge layer — they
exist precisely so user code can stitch sibling subsystems together — so the
loader/dispatcher pair is the deliberate exception to the no-cross-import
rule that applies elsewhere.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

import asyncpg
import httpx

from .. import db as _db
from ..mailer import EmailBackend, EmailMessage, get_mailer
from ..settings import Settings, get_settings
from ..storage import service as storage_service
from ..storage.backends import StorageBackend, get_backend
from ..storage.schemas import ObjectResponse, SignedUrlResponse

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import Request


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


@dataclass
class FunctionUser:
    """Caller identity decoded from the bearer token, or ``None`` for anon."""

    id: UUID | None
    email: str | None
    role: str
    claims: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> FunctionUser:
        sub = claims.get("sub")
        try:
            uid = UUID(sub) if isinstance(sub, str) else None
        except ValueError:
            uid = None
        email = claims.get("email")
        role = claims.get("role") or "anon"
        return cls(
            id=uid,
            email=email if isinstance(email, str) else None,
            role=role if isinstance(role, str) else "anon",
            claims=claims,
        )


# ---------------------------------------------------------------------------
# Storage facade
# ---------------------------------------------------------------------------


class StorageClient:
    """Short-call-site wrapper around ``storage.service`` bound to ``ctx.db``.

    All authorization still flows through the role-scoped connection — the
    wrapper exists purely so handlers can write
    ``await ctx.storage.upload(...)`` instead of threading ``conn`` and
    ``backend`` by hand.
    """

    def __init__(self, conn: asyncpg.Connection, backend: StorageBackend) -> None:
        self._conn = conn
        self._backend = backend

    async def upload(
        self,
        *,
        bucket: str,
        path: str,
        data: AsyncIterator[bytes],
        content_type: str | None = None,
    ) -> ObjectResponse:
        return await storage_service.upload_object(
            self._conn,
            self._backend,
            bucket_name=bucket,
            path=path,
            data=data,
            content_type=content_type,
        )

    async def download(
        self,
        *,
        bucket: str,
        path: str,
        byte_range: tuple[int, int | None] | None = None,
    ):
        return await storage_service.download_object(
            self._conn,
            self._backend,
            bucket_name=bucket,
            path=path,
            byte_range=byte_range,
        )

    async def delete(self, *, bucket: str, path: str) -> None:
        await storage_service.delete_object(
            self._conn,
            self._backend,
            bucket_name=bucket,
            path=path,
        )

    async def get_metadata(self, *, bucket: str, path: str) -> ObjectResponse:
        return await storage_service.get_object_metadata(self._conn, bucket, path)

    async def sign(
        self, *, bucket: str, path: str, expires_in: int | None = None
    ) -> SignedUrlResponse:
        return await storage_service.issue_signed_url(
            self._conn,
            bucket_name=bucket,
            path=path,
            expires_in=expires_in,
        )


# ---------------------------------------------------------------------------
# PostgREST forwarding client
# ---------------------------------------------------------------------------


class PostgrestClient:
    """Request-scoped ``httpx.AsyncClient`` aimed at the configured PostgREST.

    When the caller is authenticated, the bearer token is forwarded so the
    upstream RLS verdict matches whatever ``ctx.db`` would see. For anon
    callers no ``Authorization`` header is sent, which lets PostgREST resolve
    the request to its ``anon`` role.

    The dispatcher constructs one of these per request and ``aclose()``s it
    in a ``finally`` block; user code should treat it like a borrowed handle.
    """

    def __init__(self, base_url: str, jwt: str | None) -> None:
        headers: dict[str, str] = {}
        if jwt:
            headers["Authorization"] = f"Bearer {jwt}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
        )

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return await self._client.get(url, **kw)

    async def post(self, url: str, **kw: Any) -> httpx.Response:
        return await self._client.post(url, **kw)

    async def patch(self, url: str, **kw: Any) -> httpx.Response:
        return await self._client.patch(url, **kw)

    async def put(self, url: str, **kw: Any) -> httpx.Response:
        return await self._client.put(url, **kw)

    async def delete(self, url: str, **kw: Any) -> httpx.Response:
        return await self._client.delete(url, **kw)

    async def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        return await self._client.request(method, url, **kw)

    async def aclose(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# send_email kwargs wrapper
# ---------------------------------------------------------------------------


def _make_send_email(
    backend: EmailBackend,
) -> Callable[..., Awaitable[None]]:
    """Adapt ``backend.send(EmailMessage)`` to the kwargs form handlers want.

    ``await ctx.send_email(to="x@y", subject="Hi", text="...", html=None)``
    is the documented surface; ``to`` may be a single address or a list.
    """

    async def send_email(
        *,
        to: str | list[str],
        subject: str,
        text: str,
        html: str | None = None,
    ) -> None:
        recipients = [to] if isinstance(to, str) else list(to)
        msg = EmailMessage(to=recipients, subject=subject, text=text, html=html)
        await backend.send(msg)

    return send_email


# ---------------------------------------------------------------------------
# Ctx
# ---------------------------------------------------------------------------


@dataclass
class Ctx:
    """The ``ctx`` argument every user handler receives.

    Lifetime: one HTTP request. ``db`` is a live, role-scoped connection
    already inside ``db.as_role(...)`` — handlers can call
    ``await ctx.db.fetchrow(...)`` directly. ``postgrest`` is closed by the
    dispatcher in ``finally``; everything else is plain references.
    """

    db: asyncpg.Connection
    user: FunctionUser | None
    storage: StorageClient
    postgrest: PostgrestClient
    send_email: Callable[..., Awaitable[None]]
    request: Request
    settings: Settings

    def service_db(
        self,
        *,
        with_user_claims: bool = True,
    ) -> AbstractAsyncContextManager[asyncpg.Connection]:
        """Yield a ``service_role`` connection for housekeeping inside a handler.

        Convenience wrapper around :func:`supython.db.as_service_role` so user
        code can write::

            async with ctx.service_db() as conn:
                await conn.execute("insert into audit.events ...")

        instead of importing ``supython.db``. ``service_role`` bypasses RLS;
        when the caller is authenticated the user's JWT claims are forwarded
        to the session so helpers like ``auth.uid()`` still return the
        caller's id inside the block. Pass ``with_user_claims=False`` to
        suppress that and run truly impersonal admin work.
        """
        claims = (
            self.user.claims if (with_user_claims and self.user is not None) else None
        )
        return _db.as_service_role(claims=claims)


def build_ctx(
    *,
    conn: asyncpg.Connection,
    user: FunctionUser | None,
    request: Request,
    raw_jwt: str | None,
    backend: StorageBackend | None = None,
    mailer: EmailBackend | None = None,
    settings: Settings | None = None,
) -> Ctx:
    """Assemble a ``Ctx`` for one request.

    Kept as a free function so tests can construct a ``Ctx`` directly with
    fakes for ``backend`` / ``mailer`` without going through the dispatcher.
    """
    s = settings or get_settings()
    return Ctx(
        db=conn,
        user=user,
        storage=StorageClient(conn, backend or get_backend()),
        postgrest=PostgrestClient(s.postgrest_url, raw_jwt),
        send_email=_make_send_email(mailer or get_mailer()),
        request=request,
        settings=s,
    )
