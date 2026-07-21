"""Client-IP resolution behind trusted reverse proxies.

Pure functions so the trust logic is unit-testable without an ASGI stack.
"""

import ipaddress
import logging

logger = logging.getLogger(__name__)


def _parse_trusted(trusted_csv: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks = []
    for entry in trusted_csv.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("netutil: ignoring invalid TRUSTED_PROXIES entry %r", entry)
    return networks


def _is_trusted(ip: str, networks: list) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def resolve_client_ip(
    peer: str | None,
    forwarded_for: str | None,
    trusted_proxies_csv: str,
) -> str | None:
    """Return the effective client IP for rate limiting and audit logging.

    Trust model: ``X-Forwarded-For`` is only consulted when the TCP ``peer``
    is in ``trusted_proxies_csv`` (IPs/CIDRs). The chain is walked from the
    right — each trusted proxy appends the address it saw — and the first
    address NOT in the trusted set is the real client. Anything the client
    itself put into the header sits further left and is never reached, so
    spoofing cannot move the rate-limit bucket. Malformed entries fall back
    to the peer address (fail closed onto what the kernel saw).
    """
    if peer is None:
        return None
    networks = _parse_trusted(trusted_proxies_csv)
    if not networks or not _is_trusted(peer, networks) or not forwarded_for:
        return peer
    hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
    for hop in reversed(hops):
        try:
            ipaddress.ip_address(hop)
        except ValueError:
            logger.warning("netutil: malformed X-Forwarded-For hop %r; using peer", hop)
            return peer
        if not _is_trusted(hop, networks):
            return hop
    # Every hop was a trusted proxy — the leftmost one is the closest thing
    # to a client we have.
    return hops[0] if hops else peer
