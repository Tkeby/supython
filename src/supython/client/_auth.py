from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import httpx

from ._config import _parse_error_detail

T = TypeVar("T")


@dataclass
class AuthError:
    code: str
    message: str
    status: int


@dataclass
class UserResponse:
    id: str
    email: str
    created_at: str


@dataclass
class TokenResponse:
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    user: UserResponse


@dataclass
class SignUpResponse:
    """Result of sign_up.

    ``session`` is None when the server requires email confirmation
    (HTTP 202): the account exists but no tokens are issued until
    ``verify_signup`` (or the emailed link) completes.
    """

    user: UserResponse
    session: TokenResponse | None = None
    confirmation_sent_at: str | None = None


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserResponse | None


@dataclass
class SupythonResponse(Generic[T]):
    data: T | None = None
    error: AuthError | None = None


SIGNED_IN = "SIGNED_IN"
SIGNED_OUT = "SIGNED_OUT"
TOKEN_REFRESHED = "TOKEN_REFRESHED"
USER_UPDATED = "USER_UPDATED"


AuthChangeCallback = Callable[[str, Session | None], None]


def _parse_token_response(body: dict[str, Any]) -> TokenResponse:
    user_body = body["user"]
    user = UserResponse(
        id=str(user_body["id"]),
        email=user_body["email"],
        created_at=user_body["created_at"],
    )
    return TokenResponse(
        access_token=body["access_token"],
        token_type=body.get("token_type", "bearer"),
        expires_in=body["expires_in"],
        refresh_token=body["refresh_token"],
        user=user,
    )


def _parse_user_response(body: dict[str, Any]) -> UserResponse:
    return UserResponse(
        id=str(body["id"]),
        email=body["email"],
        created_at=body["created_at"],
    )


def _make_auth_error(resp: httpx.Response) -> AuthError:
    try:
        body = resp.json()
    except Exception:
        return AuthError("network_error", resp.text or f"HTTP {resp.status_code}", resp.status_code)
    code, message = _parse_error_detail(body)
    return AuthError(code, message, resp.status_code)


