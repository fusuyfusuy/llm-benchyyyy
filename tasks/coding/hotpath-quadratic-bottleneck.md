# hotpath-quadratic-bottleneck

**dimension(s):** raw model, coding harness
**difficulty tier:** hard

## Instruction

`metrics.py` powers our analytics endpoints and is failing its latency SLOs in
production. Profiling points at two functions. Your job: make both fast enough to
pass the performance tests **without changing their observable behavior in any way**
— same inputs, same outputs, same exceptions, same edge-case rules as documented in
their docstrings.

The existing implementations are correct but far too slow. Rewrite them with proper
algorithms/data structures. Standard library only. Do not change any public
signature, and do not return aliases of caller-owned input.

## Environment/setup

Fresh checkout containing:

```python
# metrics.py
"""Hot-path analytics helpers."""

def rolling_max(series, window):
    """Sliding-window maximum.

    Returns a NEW list where output[i] = max(series[i : i + window]), for
    i in range(len(series) - window + 1). The input list is never modified and
    the returned list never aliases it.

    Raises ValueError if window < 1.
    Returns [] if window > len(series) (including when series is empty).
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    out = []
    for i in range(len(series) - window + 1):
        out.append(max(series[i : i + window]))
    return out


def count_pairs_within(values, threshold):
    """Count unordered index pairs (i, j), i < j, with abs(values[i]-values[j]) <= threshold.

    Duplicates count: three equal values contribute C(3,2)=3 pairs.
    Negative thresholds count 0 pairs (abs difference is always >= 0).
    Does not modify `values`.
    """
    n = len(values)
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            if abs(values[i] - values[j]) <= threshold:
                count += 1
    return count
```

## Constraints

- Public signatures and documented behavior must not change (held-out tests probe
  edge cases AND equivalence against a brute-force oracle on randomized inputs).
- Standard library only; no third-party imports; no subprocess tricks.
- The performance tests are part of the suite: if either function still runs the
  old algorithm, they fail. Do not special-case the benchmark inputs — the oracle
  equivalence tests use different data than the performance tests.
