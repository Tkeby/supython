"""Example edge function — served at /functions/hello (no restart needed).

Drop more ``.py`` files into ``functions/`` to add routes; each file's
``handler`` is the entrypoint. See ``functions/README.md`` for the full ``ctx``
reference.
"""
auth = "anon"  # "anon" (public) or "authenticated"
methods = ["GET", "POST"]


async def handler(req, ctx):
    who = ctx.user.email if ctx.user else "world"
    return {"msg": f"hello, {who}"}
