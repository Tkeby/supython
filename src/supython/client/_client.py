from __future__ import annotations

from typing import Any

from ._auth import SIGNED_IN, AuthClient, UserResponse
from ._config import (
    ClientOptions,
    MemoryAuthStorage,
    _build_auth_url,
    _build_functions_url,
    _build_rest_url,
    _build_storage_url,
    _build_ws_url,
)
from ._functions import FunctionsClient
from ._storage import StorageClient


class Client:
    def __init__(
        self,
        supython_url: str,
        anon_key: str = "",
        *,
        options: ClientOptions | None = None,
    ) -> None:
        self.base_url = supython_url.rstrip("/")
        self._anon_key = anon_key
        self._opts = options or ClientOptions()
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._user: UserResponse | None = None

        if self._opts.auth.storage is None:
            self._storage_backend = MemoryAuthStorage()
        else:
            self._storage_backend = self._opts.auth.storage

        self.auth = AuthClient(self, _build_auth_url(self.base_url))
        self.storage = StorageClient(_build_storage_url(self.base_url), self._anon_key, self)
        self.functions = FunctionsClient(
            _build_functions_url(self.base_url), self._anon_key, self
        )

        self._rest_url = _build_rest_url(self.base_url)
        self._ws_url = _build_ws_url(self.base_url)

    def set_session(
        self,
        access_token: str,
        refresh_token: str,
        *,
        user: UserResponse | None = None,
    ) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        if user is not None:
            self._user = user

    def clear_session(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self._user = None

    async def _persist_session(self) -> None:
        if not self._opts.auth.persist_session:
            return
        # Persistence is best-effort: the in-memory session is the source of
        # truth and a failed write should not break the auth response contract.
        try:
            if self._access_token and self._refresh_token:
                await self._storage_backend.save(
                    {
                        "access_token": self._access_token,
                        "refresh_token": self._refresh_token,
                    }
                )
            else:
                await self._storage_backend.clear()
        except Exception:
            pass

    async def restore_session(self) -> bool:
        try:
            data = await self._storage_backend.load()
        except Exception:
            return False
        if not data:
            return False
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not access_token:
            return False
        self.set_session(access_token, refresh_token or "")
        self.auth._emit(SIGNED_IN, self.auth.get_session())
        return True

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._anon_key:
            headers["apikey"] = self._anon_key
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def from_(self, table: str) -> Any:
        try:
            from postgrest import PostgrestClient
        except ImportError as exc:
            raise ImportError(
                "PostgREST query builder requires postgrest-py. "
                "Install with: pip install supython[client]"
            ) from exc
        return PostgrestClient(
            self._rest_url, headers=self._auth_headers()
        ).from_(table)

    def rpc(self, fn_name: str, params: dict | None = None) -> Any:
        try:
            from postgrest import PostgrestClient
        except ImportError as exc:
            raise ImportError(
                "PostgREST query builder requires postgrest-py. "
                "Install with: pip install supython[client]"
            ) from exc
        return PostgrestClient(
            self._rest_url, headers=self._auth_headers()
        ).rpc(fn_name, params or {})

    def channel(self, topic: str) -> Any:
        try:
            from realtime import RealtimeClient
        except ImportError as exc:
            raise ImportError(
                "Realtime client requires the realtime package. "
                "Install with: pip install supython[client]"
            ) from exc
        client = RealtimeClient(self._ws_url, params={"apikey": self._anon_key})
        return client.channel(topic)

    async def _auto_refresh(self) -> bool:
        if not self._opts.auth.auto_refresh_token:
            return False
        result = await self.auth.refresh_session()
        return result.error is None
