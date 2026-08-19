# add-csv-export-endpoint

**dimension(s):** raw model, coding harness, tool-use/agentic (multi-file change +
running tests to self-check)
**difficulty tier:** medium

## Instruction

Add a new function `export_users_csv(users)` to `users.py` that takes the existing
`users` list (list of `dict` with keys `id`, `name`, `email`, `created_at`) and returns
a CSV-formatted string with a header row, sorted by `id` ascending. Use the standard
library only (no new dependencies). Wire it up so it's importable as
`from users import export_users_csv`.

## Environment/setup

Fresh checkout of a small scratch repo containing:

```python
# users.py
USERS = [
    {"id": 3, "name": "Cy", "email": "cy@example.com", "created_at": "2026-01-03"},
    {"id": 1, "name": "Al", "email": "al@example.com", "created_at": "2026-01-01"},
    {"id": 2, "name": "Bo", "email": "bo@example.com", "created_at": "2026-01-02"},
]
```

Held-out test file exists in the repo (`test_users.py`) but is not shown to the agent.

## Constraints

- Standard library only — flag any new third-party import as a constraint violation
  even if the task still passes.
- Must not rename or remove `USERS`.
- Field order in the CSV header must be `id,name,email,created_at`.
