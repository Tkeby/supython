"""Public function reachable via GET and POST."""

auth = "anon"
methods = ["GET", "POST"]


async def handler(req, ctx):
    name = ctx.user.email if ctx.user else "world"
    return {"msg": f"hello, {name}"}
