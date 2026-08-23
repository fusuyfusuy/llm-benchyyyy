# cross-file-interaction-bug

**dimension(s):** raw model
**difficulty tier:** hard

## Instruction

Users are reporting that occasionally their user profile updates are saved to the database, but the cache is not invalidated, causing stale reads. 
There are 4 files involved: `routes.py`, `service.py`, `db.py`, and `cache.py`.
Find the bug that causes the cache invalidation to be skipped, and fix it. Do not change the general architecture or add new libraries.

## Environment/setup

```python
# routes.py
from service import update_profile

def handle_update_request(user_id: int, new_data: dict):
    update_profile(user_id, new_data)
    return "OK"

# service.py
from db import save_to_db
from cache import invalidate_cache

def update_profile(user_id: int, new_data: dict):
    success = save_to_db(user_id, new_data)
    if success is True:
        invalidate_cache(user_id)

# db.py
def save_to_db(user_id: int, new_data: dict) -> int:
    """Saves data and returns the number of rows affected."""
    # Simulated db save
    rows_affected = 1
    return rows_affected

# cache.py
def invalidate_cache(user_id: int):
    # Simulated cache clear
    with open("cache_cleared.log", "a") as f:
        f.write(f"{user_id}\n")
```

## Constraints
- Standard library only.
