"""Authenticated function that sends an email via ctx.send_email."""


async def handler(req, ctx):
    body = await req.json()
    await ctx.send_email(
        to=body.get("to", ctx.user.email),
        subject=body.get("subject", "Notification"),
        text=body.get("text", ""),
    )
    return {"sent": True}
