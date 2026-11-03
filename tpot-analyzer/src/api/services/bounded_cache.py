"""Thread-safe TTL/LRU cache with entry and serialized-byte ceilings."""
from __future__ import annotations

import json
from copy import deepcopy
from sys import getsizeof
from collections import OrderedDict
from threading import RLock
from time import monotonic


class BoundedCache:
    def __init__(self, max_entries=64, max_bytes=16 * 1024 * 1024, ttl_seconds=300):
        if min(max_entries, max_bytes, ttl_seconds) <= 0:
            raise ValueError("cache limits must be positive")
        self.max_entries, self.max_bytes, self.ttl = max_entries, max_bytes, ttl_seconds
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = RLock()

    def _remove(self, key):
        _, _, size = self._entries.pop(key)
        self._bytes -= size

    def _expire(self):
        now = monotonic()
        for key, (_, expires, _) in list(self._entries.items()):
            if expires <= now:
                self._remove(key)

    def get(self, key):
        with self._lock:
            self._expire()
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry[0])

    def set(self, key, data):
        if not isinstance(key, str) or len(key) > 256:
            return False
        try:
            raw = data if isinstance(data, (str, bytes)) else json.dumps(data, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            return False
        size = len(raw.encode("utf-8") if isinstance(raw, str) else raw) + len(key.encode("utf-8"))
        if size > self.max_bytes:
            return False
        data = deepcopy(data)
        # Count retained Python objects as well as the serialized response.
        seen, pending, retained = set(), [key, data], 0
        while pending:
            item = pending.pop()
            if id(item) in seen:
                continue
            seen.add(id(item))
            retained += getsizeof(item)
            if retained > self.max_bytes:
                return False
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, (list, tuple)):
                pending.extend(item)
        size = max(size, retained)
        with self._lock:
            self._expire()
            if key in self._entries:
                self._remove(key)
            if size > self.max_bytes:
                return False
            while self._entries and (len(self._entries) >= self.max_entries or self._bytes + size > self.max_bytes):
                self._remove(next(iter(self._entries)))
            self._entries[key] = (data, monotonic() + self.ttl, size)
            self._bytes += size
            return True

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    def __len__(self):
        with self._lock:
            self._expire()
            return len(self._entries)
