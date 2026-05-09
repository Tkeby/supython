"""Tests for supython.admin.session — pure Python, no DB."""

import hashlib
from datetime import timedelta

from supython.admin import session


def test_hash_is_sha256():
    raw = "tok-abc"
    assert session._hash(raw) == hashlib.sha256(raw.encode("utf-8")).digest()


def test_hash_changes_with_input():
    assert session._hash("a") != session._hash("b")


def test_session_cookie_has_no_host_prefix():
    # __Host- requires Path=/, but the cookie is scoped to /admin.
    assert not session.SESSION_COOKIE.startswith("__Host-")


def test_session_path_scope():
    assert session.SESSION_PATH == "/admin"


def test_session_ttl_is_eight_hours():
    assert session.SESSION_TTL == timedelta(hours=8)
