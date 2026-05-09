"""Authenticated function that counts todos via ctx.db (exercises RLS)."""


async def handler(req, ctx):
    count = await ctx.db.fetchval("select count(*) from public.todos")
    return {"count": int(count)}
