#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > metrics.py
"""Hot-path analytics helpers."""
from collections import deque


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
    n = len(series)
    if window > n:
        return []

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
    """Count unordered index pairs (i, j), i < j, with abs(values[i]-values[j]) <= threshold.

    Duplicates count: three equal values contribute C(3,2)=3 pairs.
    Negative thresholds count 0 pairs (abs difference is always >= 0).
    Does not modify `values`.
    """
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
PYEOF
