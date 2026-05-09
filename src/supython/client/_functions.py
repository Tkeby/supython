from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ._auth import SupythonResponse
from ._config import _parse_error_detail


@dataclass
class FunctionsError:
    code: str
    message: str
    status: int


def _make_functions_error(resp: httpx.Response) -> FunctionsError:
    try:
        body = resp.json()
    except Exception:
        return FunctionsError(
            "network_error", resp.text or f"HTTP {resp.status_code}", resp.status_code
        )
    code, message = _parse_error_detail(body)
    return FunctionsError(code, message, resp.status_code)


class FunctionsClient:
    def __init__(self, base_url: str, anon_key: str, client: Any) -> None:
        self._url = base_url
        self._anon_key = anon_key
        self._client = client
        self._http = httpx.AsyncClient()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._anon_key:
            headers["apikey"] = self._anon_key
        access_token = self._client._access_token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    async def invoke(
        self,
        name: str,
        *,
        body: dict[str, Any] | None = None,
        method: str = "POST",
    ) -> SupythonResponse[Any]:
        url = f"{self._url}/{name}"
        try:
            resp = await self._http.request(
                method, url, json=body, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=FunctionsError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_functions_error(resp))

        try:
            data = resp.json()
        except Exception:
            data = resp.text

        return SupythonResponse(data=data)
