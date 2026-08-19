# fix-off-by-one-pagination — expected

**grading method:** unit test (executable, not judge)

## Held-out test suite

```python
# test_paginate.py
from paginate import paginate

def test_no_overlap_between_pages():
    items = list(range(10))
    page0 = paginate(items, 0, 3)
    page1 = paginate(items, 1, 3)
    assert page0 == [0, 1, 2]
    assert page1 == [3, 4, 5]
    assert set(page0).isdisjoint(page1)

def test_page_size_respected():
    items = list(range(10))
    assert len(paginate(items, 0, 3)) == 3

def test_last_partial_page():
    items = list(range(7))
    assert paginate(items, 2, 3) == [6]
```

## Pass criteria

All three tests pass (`pytest test_paginate.py`), exit code 0. No partial credit — this
is a binary pass/fail task.

## Oracle solution

```python
def paginate(items, page, page_size):
    start = page * page_size
    end = start + page_size
    return items[start:end]
```

## Notes for scoring

If the agent's fix passes the tests via a different but equally minimal approach (e.g.
computing `end` differently), that's a pass. If it passes by special-casing around the
bug instead of fixing the off-by-one (e.g. slicing then dropping the last element), mark
`result: pass` but flag `constraint_violations: workaround-not-fix` — it satisfies the
test but is the kind of fix that would resurface with a different `page_size`.
