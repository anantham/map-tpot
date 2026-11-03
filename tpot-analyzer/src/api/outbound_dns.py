"""Time-bounded system DNS with a fixed number of in-flight resolver calls.

System getaddrinfo cannot be interrupted safely. A timed-out daemon worker
retains its slot until resolution finishes; new callers fail closed when all
four slots are occupied. There is no waiting queue or unbounded thread growth.
"""
from __future__ import annotations

import socket
import threading
import time

from src.api.url_guard import BlockedURLError

MAX_RESOLVERS = 4
_SLOTS = threading.BoundedSemaphore(MAX_RESOLVERS)


def resolve_bounded(host, port, *, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not _SLOTS.acquire(blocking=False):
        raise BlockedURLError("outbound DNS deadline exceeded or resolver capacity unavailable")
    done = threading.Event()
    result, errors = [], []
    resolver = socket.getaddrinfo

    def run():
        try:
            result.extend(resolver(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP))
        except Exception as exc:
            errors.append(exc)
        finally:
            _SLOTS.release()
            done.set()

    try:
        threading.Thread(target=run, daemon=True, name="tpot-outbound-dns").start()
    except Exception:
        _SLOTS.release()
        raise
    if not done.wait(max(0, deadline - time.monotonic())) or time.monotonic() >= deadline:
        raise BlockedURLError("outbound DNS resolution deadline exceeded")
    if errors:
        raise BlockedURLError("outbound DNS resolution failed") from errors[0]
    return result