class AuthClient:
    def __init__(self, client: Any, base_url: str) -> None:
        self._client = client
        self._url = base_url
        self._http = httpx.AsyncClient()
        self._callbacks: list[AuthChangeCallback] = []

    def on_auth_state_change(self, callback: AuthChangeCallback) -> Callable[[], None]:
        self._callbacks.append(callback)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._callbacks.remove(callback)

        return unsubscribe

    def _emit(self, event: str, session: Session | None) -> None:
        for cb in self._callbacks:
            with contextlib.suppress(Exception):
                cb(event, session)

    async def sign_up(self, email: str, password: str) -> SupythonResponse[SignUpResponse]:
        try:
            resp = await self._http.post(
                f"{self._url}/signup",
                json={"email": email, "password": password},
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=AuthError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_auth_error(resp))

        body = resp.json()
        if resp.status_code == 202:
            # Email confirmation required: account created, no session yet.
            return SupythonResponse(
                data=SignUpResponse(
                    user=_parse_user_response(body["user"]),
                    session=None,
                    confirmation_sent_at=body.get("confirmation_sent_at"),
                )
            )

        token_resp = _parse_token_response(body)
        session = await self._save_session(token_resp)
        self._emit(SIGNED_IN, session)
        return SupythonResponse(
            data=SignUpResponse(user=token_resp.user, session=token_resp)
        )

    async def verify_signup(self, token: str) -> SupythonResponse[TokenResponse]:
        """Redeem an emailed signup-confirmation token for the first session."""
        try:
            resp = await self._http.get(
                f"{self._url}/confirm/verify", params={"token": token}
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=AuthError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_auth_error(resp))

        token_resp = _parse_token_response(resp.json())
        session = await self._save_session(token_resp)
        self._emit(SIGNED_IN, session)
        return SupythonResponse(data=token_resp)

    async def resend_confirmation(self, email: str) -> SupythonResponse[None]:
        try:
            resp = await self._http.post(
                f"{self._url}/confirm/resend", json={"email": email}
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=AuthError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_auth_error(resp))
        return SupythonResponse(data=None)

    async def sign_in_with_password(
        self, email: str, password: str
    ) -> SupythonResponse[TokenResponse]:
        try:
            resp = await self._http.post(
                f"{self._url}/token",
                json={"email": email, "password": password},
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=AuthError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_auth_error(resp))

        token_resp = _parse_token_response(resp.json())
        session = await self._save_session(token_resp)
        self._emit(SIGNED_IN, session)
        return SupythonResponse(data=token_resp)

    async def sign_out(self, scope: str = "local") -> SupythonResponse[None]:
        """Sign out. scope: "local" (this session), "global" (all sessions),
        or "others" (all sessions except this one)."""
        refresh_token = self._client._refresh_token
        access_token = self._client._access_token
        if not refresh_token and not access_token:
            return SupythonResponse(data=None)

        body: dict[str, Any] = {"scope": scope}
        if refresh_token:
            body["refresh_token"] = refresh_token
        headers = (
            {"Authorization": f"Bearer {access_token}"} if access_token else {}
        )
        try:
            resp = await self._http.post(
                f"{self._url}/logout", json=body, headers=headers
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=AuthError("network_error", str(exc), 0))

        if scope != "others":
            await self._clear_session()
            self._emit(SIGNED_OUT, None)

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_auth_error(resp))

        return SupythonResponse(data=None)

    async def update_password(
        self, new_password: str, current_password: str | None = None
    ) -> SupythonResponse[TokenResponse]:
        """Change the signed-in user's password.

        The server revokes every session and returns a fresh token pair,
        which replaces the local session.
        """
        access_token = self._client._access_token
        if not access_token:
            return SupythonResponse(error=AuthError("no_session", "Not authenticated", 401))

        body: dict[str, Any] = {"password": new_password}
        if current_password is not None:
            body["current_password"] = current_password
        try:
            resp = await self._http.put(
                f"{self._url}/user",
                json=body,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=AuthError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_auth_error(resp))

        token_resp = _parse_token_response(resp.json())
        session = await self._save_session(token_resp)
        self._emit(USER_UPDATED, session)
        return SupythonResponse(data=token_resp)

    async def refresh_session(self) -> SupythonResponse[TokenResponse]:
        refresh_token = self._client._refresh_token
        if not refresh_token:
            err = AuthError("no_session", "No refresh token available", 401)
            await self._clear_session()
            self._emit(SIGNED_OUT, None)
            return SupythonResponse(error=err)

        try:
            resp = await self._http.post(
                f"{self._url}/refresh",
                json={"refresh_token": refresh_token},
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=AuthError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            await self._clear_session()
            self._emit(SIGNED_OUT, None)
            return SupythonResponse(error=_make_auth_error(resp))

        token_resp = _parse_token_response(resp.json())
        session = await self._save_session(token_resp)
        self._emit(TOKEN_REFRESHED, session)
        return SupythonResponse(data=token_resp)

    async def get_user(self) -> SupythonResponse[UserResponse]:
        access_token = self._client._access_token
        if not access_token:
            return SupythonResponse(error=AuthError("no_session", "Not authenticated", 401))

        try:
            resp = await self._http.get(
                f"{self._url}/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            return SupythonResponse(error=AuthError("network_error", str(exc), 0))

        if resp.status_code >= 400:
            return SupythonResponse(error=_make_auth_error(resp))

        user = _parse_user_response(resp.json())
        previous = self._client._user
        self._client._user = user
        if previous is not None and previous != user:
            self._emit(USER_UPDATED, self.get_session())
        return SupythonResponse(data=user)

    def get_session(self) -> Session | None:
        access_token = self._client._access_token
        refresh_token = self._client._refresh_token
        if not access_token:
            return None
        return Session(
            access_token=access_token,
            refresh_token=refresh_token or "",
            expires_in=0,
            user=self._client._user,
        )

    async def _save_session(self, token_resp: TokenResponse) -> Session:
        self._client.set_session(
            token_resp.access_token,
            token_resp.refresh_token,
            user=token_resp.user,
        )
        await self._client._persist_session()
        return Session(
            access_token=token_resp.access_token,
            refresh_token=token_resp.refresh_token,
            expires_in=token_resp.expires_in,
            user=token_resp.user,
        )

    async def _clear_session(self) -> None:
        self._client.clear_session()
        await self._client._persist_session()
