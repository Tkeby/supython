"""Intentionally broken fixture — missing the required handler.

The loader must skip this file (in hot-reload / dev mode) and log a warning
rather than raising. Tests assert that bad_handler never appears in the
registry and that valid neighbouring functions still load correctly.
"""

# No `async def handler(req, ctx)` defined here on purpose.
not_a_handler = "oops"
