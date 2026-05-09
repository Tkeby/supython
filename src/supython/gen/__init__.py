"""Code generation for `supython gen`."""
from .types_py import render_types_py
from .types_ts import render_types_ts

__all__ = ["render_types_py", "render_types_ts"]
