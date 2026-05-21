"""SSRF guard for outbound URL fetches.

Used by the tweet-enrichment pipeline (``src/api/tweet_enrichment.py``), which
resolves and fetches ``t.co`` links extracted from tweet text. The destination
of a ``t.co`` link is fully attacker-controlled — anyone can register a short
link that redirects anywhere — so every fetch in that pipeline must be checked
before the request leaves the machine, or it becomes an SSRF primitive
(``POST /interpret`` -> enrichment -> fetch of an internal address).

What this guards: fetches whose URL derives from untrusted input.
What this does NOT guard: fetches to trusted, operator-configured endpoints
(Supabase archive storage, twitterapi.io) — those have a fixed host and need
no check.

Known residual — DNS rebinding: ``validate_url`` resolves the hostname and
checks the IPs, but the connection that follows re-resolves independently, so
a hostile resolver could return a public IP to the check and a private IP to
the fetch. Fully closing this needs IP-pinned connections with a manual Host
header. Accepted for now — the API server is local-only (see docs/HANDOVER.md);
revisit before any public deploy.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.request
from typing import Union
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}

# Tailscale / CGNAT shared address space (RFC 6598). Python's
# ``ipaddress.is_private`` classifies this range inconsistently across CPython
# versions, so block it explicitly to keep behaviour identical between the
# local anaconda env and CI.
_EXTRA_BLOCKED_V4 = (ipaddress.ip_network("100.64.0.0/10"),)

_IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


class BlockedURLError(Exception):
    """Raised when a URL uses a disallowed scheme or targets a non-public address."""


def _ip_is_blocked(ip: _IPAddress) -> bool:
    """True if `ip` is anything other than a public, globally-routable address."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    # IPv4-mapped IPv6 (e.g. ::ffff:10.0.0.1) — unwrap and re-check the v4 part.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _ip_is_blocked(ip.ipv4_mapped)
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in _EXTRA_BLOCKED_V4)
    return False


def validate_url(url: str) -> None:
    """Raise BlockedURLError unless `url` is an http(s) URL that resolves
    entirely to public, routable IP addresses.

    Fail-closed: any parsing, resolution, or port error blocks the URL.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise BlockedURLError(f"scheme not allowed: {parsed.scheme!r}")

    host = parsed.hostname
    if not host:
        raise BlockedURLError(f"no host in URL: {url!r}")

    # A bare IP literal in the URL skips DNS — check it directly.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_is_blocked(literal):
            raise BlockedURLError(f"non-public address: {host}")
        return

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise BlockedURLError(f"invalid port in URL: {url!r}") from exc

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedURLError(f"could not resolve host {host!r}: {exc}") from exc

    if not infos:
        raise BlockedURLError(f"host {host!r} resolved to no addresses")

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _ip_is_blocked(ip):
            raise BlockedURLError(
                f"host {host!r} resolves to non-public address {ip}"
            )


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates the target of every redirect hop, so a public URL cannot
    302 into a private one."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_urlopen(
    url: str,
    *,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
):
    """Validate `url` (and every redirect hop) against the SSRF guard, then open it.

    Raises BlockedURLError before any connection if the URL — or any redirect
    target — uses a bad scheme or points at a non-public address.
    """
    validate_url(url)
    req = urllib.request.Request(url, headers=headers or {})
    opener = urllib.request.build_opener(_ValidatingRedirectHandler)
    return opener.open(req, timeout=timeout)
