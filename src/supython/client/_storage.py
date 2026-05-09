from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ._auth import SupythonResponse
from ._config import _parse_error_detail


@dataclass
class StorageError:
    code: str
    message: str
    status: int


@dataclass
class BucketResponse:
    id: str
    name: str
    owner: str | None
    public: bool
    file_size_limit: int | None
    allowed_mime_types: list[str] | None
    created_at: str
    updated_at: str


@dataclass
class ObjectResponse:
    id: str
    bucket_id: str
    bucket: str
    name: str
    owner: str
    size: int
    mime_type: str | None
    etag: str | None
    created_at: str
    updated_at: str


@dataclass
class SignedUrlResponse:
    signed_url: str
    token: str
    expires_at: str
    expires_in: int


def _make_storage_error(resp: httpx.Response) -> StorageError:
    try:
        body = resp.json()
    except Exception:
        msg = resp.text or f"HTTP {resp.status_code}"
        return StorageError("network_error", msg, resp.status_code)
    code, message = _parse_error_detail(body)
    return StorageError(code, message, resp.status_code)


def _parse_bucket(body: dict[str, Any]) -> BucketResponse:
    return BucketResponse(
        id=str(body["id"]),
        name=body["name"],
        owner=str(body["owner"]) if body.get("owner") else None,
        public=body["public"],
        file_size_limit=body.get("file_size_limit"),
        allowed_mime_types=body.get("allowed_mime_types"),
        created_at=body["created_at"],
        updated_at=body["updated_at"],
    )


def _parse_object(body: dict[str, Any]) -> ObjectResponse:
    return ObjectResponse(
        id=str(body["id"]),
        bucket_id=str(body["bucket_id"]),
        bucket=body["bucket"],
        name=body["name"],
        owner=str(body["owner"]),
        size=body["size"],
        mime_type=body.get("mime_type"),
        etag=body.get("etag"),
        created_at=body["created_at"],
        updated_at=body["updated_at"],
    )


class StorageBucket:
    def __init__(self, client: StorageClient, bucket_name: str) -> None:
        self._client = client
        self._bucket_name = bucket_name

    def _headers(self) -> dict[str, str]:
        return self._client._headers()

    async def upload(
        self,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> SupythonResponse[ObjectResponse]:
        url = f"{self._client._url}/object/{self._bucket_name}/{path}"
        files = {"file": (path, data, content_type or "application/octet-stream")}
        try:
            resp = await self._client._http.post(
                url, files=files, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=StorageError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_storage_error(resp))

        return SupythonResponse(data=_parse_object(resp.json()))

    async def download(self, path: str) -> SupythonResponse[bytes]:
        url = f"{self._client._url}/object/{self._bucket_name}/{path}"
        try:
            resp = await self._client._http.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            return SupythonResponse(error=StorageError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_storage_error(resp))

        return SupythonResponse(data=resp.content)

    async def remove(self, path: str) -> SupythonResponse[None]:
        url = f"{self._client._url}/object/{self._bucket_name}/{path}"
        try:
            resp = await self._client._http.delete(url, headers=self._headers())
        except httpx.HTTPError as exc:
            return SupythonResponse(error=StorageError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_storage_error(resp))

        return SupythonResponse(data=None)

    async def create_signed_url(
        self, path: str, *, expires_in: int | None = None
    ) -> SupythonResponse[SignedUrlResponse]:
        url = f"{self._client._url}/object/sign/{self._bucket_name}/{path}"
        body: dict[str, Any] = {}
        if expires_in is not None:
            body["expires_in"] = expires_in
        try:
            resp = await self._client._http.post(
                url, json=body or None, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=StorageError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_storage_error(resp))

        data = resp.json()
        return SupythonResponse(
            data=SignedUrlResponse(
                signed_url=data["signed_url"],
                token=data["token"],
                expires_at=data["expires_at"],
                expires_in=data["expires_in"],
            )
        )

    def get_public_url(self, path: str) -> str:
        return f"{self._client._url}/object/public/{self._bucket_name}/{path}"


class StorageClient:
    def __init__(self, base_url: str, anon_key: str, client: Any) -> None:
        self._url = base_url
        self._anon_key = anon_key
        self._client = client
        self._http = httpx.AsyncClient()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._anon_key:
            headers["apikey"] = self._anon_key
        access_token = self._client._access_token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def from_(self, bucket_name: str) -> StorageBucket:
        return StorageBucket(self, bucket_name)

    async def create_bucket(
        self,
        *,
        name: str,
        public: bool = False,
        file_size_limit: int | None = None,
        allowed_mime_types: list[str] | None = None,
    ) -> SupythonResponse[BucketResponse]:
        body: dict[str, Any] = {"name": name, "public": public}
        if file_size_limit is not None:
            body["file_size_limit"] = file_size_limit
        if allowed_mime_types is not None:
            body["allowed_mime_types"] = allowed_mime_types

        try:
            resp = await self._http.post(
                f"{self._url}/bucket", json=body, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=StorageError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_storage_error(resp))

        return SupythonResponse(data=_parse_bucket(resp.json()))

    async def list_buckets(self) -> SupythonResponse[list[BucketResponse]]:
        try:
            resp = await self._http.get(f"{self._url}/bucket", headers=self._headers())
        except httpx.HTTPError as exc:
            return SupythonResponse(error=StorageError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_storage_error(resp))

        return SupythonResponse(data=[_parse_bucket(b) for b in resp.json()])

    async def get_bucket(self, name: str) -> SupythonResponse[BucketResponse]:
        try:
            resp = await self._http.get(
                f"{self._url}/bucket/{name}", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=StorageError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_storage_error(resp))

        return SupythonResponse(data=_parse_bucket(resp.json()))

    async def delete_bucket(self, name: str) -> SupythonResponse[None]:
        try:
            resp = await self._http.delete(
                f"{self._url}/bucket/{name}", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=StorageError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_storage_error(resp))

        return SupythonResponse(data=None)
