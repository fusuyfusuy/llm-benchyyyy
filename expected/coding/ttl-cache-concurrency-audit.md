# ttl-cache-concurrency-audit — expected

**grading method:** unit test (executable, not judge)

## Held-out test suite

```python
# test_ttlcache.py
import sys, threading, time
import pytest
from ttlcache import TTLCache

class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def advance(self, dt): self.t += dt

# ---------- single-threaded semantics ----------

def test_basic_set_get_delete():
    c = TTLCache(maxsize=4, ttl=10)
    c.set("a", 1); c.set("b", 2)
    assert c.get("a") == 1 and c.get("b") == 2 and len(c) == 2
    c.delete("a")
    assert c.get("a") is None and len(c) == 1

def test_ttl_expiry_is_absent_behaviour():
    ck = FakeClock()
    c = TTLCache(maxsize=8, ttl=5.0, clock=ck)
    c.set("k", "v")
    assert c.get("k") == "v"
    ck.advance(4.999)
    assert c.get("k") == "v"          # still live at ttl-epsilon
    ck.advance(0.001)
    assert c.get("k") is None         # >= ttl means expired
    assert len(c) == 0 and c.keys() == []

def test_len_and_keys_exclude_expired():
    ck = FakeClock()
    c = TTLCache(maxsize=8, ttl=5.0, clock=ck)
    c.set("x", 1); c.set("y", 2)
    ck.advance(6)
    assert len(c) == 0
    assert c.keys() == []
    c.set("z", 3)
    assert c.keys() == ["z"]

def test_set_refreshes_ttl_and_recency_no_evict():
    ck = FakeClock()
    c = TTLCache(maxsize=2, ttl=10.0, clock=ck)
    c.set("a", 1)
    ck.advance(3)
    c.set("a", 9)          # overwrite: refresh ts + recency, no eviction
    ck.advance(3)
    assert c.get("a") == 9  # age 3 < 10 since refresh
    ck.advance(7)           # age now 10 >= ttl -> expired despite original set at t=0
    assert c.get("a") is None

def test_lru_eviction_order():
    ck = FakeClock()
    c = TTLCache(maxsize=2, ttl=100.0, clock=ck)
    c.set("a", 1); c.set("b", 2)
    c.get("a")             # a now most recent; b is LRU
    c.set("c", 3)          # must evict b
    assert c.get("b") is None
    assert c.get("a") == 1 and c.get("c") == 3

def test_eviction_skips_expired_without_failing():
    ck = FakeClock()
    c = TTLCache(maxsize=2, ttl=10.0, clock=ck)
    c.set("a", 1)
    ck.advance(11)          # a expired
    c.set("b", 2)
    c.set("c", 3)           # b fills slot; expired 'a' must not block or crash
    assert c.get("c") == 3 and len(c) <= 2

def test_overwrite_does_not_evict():
    c = TTLCache(maxsize=2, ttl=100.0)
    c.set("a", 1); c.set("b", 2)
    c.set("a", 10)          # existing key: never evicts anything
    assert c.get("a") == 10 and c.get("b") == 2 and len(c) == 2

def test_never_exceeds_maxsize_single_thread():
    c = TTLCache(maxsize=3, ttl=1000.0)
    for i in range(50):
        c.set(f"k{i}", i)
        assert len(c) <= 3

# ---------- concurrency ----------

def run_stress(c, n_threads, ops_per_thread, key_space, barrier):
    errors = []
    def worker(tid):
        try:
            barrier.wait(timeout=10)
            for i in range(ops_per_thread):
                k = (tid * 7919 + i * 104729) % key_space
                if i % 5 == 0:
                    c.delete(k)
                elif i % 3 == 0:
                    c.get(k)
                else:
                    c.set(k, (tid, i))
        except Exception as e:  # noqa: BLE001 - collected, asserted below
            errors.append(repr(e))
    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    return errors

def test_stress_no_errors_bounded_consistent():
    old_switch = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # force interleavings
    try:
        c = TTLCache(maxsize=64, ttl=30.0)
        errs = run_stress(c, n_threads=8, ops_per_thread=600, key_space=128,
                          barrier=threading.Barrier(8))
        assert errs == [], f"threads raised: {errs[:3]}"
        assert len(c) <= 64
        exposed = c.keys()
        assert len(exposed) <= 64
        assert len(set(exposed)) == len(exposed)
        # every exposed key must be retrievable without raising
        for k in exposed:
            c.get(k)
    finally:
        sys.setswitchinterval(old_switch)

def test_aligned_expiry_race_on_hot_key():
    # All threads hit one just-expired key simultaneously: exactly one logical
    # delete may happen, nobody may raise, everyone gets the default.
    old_switch = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # maximize interleaving pressure
    try:
        c = TTLCache(maxsize=8, ttl=0.05)
        c.set("hot", "value")
        time.sleep(0.06)
        n = 16
        barrier = threading.Barrier(n)
        results, errors = [], []
        lock = threading.Lock()
        def worker():
            try:
                barrier.wait(timeout=10)
                r = c.get("hot", "MISS")
                with lock:
                    results.append(r)
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(repr(e))
        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads: t.start()
        for t in threads: t.join()
    finally:
        sys.setswitchinterval(old_switch)
    assert errors == [], f"racing gets raised: {errors[:3]}"
    assert results == ["MISS"] * n
    assert len(c) == 0

def test_concurrent_overwrite_never_loses_all_writes():
    # N threads write distinct values to the SAME key; afterwards the cache must
    # hold ONE of the written values (never a torn/missing entry while live).
    c = TTLCache(maxsize=8, ttl=60.0)
    n = 6
    barrier = threading.Barrier(n)
    vals = list(range(1000, 1000 + n))
    def worker(v):
        barrier.wait(timeout=10)
        for _ in range(200):
            c.set("shared", v)
    threads = [threading.Thread(target=worker, args=(v,)) for v in vals]
    for t in threads: t.start()
    for t in threads: t.join()
    got = c.get("shared")
    assert got in vals
```

## Pass criteria

All eleven tests pass. Binary pass/fail. The stress test runs once per grading;
the aligned-race test is deterministic enough that the seeded code fails it on
every run.

## Check

```bash
pytest -q test_ttlcache.py
```

## Oracle solution

```python
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
        self._lock = __import__("threading").RLock()

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
```

## Notes for scoring

- The seeded `popitem()` defaults to `last=True` — it evicts the MOST recent
  entry. `test_lru_eviction_order` catches this without any threads.
- The check-then-act expiry gap fails `test_aligned_expiry_race_on_hot_key`
  loudly (raw KeyError escaping `get`). A fix that swallows KeyError but leaks
  other state problems will trip the stress invariants.
- Coarse-locking everything is an ACCEPTED fix here (the contract bans changing
  observable semantics, not locking granularity) — do not penalize it.
- Solutions using a per-key striping scheme are fine too, provided all eleven
  tests pass.
