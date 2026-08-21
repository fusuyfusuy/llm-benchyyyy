# ttl-cache-concurrency-audit

**dimension(s):** raw model, coding harness, tool-use/agentic (concurrency
debugging, invariant reasoning)
**difficulty tier:** hard

## Instruction

`ttlcache.py` is an in-process TTL + LRU cache used by our request path. Under load
it intermittently throws, loses track of its own contents, and evicts the wrong
entries. Find and fix every defect so it upholds this contract:

- Thread-safe: any mix of concurrent `get`/`set`/`delete`/`keys()`/`len()` calls
  must never raise, corrupt internal state, or expose intermediate state.
- Bounded: `len(cache)` never exceeds `maxsize`, counting only live (unexpired)
  entries.
- TTL: an entry is live until `now - stored_at >= ttl`. Expired entries behave as
  absent: `get` returns the default, `keys()` and `len()` exclude them, and their
  space is reusable. Stale entries must be reclaimed eventually (lazy reclamation on
  access/mutation is fine) — but reclamation must never remove an entry that was
  overwritten with a fresh value.
- LRU: when a `set` of a NEW key would exceed `maxsize`, the least-recently-used
  live entry is evicted first. `get` counts as a use. `set` on an existing key
  updates value, refreshes its recency AND its TTL timestamp, and evicts nothing
  (unless it was expired).
- `clock` is an injectable monotonic seconds callable for testing; production passes
  nothing (time.monotonic).

## Environment/setup

Fresh checkout containing:

```python
# ttlcache.py
"""Thread-safe TTL + LRU cache. See task spec for the contract."""

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
        # BUG: a single lock exists but get()'s fast path skips it

    def _expired(self, stored_at, now=None):
        return (now or self._clock()) - stored_at >= self._ttl

    def _purge_expired(self):
        now = self._clock()
        # BUG: unsynchronized sweep -- races with other threads' get/set,
        # raising KeyError here or deleting entries written mid-sweep
        for k, (_, stored_at) in self._data.items():
            if now - stored_at >= self._ttl:
                del self._data[k]

    def get(self, key, default=None):
        entry = self._data.get(key)
        if entry is None:
            return default
        if self._expired(entry[1]):
            # BUG: check-then-act gap; two threads can both get here
            del self._data[key]
            return default
        # BUG: recency bump outside any lock
        self._data.move_to_end(key)
        return entry[0]

    def set(self, key, value):
        now = self._clock()
        if key in self._data and not self._expired(self._data[key][1], now):
            self._data[key] = [value, now]
            self._data.move_to_end(key)
            return
        # BUG: purge may free nothing because it ran before another thread's
        # insert landed; also evicts newest-first on ties
        self._purge_expired()
        while len(self._data) >= self._maxsize:
            self._data.popitem()  # BUG: pops MOST recent (end), contract says LRU
        self._data[key] = [value, now]

    def delete(self, key):
        self._data.pop(key, None)

    def keys(self):
        now = self._clock()
        return [k for k, (_, stored_at) in self._data.items()
                if now - stored_at < self._ttl]

    def __len__(self):
        return len(self.keys())
```

Tests are ground truth. Where comments, variable names, or structure suggest
different behavior than the contract above, the contract wins.

## Constraints

- Public API (`TTLCache(maxsize, ttl, clock)`, `.get`, `.set`, `.delete`, `.keys`,
  `__len__`) must not change.
- Standard library only.
- Correctness must not come from serializing everything behind coarse locking that
  changes observable semantics (e.g., `get` must still return values, expired
  entries must still be reclaimable). Held-out tests include a multi-threaded
  stress phase with forced interleavings.
