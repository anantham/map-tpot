"""HTTP transport pinned to validated public addresses, with hostname TLS."""
from __future__ import annotations

import http.client
import ipaddress
import math
import socket
import ssl
import threading
import time
from urllib.parse import urljoin

from src.api.response_limits import BoundedResponse, LimitedHTTPResponse
from src.api.url_guard import BlockedURLError, resolve_public_url

MAX_REDIRECTS = 5


class PinnedConnection(http.client.HTTPConnection):
    def __init__(self, destination, timeout, deadline):
        super().__init__(destination.host, destination.port, timeout=timeout)
        self.destination = destination
        self.deadline = deadline
        self.expired = threading.Event()
        self.timer = None
        self.deadline_socket = None

    def _expire(self):
        self.expired.set()
        sock = self.deadline_socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def cancel_deadline(self):
        if self.timer is not None:
            self.timer.cancel()
        self.deadline_socket = None

    def _check_deadline(self):
        if self.expired.is_set() or time.monotonic() >= self.deadline:
            self._expire()
            raise BlockedURLError("outbound connection deadline exceeded")

    def connect(self):
        last_error = None
        self.timer = threading.Timer(max(0, self.deadline - time.monotonic()), self._expire)
        self.timer.daemon = True
        self.timer.start()
        for family, ip in self.destination.addresses:
            sock = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            self.sock = sock
            self.deadline_socket = sock
            try:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("outbound connection deadline exceeded")
                sock.settimeout(remaining)
                address = (ip, self.port, 0, 0) if family == socket.AF_INET6 else (ip, self.port)
                sock.connect(address)  # Numeric sockaddr; never re-resolve the hostname.
                self._verify_peer(sock, ip)
                if self.destination.scheme == "https":
                    sock = ssl.create_default_context().wrap_socket(
                        sock, server_hostname=self.destination.host, do_handshake_on_connect=False)
                    self.sock = sock
                    self.deadline_socket = sock
                    self._check_deadline()  # The timer may fire while wrap_socket detaches the raw socket.
                    sock.do_handshake()
                    self._verify_peer(sock, ip)
                self._check_deadline()
                self.sock = sock
                return
            except BlockedURLError:
                sock.close()
                raise
            except (OSError, ValueError) as exc:
                sock.close()
                if self.expired.is_set():
                    raise BlockedURLError("outbound connection deadline exceeded") from exc
                last_error = exc
        raise BlockedURLError("could not connect to a validated outbound address") from last_error

    @staticmethod
    def _verify_peer(sock, expected):
        try:
            peer = ipaddress.ip_address(sock.getpeername()[0])
        except (ValueError, OSError) as exc:
            raise BlockedURLError("could not verify outbound connection peer") from exc
        if peer != ipaddress.ip_address(expected):
            raise BlockedURLError("outbound peer differs from the validated address")


def open_pinned(url, *, timeout, headers, max_bytes, max_wire_bytes=None):
    """GET only, no ambient proxies or credentials, with validation at every hop."""
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("outbound timeout must be finite and positive")
    wire_limit = max_bytes if max_wire_bytes is None else max_wire_bytes
    if any(not isinstance(v, int) or isinstance(v, bool) or not 0 < v <= 16_777_216
           for v in (max_bytes, wire_limit)):
        raise ValueError("outbound byte limits must be positive and at most 16 MiB")
    request_headers = {key: value for key, value in headers.items()
                       if key.lower() in {"user-agent", "accept"}}
    request_headers.update({"Accept-Encoding": "identity", "Connection": "close"})
    deadline = time.monotonic() + timeout
    for hop in range(MAX_REDIRECTS + 1):
        destination = resolve_public_url(url, deadline=deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BlockedURLError("outbound fetch deadline exceeded")
        connection = PinnedConnection(destination, remaining, deadline)
        connection.response_class = lambda sock, **kwargs: LimitedHTTPResponse(
            sock, deadline=deadline, max_wire_bytes=wire_limit, **kwargs)
        response = None
        try:
            connection.request("GET", destination.target,
                               headers={**request_headers, "Host": destination.authority})
            peer_socket = connection.sock
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                response.close()
                connection.close()
                connection.cancel_deadline()
                if not location or hop == MAX_REDIRECTS:
                    raise BlockedURLError("missing redirect target or redirect limit exceeded")
                url = urljoin(url, location)
                continue
            if not 200 <= response.status < 300:
                raise BlockedURLError(f"outbound HTTP response status {response.status}")
            return BoundedResponse(response, connection, peer_socket, url, deadline,
                                   max_bytes=max_bytes, max_wire_bytes=wire_limit)
        except Exception:
            connection.close()
            connection.cancel_deadline()
            if response is not None:
                response.close()
            raise
    raise BlockedURLError("outbound redirect limit exceeded")
