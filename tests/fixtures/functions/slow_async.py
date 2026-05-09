"""Sleeps far longer than any reasonable test timeout to exercise wait_for."""

import asyncio

auth = "anon"
methods = ["GET"]


async def handler(req, ctx):
    await asyncio.sleep(60)
    return {"never": "reached"}
