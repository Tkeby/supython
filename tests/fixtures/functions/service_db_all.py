"""Authenticated function that uses ctx.service_db() to bypass RLS.

Counts every row in public.todos via a service_role connection — visible to
the caller regardless of which user actually owns the rows.
"""


async def handler(req, ctx):
    async with ctx.service_db() as conn:
        count = await conn.fetchval("select count(*) from public.todos")
        uid = await conn.fetchval("select auth.uid()")
    return {
        "count": int(count),
        "auth_uid": str(uid) if uid is not None else None,
    }
