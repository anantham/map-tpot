"""Tests for the SSRF guard used by the tweet-enrichment pipeline.

The guard's contract: refuse to fetch any URL that isn't an http(s) URL
resolving entirely to public, routable addresses, and re-check every redirect
hop so a public URL can't 302 into an internal one. See src/api/url_guard.py.
"""
from __future__ import annotations

import socket
import urllib.request

import pytest

from src.api.url_guard import (
    BlockedURLError,
    _ValidatingRedirectHandler,
    safe_urlopen,
    validate_url,
)


def _fake_getaddrinfo(ip: str):
    """Return a getaddrinfo stub that resolves every host to `ip`."""
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, 80, 0, 0) if family == socket.AF_INET6 else (ip, 80)
    return lambda *a, **k: [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]


# ── scheme allowlist ─────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com/",
    "localhost:5001/admin",  # no scheme — urlparse reads 'localhost' as the scheme
])
def test_rejects_non_http_schemes(url):
    with pytest.raises(BlockedURLError):
        validate_url(url)


# ── IP literals that must be blocked ─────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
    "http://10.0.0.1/",
    "http://192.168.1.1/",
    "http://172.16.0.1/",
    "http://0.0.0.0/",
    "http://[::1]/",                              # IPv6 loopback
    "http://[::ffff:10.0.0.1]/",                  # IPv4-mapped IPv6
    "http://100.100.100.100/",                    # Tailscale / CGNAT 100.64.0.0/10
])
def test_rejects_non_public_ip_literals(url):
    with pytest.raises(BlockedURLError):
        validate_url(url)


@pytest.mark.unit
def test_allows_public_ip_literal():
    validate_url("http://93.184.216.34/")  # public literal — no DNS, no exception


# ── hostname resolution ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_rejects_hostname_resolving_to_private_ip(monkeypatch):
    """A domain that points inward — the internal-domain / DNS-rebinding case."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("10.1.2.3"))
    with pytest.raises(BlockedURLError):
        validate_url("http://evil.example.com/")


@pytest.mark.unit
def test_rejects_hostname_resolving_to_tailscale_ip(monkeypatch):
    """A t.co link must not be fetchable just because it points at the tailnet."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("100.92.1.1"))
    with pytest.raises(BlockedURLError):
        validate_url("http://gpu-box.example.ts.net/")


@pytest.mark.unit
def test_allows_hostname_resolving_to_public_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    validate_url("http://example.com/article")  # no exception


@pytest.mark.unit
def test_rejects_unresolvable_hostname(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror("name resolution failed")
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(BlockedURLError):
        validate_url("http://does-not-exist.invalid/")


# ── safe_urlopen short-circuits before any network call ──────────────────────

@pytest.mark.unit
def test_safe_urlopen_blocks_before_opening():
    """A blocked URL must raise without attempting a connection."""
    with pytest.raises(BlockedURLError):
        safe_urlopen("http://169.254.169.254/latest/meta-data/")


# ── redirect hops are re-validated ───────────────────────────────────────────

@pytest.mark.unit
def test_redirect_handler_blocks_private_redirect_target():
    """A public URL must not be able to 302 into a private address."""
    handler = _ValidatingRedirectHandler()
    req = urllib.request.Request("http://example.com/")
    with pytest.raises(BlockedURLError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/")
