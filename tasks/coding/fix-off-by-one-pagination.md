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

## Constraints

- Must not modify the function signature.
- Fix should be a minimal diff — flag (don't fail) a submission that rewrites the whole
  function unnecessarily; note it under `constraint_violations` in metrics, it's a
  style signal not a correctness one.
