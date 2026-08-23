# cross-file-interaction-bug — expected

**grading method:** unit test

## Held-out test suite

```python
# test_bug.py
import os
from routes import handle_update_request

def test_cache_is_invalidated():
    if os.path.exists("cache_cleared.log"):
        os.remove("cache_cleared.log")
        
    handle_update_request(42, {"name": "Test"})
    
    assert os.path.exists("cache_cleared.log"), "Cache was not invalidated!"
    with open("cache_cleared.log") as f:
        assert "42" in f.read()
```

## Pass criteria
The bug is in `service.py`: it checks `if success is True:`. However, `db.py`'s `save_to_db` returns an `int` (the number of rows affected, e.g., `1`). In Python, `1 is True` evaluates to `False` (identity vs equality). The agent must either change `service.py` to `if success:` or `if success == 1:`, or change `db.py` to return a boolean.

## Check
```bash
pytest -q test_bug.py
```
