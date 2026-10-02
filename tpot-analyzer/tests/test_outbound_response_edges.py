"""Test intent: fail closed on framing/encoding ambiguity and transport edges.

Synthetic DNS/sockets cover mixed answers, IPv6 and TLS verification failures.
Bounded valid compressed bodies remain readable; malformed ones are discarded.
"""
import gzip
import http.client
import socket
import ssl
import zlib

import pytest

from src.api.url_guard import BlockedURLError, safe_urlopen, validate_url
from tests.test_outbound_transport import answer, network, wire


def test_mixed_public_private_answer_is_rejected(network, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: answer("1.1.1.1") + answer("10.0.0.1"))
    with pytest.raises(BlockedURLError):
        safe_urlopen("http://public.example/")
    assert network[1] == []


def test_public_ipv6_literal_connects_without_dns(network, monkeypatch):
    pending, sockets = network
    pending.append((wire(),))
    def no_dns(*args, **kwargs):
        pytest.fail("an IP literal must not be resolved again")
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    with safe_urlopen("http://[2606:4700:4700::1111]:8080/") as response:
        assert response.read() == b"ok"
    assert sockets[0].address == ("2606:4700:4700::1111", 8080, 0, 0)
    assert b"Host: [2606:4700:4700::1111]:8080\r\n" in sockets[0].sent


def test_transition_address_cannot_embed_private_ipv4(network):
    with pytest.raises(BlockedURLError):
        validate_url("http://[2002:7f00:0001::]/")


def test_tls_verification_errors_fail_closed(network, monkeypatch):
    pending, sockets = network
    pending.append((wire(),))
    context = ssl.create_default_context()
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    class RejectingContext:
        def wrap_socket(self, sock, *, server_hostname, **kwargs):
            raise ssl.SSLCertVerificationError("synthetic invalid certificate")
    monkeypatch.setattr(ssl, "create_default_context", RejectingContext)
    with pytest.raises(BlockedURLError):
        safe_urlopen("https://public.example/")
    assert sockets[0].sent == b"" and sockets[0].closed


def test_tls_wrapped_peer_is_checked(network, monkeypatch):
    pending, sockets = network
    pending.append((wire(),))
    class Context:
        def wrap_socket(self, sock, **kwargs):
            sock.peer = "127.0.0.1"
            return sock
    monkeypatch.setattr(ssl, "create_default_context", Context)
    with pytest.raises(BlockedURLError):
        safe_urlopen("https://public.example/")
    assert sockets[0].sent == b"" and sockets[0].closed


def test_redirect_cap_closes_every_hop(network):
    pending, sockets = network
    pending.extend([(wire(headers=b"Location: /again\r\n", status=b"302 Found"),)] * 6)
    with pytest.raises(BlockedURLError):
        safe_urlopen("http://public.example/")
    assert len(sockets) == 6 and all(sock.closed for sock in sockets)


def test_sensitive_headers_never_follow_redirects(network):
    pending, sockets = network
    pending.extend([
        (wire(headers=b"Location: http://second.example/\r\n", status=b"302 Found"),),
        (wire(),),
    ])
    with safe_urlopen("http://public.example/", headers={"Host": "127.0.0.1", "Cookie": "private", "Authorization": "private"}) as response:
        assert response.read() == b"ok"
    assert all(b"private" not in sock.sent and b"Host: 127.0.0.1" not in sock.sent for sock in sockets)


@pytest.mark.parametrize("encoding,body", [(b"gzip", gzip.compress(b"small body")), (b"deflate", zlib.compress(b"small body"))])
def test_valid_compressed_body_is_decoded(network, encoding, body):
    pending, _ = network
    pending.append((wire(body, b"Content-Encoding: " + encoding + b"\r\n"),))
    with safe_urlopen("http://public.example/", max_bytes=100) as response:
        assert response.read() == b"small body"


@pytest.mark.parametrize("headers,body", [
    (b"Content-Encoding: br\r\n", b"unknown"),
    (b"Content-Encoding: gzip\r\n", gzip.compress(b"small")[:-5]),
    (b"Content-Encoding: gzip\r\n", gzip.compress(b"one") + gzip.compress(b"two")),
    (b"Content-Encoding: gzip\r\n", b"invalid gzip"),
    (b"Transfer-Encoding: chunked\r\nContent-Length: 1\r\n", b"1\r\nx\r\n0\r\n\r\n"),
    (b"Content-Length: 1, 1\r\n", b"x"),
    (b"Content-Length: -1\r\n", b"x"),
    (b"Transfer-Encoding: gzip\r\n", b"ambiguous"),
])
def test_malformed_responses_are_closed(network, headers, body):
    pending, sockets = network
    pending.append((wire(body, headers),))
    with pytest.raises(BlockedURLError):
        with safe_urlopen("http://public.example/") as response:
            response.read()
    assert sockets[0].closed


def test_encoded_cap_is_independent_of_decoded_cap(network):
    pending, _ = network
    pending.append((wire(gzip.compress(b"x"), b"Content-Encoding: gzip\r\n"),))
    with pytest.raises(BlockedURLError):
        with safe_urlopen("http://public.example/", max_bytes=100, max_wire_bytes=10) as response:
            response.read()


def test_http_trailer_overhead_is_bounded(network):
    pending, sockets = network
    body = b"1\r\nx\r\n0\r\n" + b"X-Trailer: synthetic\r\n" * 10_000 + b"\r\n"
    pending.append((wire(body, b"Transfer-Encoding: chunked\r\n"),))
    with pytest.raises(BlockedURLError):
        with safe_urlopen("http://public.example/", max_bytes=100) as response:
            response.read()
    assert sockets[0].closed


def test_body_total_deadline_does_not_reset_on_reads(network, monkeypatch):
    from src.api import response_limits
    pending, sockets = network
    pending.append((wire(),))
    with safe_urlopen("http://public.example/") as response:
        monkeypatch.setattr(response_limits.time, "monotonic", lambda: response.deadline + 1)
        with pytest.raises(BlockedURLError):
            response.read()
    assert sockets[0].closed


@pytest.mark.parametrize("parse_error", [
    http.client.HTTPException("synthetic trailer parser rejection"),
    http.client.IncompleteRead(b"x", 2),
])
def test_http_parser_body_errors_are_normalized_and_closed(network, monkeypatch, parse_error):
    """Stdlib parser limits must expose the guarded response failure contract."""
    pending, sockets = network
    pending.append((wire(),))
    def reject_body(*args, **kwargs):
        raise parse_error
    monkeypatch.setattr(http.client.HTTPResponse, "read1", reject_body)
    with safe_urlopen("http://public.example/") as response:
        with pytest.raises(BlockedURLError):
            response.read()
        assert response.closed and sockets[0].closed
