"""Authenticated function that uploads a small payload via ctx.storage."""


async def handler(req, ctx):
    body = await req.body()

    async def _stream():
        yield body

    obj = await ctx.storage.upload(
        bucket="avatars",
        path=f"{ctx.user.id}/payload.bin",
        data=_stream(),
        content_type="application/octet-stream",
    )
    signed = await ctx.storage.sign(
        bucket="avatars",
        path=f"{ctx.user.id}/payload.bin",
        expires_in=3600,
    )
    return {"key": f"{obj.bucket}/{obj.name}", "signed_url": signed.signed_url}
