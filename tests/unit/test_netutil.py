"""Tests for supython.netutil.resolve_client_ip — pure Python, no ASGI."""

from supython.netutil import resolve_client_ip


def test_no_trusted_proxies_ignores_header():
    assert (
        resolve_client_ip("192.0.2.1", "203.0.113.5", "") == "192.0.2.1"
    )


def test_untrusted_peer_ignores_header():
    assert (
        resolve_client_ip("192.0.2.1", "203.0.113.5", "10.0.0.0/8") == "192.0.2.1"
    )


def test_trusted_peer_uses_rightmost_untrusted_hop():
    assert (
        resolve_client_ip("10.0.0.2", "203.0.113.5", "10.0.0.0/8") == "203.0.113.5"
    )


def test_walks_past_trusted_chain():
    # client → proxy A (10.0.0.3) → proxy B (10.0.0.2) → app
    xff = "203.0.113.5, 10.0.0.3"
    assert resolve_client_ip("10.0.0.2", xff, "10.0.0.0/8") == "203.0.113.5"


def test_spoofed_left_entries_never_reached():
    # The client sent its own forged XFF; the proxy appended the real IP.
    xff = "1.2.3.4, 203.0.113.5"
    assert resolve_client_ip("10.0.0.2", xff, "10.0.0.0/8") == "203.0.113.5"


def test_malformed_hop_falls_back_to_peer():
    assert resolve_client_ip("10.0.0.2", "evil-garbage", "10.0.0.0/8") == "10.0.0.2"


def test_all_hops_trusted_returns_leftmost():
    assert resolve_client_ip("10.0.0.2", "10.0.0.9, 10.0.0.3", "10.0.0.0/8") == "10.0.0.9"


def test_missing_header_returns_peer():
    assert resolve_client_ip("10.0.0.2", None, "10.0.0.0/8") == "10.0.0.2"


def test_none_peer_returns_none():
    assert resolve_client_ip(None, "203.0.113.5", "10.0.0.0/8") is None


def test_cidr_list_and_plain_ip_entries():
    trusted = "127.0.0.1, 10.0.0.0/8"
    assert resolve_client_ip("127.0.0.1", "203.0.113.5", trusted) == "203.0.113.5"


def test_invalid_trusted_entry_is_ignored():
    assert resolve_client_ip("192.0.2.1", "203.0.113.5", "nonsense,,") == "192.0.2.1"


def test_ipv6_support():
    assert (
        resolve_client_ip("::1", "2001:db8::5", "::1/128") == "2001:db8::5"
    )
