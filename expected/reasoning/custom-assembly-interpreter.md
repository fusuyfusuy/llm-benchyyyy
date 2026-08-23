# custom-assembly-interpreter — expected

**grading method:** unit test

## Held-out test suite

```python
# test_interpreter.py
import pytest
from interpreter import run_program

def test_basic():
    code = "MOV R0, 5\nADD R0, R0\nHALT"
    assert run_program(code) == 10

def test_jump_and_loop():
    code = """
MOV R1, 5
MOV R2, 1
SUB R1, R2
JZ R1, 5
JMP 2
HALT
"""
    assert run_program(code) == 0

def test_modulo():
    code = "MOV R0, 0\nMOV R1, 5\nSUB R0, R1\nHALT"
    assert run_program(code) == 251

def test_infinite_loop():
    code = "MOV R0, 0\nJMP 0\nHALT"
    with pytest.raises(RuntimeError):
        run_program(code)

def test_empty_lines_ignored_for_index():
    code = "\n\nMOV R0, 10\n\n\nHALT\n"
    assert run_program(code) == 10
```

## Check
```bash
pytest -q test_interpreter.py
```
