import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _hsts_effective(settings: Settings) -> bool:
    # Explicit override wins; otherwise auto-on for https site_url, off for http.
    if settings.security_hsts_enabled is not None:
        return settings.security_hsts_enabled
    return settings.site_url.lower().startswith("https://")


def _build_always_headers(settings: Settings) -> list[tuple[bytes, bytes]]:
    headers: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", settings.security_frame_options.encode("ascii")),
        (b"referrer-policy", settings.security_referrer_policy.encode("ascii")),
    ]
    if _hsts_effective(settings):
        parts = [f"max-age={settings.security_hsts_max_age}"]
        if settings.security_hsts_include_subdomains:
            parts.append("includeSubDomains")
        if settings.security_hsts_preload:
            parts.append("preload")
        headers.append(
            (b"strict-transport-security", "; ".join(parts).encode("ascii"))
        )
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app: Any, settings: Settings | None = None) -> None:
        self.app = app
        self._settings = settings or get_settings()
        self._always = _build_always_headers(self._settings)
        self._csp = (
            self._settings.security_csp.encode("ascii")
            if self._settings.security_csp
            else b""
        )
        self._csp_exempt = tuple(
            p.strip()
            for p in self._settings.security_csp_exempt_paths.split(",")
            if p.strip()
        )

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http" or not self._settings.security_headers_enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        apply_csp = bool(self._csp) and not any(
            path == p or path.startswith(p + "/") for p in self._csp_exempt
        )

        async def _send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                existing: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {name.lower() for name, _ in existing}
                for name, value in self._always:
                    if name not in present:
                        existing.append((name, value))
                if apply_csp and b"content-security-policy" not in present:
                    existing.append((b"content-security-policy", self._csp))
                message["headers"] = existing
            await send(message)

        await self.app(scope, receive, _send)
