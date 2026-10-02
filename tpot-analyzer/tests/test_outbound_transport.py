"""Test intent: outbound fetches bind URL validation to the actual socket.

- A rebinding resolver cannot move a validated request to a private address.
- Every redirect is validated and connection-pinned; peers must match.
- HTTPS keeps the original TLS hostname and Host authority, without proxies.
- Header-free, dishonest, compressed and chunked bodies obey streaming caps.
All sockets, DNS and TLS here are synthetic; no network requests are made.
"""
from __future__ import annotations

import gzip
import io
import socket
import zlib

import pytest

from src.api.url_guard import BlockedURLError, safe_urlopen, validate_url


def answer(ip, port=80):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    address = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)]


class FakeSocket:
    def __init__(self, wire, peer=None):
        self.buffer = io.BytesIO(wire)
        self.peer = peer
        self.address = None
        self.sent = b""
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def setsockopt(self, *args):
        pass

    def connect(self, address):
        self.address = address

    def getpeername(self):
        return (self.peer or self.address[0], self.address[1])

    def sendall(self, data):
        self.sent += data

    def makefile(self, *args):
        return self.buffer

    def close(self):
        self.closed = True

    def shutdown(self, *args):
        pass

    def do_handshake(self):
        pass


def wire(body=b"ok", headers=b"", status=b"200 OK"):
    return b"HTTP/1.1 " + status + b"\r\n" + headers + b"\r\n" + body


@pytest.fixture
def network(monkeypatch):
    sockets = []
    pending = []
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kwargs: answer("93.184.216.34", port))

    def factory(*args, **kwargs):
        assert pending, "unexpected additional socket"
        sock = FakeSocket(*pending.pop(0))
        sockets.append(sock)
        return sock

    monkeypatch.setattr(socket, "socket", factory)
    return pending, sockets


def test_rebinding_cannot_change_connected_address(network, monkeypatch):
    pending, sockets = network
    pending.append((wire(),))
    resolutions = []

    def rebinding(host, port, *args, **kwargs):
        resolutions.append(host)
        return answer("93.184.216.34" if len(resolutions) == 1 else "127.0.0.1", port)

    monkeypatch.setattr(socket, "getaddrinfo", rebinding)
    with safe_urlopen("http://public.example/article") as response:
        assert response.read() == b"ok"
    assert sockets[0].address == ("93.184.216.34", 80)
    assert resolutions == ["public.example"]


@pytest.mark.parametrize("url", [
    "http://93.184.216.34:notaport/", "http://93.184.216.34:0/",
    "http://user:password@93.184.216.34/", "http://[fe80::1%en0]/",
])
def test_invalid_authority_is_rejected_before_socket(url, network):
    with pytest.raises(BlockedURLError):
        validate_url(url)
    assert network[1] == []


def test_wrong_peer_is_rejected_before_http(network):
    pending, sockets = network
    pending.append((wire(), "127.0.0.1"))
    with pytest.raises(BlockedURLError):
        safe_urlopen("http://public.example/")
    assert sockets[0].sent == b""
    assert sockets[0].closed


def test_https_preserves_tls_hostname_and_host(network, monkeypatch):
    import ssl
    pending, sockets = network
    pending.append((wire(),))
    tls_hosts = []

    class Context:
        def wrap_socket(self, sock, *, server_hostname, **kwargs):
            tls_hosts.append(server_hostname)
            return sock

    monkeypatch.setattr(ssl, "create_default_context", Context)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9876")
    with safe_urlopen("https://public.example:8443/article") as response:
        assert response.read() == b"ok"
    assert tls_hosts == ["public.example"]
    assert sockets[0].address == ("93.184.216.34", 8443)
    assert b"Host: public.example:8443\r\n" in sockets[0].sent


def test_redirect_revalidates_private_destination(network):
    pending, sockets = network
    pending.append((wire(headers=b"Location: http://127.0.0.1/\r\n", status=b"302 Found"),))
    with pytest.raises(BlockedURLError):
        safe_urlopen("http://public.example/")
    assert len(sockets) == 1
    assert sockets[0].closed


def test_redirects_pin_new_host_and_resolve_relative_paths(network, monkeypatch):
    pending, sockets = network
    pending.extend([
        (wire(headers=b"Location: https://second.example/base\r\n", status=b"302 Found"),),
        (wire(headers=b"Location: /article\r\n", status=b"307 Temporary Redirect"),),
        (wire(b"article"),),
    ])
    hosts = []
    def resolve(host, port, **kwargs):
        hosts.append(host)
        return answer("93.184.216.34" if host == "public.example" else "1.1.1.1", port)
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    import ssl
    class Context:
        def wrap_socket(self, sock, **kwargs):
            return sock
    monkeypatch.setattr(ssl, "create_default_context", Context)
    with safe_urlopen("http://public.example/") as response:
        assert response.url == "https://second.example/article"
        assert response.read() == b"article"
    assert hosts == ["public.example", "second.example", "second.example"]
    assert [sock.address[0] for sock in sockets] == ["93.184.216.34", "1.1.1.1", "1.1.1.1"]
    assert all(sock.closed for sock in sockets)


@pytest.mark.parametrize("headers,body", [
    (b"", b"x" * 101),
    (b"Content-Length: 101\r\n", b"x" * 101),
    (b"Transfer-Encoding: chunked\r\n", b"65\r\n" + b"x" * 101 + b"\r\n0\r\n\r\n"),
])
def test_actual_stream_size_is_bounded(network, headers, body):
    pending, sockets = network
    pending.append((wire(body, headers),))
    with pytest.raises(BlockedURLError):
        with safe_urlopen("http://public.example/", max_bytes=100) as response:
            response.read()
    assert sockets[0].closed


@pytest.mark.parametrize("encoding,body", [
    (b"gzip", gzip.compress(b"x" * 100_000)),
    (b"deflate", zlib.compress(b"x" * 100_000)),
])
def test_compression_bomb_is_bounded(network, encoding, body):
    pending, sockets = network
    pending.append((wire(body, b"Content-Encoding: " + encoding + b"\r\n"),))
    with pytest.raises(BlockedURLError):
        with safe_urlopen("http://public.example/", max_bytes=1024) as response:
            response.read()
    assert sockets[0].closed


def test_caps_apply_across_incremental_reads(network):
    pending, sockets = network
    pending.append((wire(b"x" * 101),))
    with safe_urlopen("http://public.example/", max_bytes=100) as response:
        class SlowChunks(io.BytesIO):
            def read1(self, size=-1):
                return super().read1(min(size, 25))
        response.response.fp.fp = SlowChunks(sockets[0].buffer.read())
        assert response.read(50) == b"x" * 50
        assert response.read(50) == b"x" * 50
        with pytest.raises(BlockedURLError):
            response.read(1)
