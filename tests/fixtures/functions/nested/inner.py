"""Nested function — registered as 'nested/inner'."""

auth = "anon"
methods = ["GET", "POST"]


async def handler(req, ctx):
    return {"route": "nested/inner"}
