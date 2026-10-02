"""Fail-closed public-address validation for enrichment HTTP fetches.

Resolution returns the exact addresses used by the pinned transport. No second
DNS lookup, proxy, cookie jar or automatic redirect handler can bypass it.
"""
from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit


class BlockedURLError(Exception):
    """An outbound URL, peer or response violated the enrichment policy."""


@dataclass(frozen=True)
class ResolvedURL:
    url: str
    scheme: str
    host: str
    port: int
    authority: str
    target: str
    addresses: tuple


def _ip_is_blocked(ip) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return _ip_is_blocked(ip.ipv4_mapped)
        if ip.sixtofour is not None and _ip_is_blocked(ip.sixtofour):
            return True
        if ip.teredo is not None and any(_ip_is_blocked(v4) for v4 in ip.teredo):
            return True
    return not ip.is_global or ip.is_multicast


def resolve_public_url(url: str, *, deadline: float | None = None) -> ResolvedURL:
    """Parse and resolve once; reject the entire answer if any IP is non-public."""
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise BlockedURLError("invalid or oversized outbound URL")
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("HTTP(S) scheme and host required")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URL credentials are prohibited")
        host = parsed.hostname.encode("idna").decode("ascii")
        if "%" in host:
            raise ValueError("scoped or escaped host prohibited")
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        if not 1 <= port <= 65535:
            raise ValueError("port outside allowed range")
    except (ValueError, UnicodeError) as exc:
        raise BlockedURLError(f"invalid outbound URL authority: {exc}") from exc

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        family = socket.AF_INET6 if literal.version == 6 else socket.AF_INET
        infos = [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (host, port))]
    else:
        from src.api.outbound_dns import resolve_bounded
        try:
            infos = resolve_bounded(host, port, deadline=deadline if deadline is not None else time.monotonic() + 5)
        except (OSError, UnicodeError) as exc:
            raise BlockedURLError("outbound host resolution failed") from exc
    addresses = []
    for family, kind, proto, _, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise BlockedURLError("resolver returned an invalid address") from exc
        if family not in {socket.AF_INET, socket.AF_INET6} or _ip_is_blocked(ip):
            raise BlockedURLError("outbound host resolves to a non-public address")
        address = (family, str(ip))
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise BlockedURLError("outbound host resolved to no addresses")

    authority = f"[{host}]" if ":" in host else host
    if port != (443 if parsed.scheme == "https" else 80):
        authority += f":{port}"
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    return ResolvedURL(url, parsed.scheme, host, port, authority, target, tuple(addresses))


def validate_url(url: str) -> None:
    """Validate without fetching; transport callers use the returned resolution."""
    resolve_public_url(url)


def safe_urlopen(url: str, *, timeout: float = 10.0, headers: dict | None = None,
                 max_bytes: int = 1_048_576, max_wire_bytes: int | None = None):
    """Open a pinned GET with bounded redirects, elapsed time and response bytes.

    ``read()`` streams at most max_wire_bytes encoded payload bytes and
    max_bytes decoded bytes, including when callers read incrementally.
    The returned response is a context manager and must be closed by callers.
    """
    from src.api.outbound_transport import open_pinned
    return open_pinned(url, timeout=timeout, headers=headers or {},
                       max_bytes=max_bytes, max_wire_bytes=max_wire_bytes)
