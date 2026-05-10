"""Public FastAPI dependencies for downstream apps.

These are the supported way for application code to read the authenticated
caller out of an incoming request — equivalent to the auth router's private
``_current_user_id`` but stable, re-exported, and documented.

Usage::

    from typing import Annotated
    from uuid import UUID

    from fastapi import Depends
    from supython.auth import current_user_id, current_claims

    @router.get("/me")
    async def me(user_id: Annotated[UUID, Depends(current_user_id)]):
        ...

    @router.get("/whoami")
    async def whoami(claims: Annotated[dict, Depends(current_claims)]):
        return {"org_id": claims.get("org_id")}
"""

from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status

from .. import tokens


async def current_claims(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return the decoded JWT claims of the bearer token, or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        return tokens.decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}"
        ) from exc


async def current_user_id(
    claims: Annotated[dict[str, Any], Depends(current_claims)],
) -> UUID:
    """Return the authenticated user's UUID from the bearer token, or 401."""
    try:
        return UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token missing valid sub claim"
        ) from exc
