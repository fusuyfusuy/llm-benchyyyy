# add-csv-export-endpoint — expected

**grading method:** unit test (executable, not judge)

## Held-out test suite

```python
# test_users.py
import csv, io
from users import export_users_csv, USERS

def test_header_and_order():
    out = export_users_csv(USERS)
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0] == ["id", "name", "email", "created_at"]
    ids = [r[0] for r in rows[1:]]
    assert ids == ["1", "2", "3"]

def test_no_third_party_import():
    src = open("users.py").read()
    for banned in ("pandas", "import requests"):
        assert banned not in src
```

## Pass criteria

Both tests pass. Binary pass/fail on the tests; the "standard library only" constraint
is graded separately (a passing-but-constraint-violating run is `result: pass`,
`constraint_violations: used-pandas` or similar).

## Check

```bash
pytest -q test_users.py
```

## Oracle solution

```python
import csv
import io

def export_users_csv(users):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "name", "email", "created_at"])
    writer.writeheader()
    for user in sorted(users, key=lambda u: u["id"]):
        writer.writerow(user)
    return output.getvalue()
```

## Notes for scoring

Manual `csv.writer` string-joining (instead of `csv.DictWriter`) is fine if it passes
the tests. Watch for a subtle failure mode: sorting `users` in place (mutating the
shared `USERS` list) rather than sorting a copy — not caught by the test above as
written, but worth a quick manual check (`id(USERS) == id(users)` order unchanged after
the call) since it's the kind of silent side-effect bug that matters more in agentic
multi-step runs than in a single grading pass.

## Grader Notes

Moved from `tasks/` (contamination hygiene 2026-08-30).

- A held-out `test_users.py` exists for grading but is not shown to the agent; the
  graded copy is seeded at check time from `## Held-out test suite` above.
