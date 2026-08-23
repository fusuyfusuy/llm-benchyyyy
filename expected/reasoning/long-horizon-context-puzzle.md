# long-horizon-context-puzzle — expected

**grading method:** unit test (executable, not judge)

## Held-out test suite

```python
# test_config_merger.py
import pytest
from config_merger import merge_configs

def test_basic_override():
    base = {"a": 1, "b": 2}
    override = {"b": 3, "c": 4}
    assert merge_configs(base, override) == {"a": 1, "b": 3, "c": 4}

def test_deep_merge():
    base = {"db": {"host": "localhost", "port": 5432}}
    override = {"db": {"port": 5433, "user": "admin"}}
    assert merge_configs(base, override) == {"db": {"host": "localhost", "port": 5433, "user": "admin"}}

def test_null_deletion():
    base = {"a": 1, "b": 2}
    override = {"a": None, "c": None}
    assert merge_configs(base, override) == {"b": 2}

def test_list_append():
    base = {"tags_append": ["v1"], "normal_list": [1, 2]}
    override = {"tags_append": ["v2"], "normal_list": [3, 4]}
    assert merge_configs(base, override) == {"tags_append": ["v1", "v2"], "normal_list": [3, 4]}
    
    # Should not append if one is not a list
    base2 = {"tags_append": ["v1"]}
    override2 = {"tags_append": "not-a-list"}
    assert merge_configs(base2, override2) == {"tags_append": "not-a-list"}

def test_ignore_internal_keys():
    base = {"a": 1}
    override = {"__debug": True, "__a": 2, "b": 3}
    assert merge_configs(base, override) == {"a": 1, "b": 3}

def test_security_constraint_admin_roles():
    # Buried constraint: admin_roles never overridden
    base = {"users": {"admin_roles": ["superadmin"]}, "admin_roles": ["owner"]}
    override = {"users": {"admin_roles": ["hacker"]}, "admin_roles": ["hacker"], "new_roles": {"admin_roles": ["hacker"]}}
    
    merged = merge_configs(base, override)
    assert merged["users"]["admin_roles"] == ["superadmin"]
    assert merged["admin_roles"] == ["owner"]
    # If it wasn't in base, the override shouldn't add it either!
    assert "admin_roles" not in merged["new_roles"]

def test_no_mutation():
    base = {"a": {"b": 1}}
    override = {"a": {"c": 2}}
    merge_configs(base, override)
    assert base == {"a": {"b": 1}}
    assert override == {"a": {"c": 2}}
```

## Pass criteria

All tests pass. Binary pass/fail.

## Check

```bash
pytest -q test_config_merger.py
```
