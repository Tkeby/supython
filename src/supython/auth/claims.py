"""Custom-claim providers for access-token issuance.

Library users register an async callable via ``claims.register`` (typically
imported as ``from supython.auth.claims import register as claims_provider``)
and the auth service invokes it inside ``_issue_pair`` just before minting
the JWT. Each provider returns a ``dict`` that is merged into the access
token's payload.

Contract (intentionally narrower than ``hooks.fire``):

- Providers run on the **service-role** connection used by the auth flow,
  so they can read tables that RLS would block during issuance (e.g. a
  ``user_roles`` lookup keyed by a brand-new user). Treat the function as
  privileged — same posture as a Postgres ``security definer`` routine.
- A provider raising propagates: a missing claim is a silent authz bug,
  not a missing welcome email. ``hooks.fire`` swallows on purpose;
  ``collect`` does not.
- Reserved JWT claims (``sub``, ``email``, ``role``, ``aud``, ``iat``,
  ``exp``, ``jti``) cannot be overridden — they are filtered out of every
  provider's return value so a misbehaving provider can't mint a token
  that contradicts its own header or expiry.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg

from .schemas import UserResponse

logger = logging.getLogger(__name__)

ClaimsProvider = Callable[[UserResponse, asyncpg.Connection], Awaitable[dict[str, Any]]]

_RESERVED: frozenset[str] = frozenset(
    {"sub", "email", "role", "aud", "iat", "exp", "jti"}
)

_providers: list[ClaimsProvider] = []


def register(fn: ClaimsProvider) -> ClaimsProvider:
    """Register *fn* as a claims provider. Usable as a decorator."""
    _providers.append(fn)
    return fn


async def collect(user: UserResponse, conn: asyncpg.Connection) -> dict[str, Any]:
    """Run every registered provider and return the merged claim dict.

    Providers run in registration order; later providers win on key
    collisions. Reserved JWT claims are stripped from each return value
    before merging.
    """
    merged: dict[str, Any] = {}
    for fn in _providers:
        out = await fn(user, conn)
        if not out:
            continue
        for key in _RESERVED.intersection(out):
            logger.warning(
                "claims provider %r returned reserved claim %r; dropping",
                getattr(fn, "__qualname__", fn),
                key,
            )
        merged.update({k: v for k, v in out.items() if k not in _RESERVED})
    return merged


def reset() -> None:
    """Clear all registered providers. Test-only."""
    _providers.clear()
