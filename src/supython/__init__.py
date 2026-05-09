"""supython: a lightweight Postgres-first BaaS framework for Python."""

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

try:
    __version__ = version("supython")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"


if TYPE_CHECKING:
    from .app import create_app as build_app  # noqa: F401


def __getattr__(name: str):
    if name == "build_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module 'supython' has no attribute {name!r}")


__all__ = ["__version__", "build_app"]
