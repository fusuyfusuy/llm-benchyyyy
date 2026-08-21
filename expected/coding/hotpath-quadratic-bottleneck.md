# hotpath-quadratic-bottleneck — expected

**grading method:** unit test (executable, not judge)

## Held-out test suite

```python
# test_metrics.py
import random, time
import pytest
from metrics import rolling_max, count_pairs_within

def brute_rolling(series, window):
    if window < 1:
        raise ValueError
    return [max(series[i:i+window]) for i in range(len(series) - window + 1)]

def brute_pairs(values, t):
    n = len(values); c = 0
    for i in range(n):
        for j in range(i+1, n):
            if abs(values[i]-values[j]) <= t:
                c += 1
    return c

# ---------- correctness: rolling_max ----------

def test_rm_edges():
    assert rolling_max([], 3) == []
    assert rolling_max([5], 1) == [5]
    assert rolling_max([1, 2], 5) == []
    with pytest.raises(ValueError):
        rolling_max([1], 0)
    with pytest.raises(ValueError):
        rolling_max([1], -2)

def test_rm_no_alias_even_when_trivial():
    src = [7, 7, 7]
    out = rolling_max(src, 1)
    assert out == src and out is not src
    out.append(99)
    assert src == [7, 7, 7]

def test_rm_ties_and_negatives():
    assert rolling_max([2, 2, 2, 2], 2) == [2, 2, 2]
    assert rolling_max([-5, -1, -9, -3], 2) == [-1, -1, -3]
    assert rolling_max([4, -4, 4, -4, 4], 3) == [4, 4, 4]

def test_rm_random_vs_oracle():
    rng = random.Random(1234)
    for _ in range(60):
        n = rng.randint(0, 40)
        series = [rng.randint(-50, 50) for _ in range(n)]
        w = rng.randint(1, n + 3)
        expected = brute_rolling(series, w) if w >= 1 else None
        if w < 1:
            with pytest.raises(ValueError):
                rolling_max(series, w)
        else:
            assert rolling_max(series, w) == expected

# ---------- correctness: count_pairs_within ----------

def test_cp_duplicates_and_empty():
    assert count_pairs_within([], 5) == 0
    assert count_pairs_within([1], 5) == 0
    assert count_pairs_within([9, 9, 9], 0) == 3      # C(3,2), threshold 0 counts equals
    assert count_pairs_within([1, 2, 3], -1) == 0     # negative threshold -> none
    assert count_pairs_within([1, 2, 3], 1) == 2      # (1,2),(2,3) but not (1,3)

def test_cp_does_not_modify_input():
    v = [3, 1, 2]
    count_pairs_within(v, 10)
    assert v == [3, 1, 2]

def test_cp_random_vs_oracle():
    rng = random.Random(99)
    for _ in range(40):
        n = rng.randint(0, 60)
        values = [rng.randint(-20, 20) for _ in range(n)]
        t = rng.randint(-2, 15)
        assert count_pairs_within(values, t) == brute_pairs(values, t)

# ---------- performance gates ----------

def test_rm_performance():
    rng = random.Random(7)
    series = [rng.randint(0, 10**6) for _ in range(300_000)]
    w = 2000
    t0 = time.perf_counter()
    out = rolling_max(series, w)
    dt = time.perf_counter() - t0
    assert len(out) == len(series) - w + 1
    assert dt < 8.0, f"rolling_max too slow: {dt:.1f}s"

def test_cp_performance():
    rng = random.Random(8)
    values = [rng.randint(0, 10**6) for _ in range(80_000)]
    t0 = time.perf_counter()
    c = count_pairs_within(values, 500)
    dt = time.perf_counter() - t0
    assert isinstance(c, int) and c > 0
    assert dt < 8.0, f"count_pairs_within too slow: {dt:.1f}s"
```

## Pass criteria

All nine tests pass. Binary pass/fail. The two performance gates are the point of
the task — a submission that passes correctness but trips a gate fails.

## Check

```bash
pytest -q test_metrics.py
```

## Oracle solution

```python
from bisect import bisect_left, insort


def rolling_max(series, window):
    if window < 1:
        raise ValueError("window must be >= 1")
    n = len(series)
    if window > n:
        return []
    from collections import deque
    dq = deque()  # indices, decreasing values
    out = []
    for i, v in enumerate(series):
        while dq and series[dq[-1]] <= v:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - window:
            dq.popleft()
        if i >= window - 1:
            out.append(series[dq[0]])
    return out


def count_pairs_within(values, threshold):
    if threshold < 0 or len(values) < 2:
        return 0
    xs = sorted(values)
    count = 0
    lo = 0
    for hi in range(len(xs)):
        while xs[hi] - xs[lo] > threshold:
            lo += 1
        count += hi - lo
    return count
```

(`count` sums, over each `hi`, the number of valid partners at smaller sorted
positions — exactly the unordered index pairs; duplicates handled naturally.)

## Notes for scoring

- The perf gates are sized so the seeded implementations need minutes; anything
  still quadratic fails. But watch for "cheating" speedups that change semantics —
  the randomized oracle tests use different data than the perf tests on purpose.
- A deque-based `rolling_max` that pops equal elements with `<` instead of `<=`
  still passes correctness but degrades toward O(n·w) on all-equal inputs; the
  perf gate uses random data so it won't catch that. Acceptable.
- `count_pairs_within` solutions via `bisect` (`insort` into a sorted list) are
  O(n²) worst case due to list insertion — they may pass the 8s gate marginally;
  that's fine, it's a real algorithmic choice.
