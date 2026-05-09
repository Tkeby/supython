"""Authenticated function that echoes back the caller's identity."""


async def handler(req, ctx):
    u = ctx.user
    return {
        "id": str(u.id) if u and u.id else None,
        "email": u.email if u else None,
        "role": u.role if u else None,
    }
