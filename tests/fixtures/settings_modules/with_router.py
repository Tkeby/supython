"""Settings module fixture: declares an extra router."""

EXTENSIONS: list[str] = []
EXTRA_ROUTERS: list[str] = ["tests.fixtures.routers:router"]
EXTRA_MIDDLEWARE: list[str] = []
