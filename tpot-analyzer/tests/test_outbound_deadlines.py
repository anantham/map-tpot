"""Test intent: slow DNS and within-line/body trickles cannot evade total time.

- Timed-out DNS uses ≤4 daemon workers with no backlog, then recovers.
- Absolute socket shutdown cancels header/body/TLS operations before they return.
Events and fake sockets simulate stuck operations; no live DNS/HTTP is used.
"""
import io
import socket
import threading
import time

import pytest

from src.api.url_guard import BlockedURLError, safe_urlopen
from tests.test_outbound_transport import FakeSocket, answer, network, wire


def test_stuck_dns_is_time_bounded_with_fixed_capacity(network, monkeypatch):
    release = threading.Event()
    workers = []
    def stuck(host, port, **kwargs):
        workers.append(threading.current_thread())
        release.wait()
        return answer("93.184.216.34", port)
    monkeypatch.setattr(socket, "getaddrinfo", stuck)
    try:
        for _ in range(4):
            with pytest.raises(BlockedURLError):
                safe_urlopen("http://public.example/", timeout=0.02)
        start = time.monotonic()
        with pytest.raises(BlockedURLError):
            safe_urlopen("http://public.example/", timeout=0.5)
        assert time.monotonic() - start < 0.2
        assert len(workers) == 4 and all(worker.daemon for worker in workers)
        assert network[1] == []
    finally:
        release.set()
        for worker in workers:
            worker.join(timeout=1)
            assert not worker.is_alive()
    # Finished lookups release all slots so normal requests recover.
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **k: answer("93.184.216.34", port))
    network[0].append((wire(),))
    with safe_urlopen("http://public.example/") as response:
        assert response.read() == b"ok"


class TrickleSocket(FakeSocket):
    def __init__(self, stage):
        super().__init__(wire())
        self.shutdown_event = threading.Event()
        event = self.shutdown_event
        class TrickleFile(io.BytesIO):
            calls = 0
            def readline(self, size=-1):
                self.calls += 1
                if stage == "headers" and self.calls == 2:
                    assert event.wait(1), "absolute deadline did not interrupt headers"
                    return b""
                return super().readline(size)
            def read1(self, size=-1):
                if stage == "body":
                    assert event.wait(1), "absolute deadline did not interrupt body"
                    return b""
                return super().read1(size)
        self.buffer = TrickleFile(wire())

    def shutdown(self, *args):
        self.shutdown_event.set()


@pytest.mark.parametrize("stage", ["headers", "body"])
def test_absolute_deadline_interrupts_in_progress_reads(network, monkeypatch, stage):
    sock = TrickleSocket(stage)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: sock)
    start = time.monotonic()
    with pytest.raises(BlockedURLError):
        with safe_urlopen("http://public.example/", timeout=0.05) as response:
            response.read()
    assert time.monotonic() - start < 1
    assert sock.shutdown_event.is_set() and sock.closed


def test_absolute_deadline_interrupts_tls_handshake(network, monkeypatch):
    import ssl
    sock = TrickleSocket("tls")
    monkeypatch.setattr(socket, "socket", lambda *a, **k: sock)
    def handshake():
        assert sock.shutdown_event.wait(1), "absolute deadline did not interrupt TLS"
        raise socket.timeout("synthetic cancelled TLS")
    sock.do_handshake = handshake
    class Context:
        def wrap_socket(self, value, **kwargs):
            assert kwargs["server_hostname"] == "public.example"
            assert kwargs["do_handshake_on_connect"] is False
            return value
    monkeypatch.setattr(ssl, "create_default_context", Context)
    with pytest.raises(BlockedURLError):
        safe_urlopen("https://public.example/", timeout=0.05)
    assert sock.shutdown_event.is_set() and sock.sent == b"" and sock.closed


def test_expiry_during_tls_socket_swap_cannot_start_handshake(network, monkeypatch):
    import ssl
    from src.api import outbound_transport
    timers = []
    class Timer:
        def __init__(self, interval, callback):
            self.callback = callback
        def start(self):
            timers.append(self)
        def cancel(self):
            pass
    monkeypatch.setattr(outbound_transport.threading, "Timer", Timer)
    raw = TrickleSocket("raw")
    replacement = TrickleSocket("tls")
    def forbidden_handshake():
        pytest.fail("an expired swapped TLS socket must not start its handshake")
    replacement.do_handshake = forbidden_handshake
    monkeypatch.setattr(socket, "socket", lambda *a, **k: raw)
    class Context:
        def wrap_socket(self, sock, **kwargs):
            replacement.address = sock.address
            sock.close()  # Simulate transfer/detach of the raw socket descriptor.
            timers[0].callback()  # Deadline lands before the returned socket can be assigned.
            return replacement
    monkeypatch.setattr(ssl, "create_default_context", Context)
    with pytest.raises(BlockedURLError):
        safe_urlopen("https://public.example/")
    assert raw.closed and replacement.closed and replacement.shutdown_event.is_set()
