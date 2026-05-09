from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


@runtime_checkable
class AuthStorageBackend(Protocol):
    async def load(self) -> dict[str, str] | None: ...
    async def save(self, data: dict[str, str]) -> None: ...
    async def clear(self) -> None: ...


class MemoryAuthStorage:
    def __init__(self) -> None:
        self._data: dict[str, str] | None = None

    async def load(self) -> dict[str, str] | None:
        return self._data

    async def save(self, data: dict[str, str]) -> None:
        self._data = dict(data)

    async def clear(self) -> None:
        self._data = None


class FileAuthStorage:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def load(self) -> dict[str, str] | None:
        if not self._path.exists():
            return None
        text = self._path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return json.loads(text)

    async def save(self, data: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data), encoding="utf-8")

    async def clear(self) -> None:
        if self._path.exists():
            self._path.write_text("", encoding="utf-8")


@dataclass
class AuthOptions:
    storage: AuthStorageBackend | None = None
    auto_refresh_token: bool = True
    persist_session: bool = True


@dataclass
class ClientOptions:
    auth: AuthOptions = field(default_factory=AuthOptions)


def _build_rest_url(base_url: str) -> str:
    return f"{base_url}/rest/v1"


def _build_auth_url(base_url: str) -> str:
    return f"{base_url}/auth/v1"


def _build_storage_url(base_url: str) -> str:
    return f"{base_url}/storage/v1"


def _build_functions_url(base_url: str) -> str:
    return f"{base_url}/functions"


def _build_ws_url(base_url: str) -> str:
    return base_url.replace("http://", "ws://").replace("https://", "wss://") + "/realtime/v1"


def _parse_error_detail(body: Any) -> tuple[str, str]:
    if isinstance(body, dict):
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            return detail.get("code", "unknown"), detail.get("message", str(body))
        return "unknown", str(detail)
    return "unknown", str(body)
