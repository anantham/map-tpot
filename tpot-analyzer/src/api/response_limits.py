"""Streaming encoded/decoded response budgets for enrichment HTTP requests."""
from __future__ import annotations

import time
import zlib
import http.client

from src.api.url_guard import BlockedURLError

CHUNK_BYTES = 16_384
HTTP_OVERHEAD_BYTES = 65_536


class BudgetedSocketFile:
    """Bound bytes/time below HTTP parsing, including headers and chunk trailers."""
    def __init__(self, sock, deadline, limit):
        self.sock, self.deadline, self.limit = sock, deadline, limit
        self.fp = sock.makefile("rb")
        self.count = 0

    def _read(self, method, size=-1):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise BlockedURLError("outbound HTTP parsing deadline exceeded")
        self.sock.settimeout(remaining)
        budget = self.limit - self.count + 1
        size = budget if size is None or size < 0 else min(size, budget)
        data = getattr(self.fp, method)(size)
        self.count += len(data)
        if self.count > self.limit or time.monotonic() > self.deadline:
            self.close()
            raise BlockedURLError("outbound HTTP framing byte/time limit exceeded")
        return data

    def read(self, size=-1):
        return self._read("read", size)

    def read1(self, size=-1):
        return self._read("read1", size)

    def readline(self, size=-1):
        return self._read("readline", size)

    def close(self):
        self.fp.close()

    def flush(self):
        if not self.fp.closed:
            self.fp.flush()


class LimitedHTTPResponse(http.client.HTTPResponse):
    def __init__(self, sock, *args, deadline, max_wire_bytes, **kwargs):
        class FileSocket:
            def makefile(self, *args):
                return BudgetedSocketFile(sock, deadline, max_wire_bytes + HTTP_OVERHEAD_BYTES)
        super().__init__(FileSocket(), *args, **kwargs)


class BoundedResponse:
    """Small urlopen-compatible context manager whose reads enforce total caps."""
    def __init__(self, response, connection, peer_socket, url, deadline, *, max_bytes, max_wire_bytes):
        self.response, self.connection, self.socket = response, connection, peer_socket
        self.url, self.deadline = url, deadline
        self.headers, self.status = response.headers, response.status
        self.max_bytes, self.max_wire_bytes = max_bytes, max_wire_bytes
        self.wire_bytes = self.decoded_bytes = 0
        self.buffer = bytearray()
        self.eof = self.closed = False
        self.decoder = None
        try:
            length = response.getheader("Content-Length")
            if length is not None and (not length.isascii() or not length.isdigit() or int(length) > max_wire_bytes):
                raise BlockedURLError("invalid or oversized outbound Content-Length")
            transfer = response.getheader("Transfer-Encoding")
            if transfer and (length is not None or transfer.strip().lower() != "chunked"):
                raise BlockedURLError("ambiguous outbound response framing")
            encoding = (response.getheader("Content-Encoding") or "identity").strip().lower()
            if encoding == "gzip":
                self.decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            elif encoding == "deflate":
                self.decoder = zlib.decompressobj()
            elif encoding != "identity":
                raise BlockedURLError("unsupported outbound Content-Encoding")
        except Exception:
            self.close()
            raise

    def _next_chunk(self):
        try:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise BlockedURLError("outbound response deadline exceeded")
            self.socket.settimeout(remaining)
            chunk = self.response.read1(min(CHUNK_BYTES, self.max_wire_bytes - self.wire_bytes + 1))
            self.wire_bytes += len(chunk)
            if self.wire_bytes > self.max_wire_bytes:
                raise BlockedURLError("outbound encoded response byte limit exceeded")
            if self.decoder:
                decoded = self.decoder.decompress(chunk, self.max_bytes - self.decoded_bytes + 1)
                if self.decoder.unused_data:
                    raise BlockedURLError("trailing or concatenated compressed response prohibited")
            else:
                decoded = chunk
            self.decoded_bytes += len(decoded)
            if self.decoded_bytes > self.max_bytes:
                raise BlockedURLError("outbound decoded response byte limit exceeded")
            self.buffer.extend(decoded)
            if not chunk:
                if self.decoder and not self.decoder.eof:
                    raise BlockedURLError("truncated compressed outbound response")
                self.eof = True
        except (OSError, ValueError, zlib.error, http.client.HTTPException) as exc:
            self.close()
            raise BlockedURLError("outbound response stream failed") from exc
        except Exception:
            self.close()
            raise

    def read(self, size=-1):
        if self.closed:
            raise ValueError("read from closed outbound response")
        if size is None:
            size = -1
        if not isinstance(size, int):
            raise TypeError("read size must be an integer")
        while not self.eof and (size < 0 or len(self.buffer) < size):
            self._next_chunk()
        count = len(self.buffer) if size < 0 else min(size, len(self.buffer))
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def geturl(self):
        return self.url

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.response.close()
            finally:
                self.connection.close()
                self.connection.cancel_deadline()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
