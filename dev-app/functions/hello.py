"""Anon-readable greeter used by the TS SDK e2e suite."""

auth = "anon"
methods = ["GET", "POST"]


async def handler(req, ctx):
    payload = await req.json() if req.method == "POST" else {}
    name = payload.get("name") or (ctx.user.email if ctx.user else "world")
    return {"msg": f"hello, {name}"}
