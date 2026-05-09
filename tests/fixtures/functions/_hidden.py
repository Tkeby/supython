"""Underscore-prefixed — must be ignored by the loader entirely."""


async def handler(req, ctx):
    return {"msg": "you should never see this"}
