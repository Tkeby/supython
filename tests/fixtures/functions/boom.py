"""Handler that raises a deliberate exception to exercise the 500 path."""

auth = "anon"
methods = ["POST"]


async def handler(req, ctx):
    raise RuntimeError("kaboom")
