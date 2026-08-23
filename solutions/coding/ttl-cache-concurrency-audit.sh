#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > ttlcache.py
"""Thread-safe TTL + LRU cache."""

import threading
import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, maxsize=128, ttl=60.0, clock=None):
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._maxsize = maxsize
        self._ttl = ttl
        self._clock = clock or time.monotonic
        self._data = OrderedDict()  # key -> [value, stored_at]
        self._lock = threading.RLock()

    def _expired(self, stored_at, now=None):
        return (now if now is not None else self._clock()) - stored_at >= self._ttl

    def get(self, key, default=None):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default
            if self._expired(entry[1]):
                del self._data[key]
                return default
            self._data.move_to_end(key)
            return entry[0]

    def set(self, key, value):
        now = self._clock()
        with self._lock:
            entry = self._data.get(key)
            if entry is not None and not self._expired(entry[1], now):
                self._data[key] = [value, now]
                self._data.move_to_end(key)
                return
            self._data.pop(key, None)  # drop stale shadow, if any
            # reclaim expired first, then LRU
            stale = [k for k, (_, at) in self._data.items() if self._expired(at, now)]
            for k in stale:
                del self._data[k]
            while len(self._data) >= self._maxsize:
                self._data.popitem(last=False)  # least-recently-used
            self._data[key] = [value, now]

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def keys(self):
        now = self._clock()
        with self._lock:
            return [k for k, (_, at) in self._data.items() if not self._expired(at, now)]

    def __len__(self):
        return len(self.keys())
PYEOF
chmod +x solutions/coding/ttl-cache-concurrency-audit.sh
