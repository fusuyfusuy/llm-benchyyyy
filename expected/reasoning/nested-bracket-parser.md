# nested-bracket-parser — expected

**grading method:** unit test

## Held-out test suite

```python
# test_parser.py
import pytest
from parser import parse_lisp_expr

def test_flat():
    assert parse_lisp_expr("(a b c)") == ["a", "b", "c"]

def test_nested():
    assert parse_lisp_expr("(a (b c) d)") == ["a", ["b", "c"], "d"]

def test_deeply_nested():
    assert parse_lisp_expr("(first (second third (fourth)))") == ["first", ["second", "third", ["fourth"]]]

def test_no_spaces_around_brackets():
    assert parse_lisp_expr("((a)b(c))") == [["a"], "b", ["c"]]

def test_empty():
    assert parse_lisp_expr("()") == []
    
def test_empty_nested():
    assert parse_lisp_expr("(() ())") == [[], []]
```

## Check
```bash
pytest -q test_parser.py
```
