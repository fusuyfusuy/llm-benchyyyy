# fix-off-by-one-pagination

**dimension(s):** raw model, coding harness
**difficulty tier:** easy

## Instruction

The repo has a `paginate(items, page, page_size)` function used across several call
sites. Users report that the last item of each page is duplicated as the first item of
the next page. Find the bug and fix it. Do not change the function's signature or the
call sites — only fix the bug inside `paginate`.

## Environment/setup

Fresh checkout of a small scratch repo containing (place these files verbatim before
the run):

```python
# paginate.py
def paginate(items, page, page_size):
    start = page * page_size
    end = start + page_size + 1  # bug lives here
    return items[start:end]
```

```python
# test_paginate.py  (present in the repo but NOT run for the agent — held out, see expected/)
```

Give the agent `paginate.py` and a natural-language bug report only. Do not show it
`test_paginate.py`.

## Constraints

- Must not modify the function signature.
- Must not modify or delete the held-out test file if it's visible in the working tree.
- Fix should be a minimal diff — flag (don't fail) a submission that rewrites the whole
  function unnecessarily; note it under `constraint_violations` in metrics, it's a
  style signal not a correctness one.
