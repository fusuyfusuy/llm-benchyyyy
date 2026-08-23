# streaming-memory-optimization — expected

**grading method:** unit test

## Held-out test suite

```python
# test_processor.py
import os, sys, json, types
import pytest
from processor import process_telemetry

def test_returns_generator():
    # Create a small dummy file
    with open("dummy.jsonl", "w") as f:
        f.write('{"type": "CRITICAL", "msg": "A"}\n')
    
    gen = process_telemetry("dummy.jsonl")
    assert isinstance(gen, types.GeneratorType) or hasattr(gen, '__iter__')
    
    results = list(gen)
    assert len(results) == 1
    assert results[0]["msg"] == "A"

def test_memory_streaming():
    # We test this by replacing the standard open() with a mock that throws
    # if readlines() or read() is called without a size limit.
    # A true streaming solution will iterate over the file object directly.
    import builtins
    original_open = builtins.open
    
    class StrictFileProxy:
        def __init__(self, f):
            self.f = f
        def __iter__(self):
            return self.f.__iter__()
        def __next__(self):
            return next(self.f)
        def readlines(self, hint=-1):
            raise MemoryError("readlines() called")
        def read(self, size=-1):
            if size == -1:
                raise MemoryError("read() all called")
            return self.f.read(size)
        def close(self):
            self.f.close()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

        # delegate other attributes safely
        def __getattr__(self, name):
            return getattr(self.f, name)
            
    def strict_open(*args, **kwargs):
        f = original_open(*args, **kwargs)
        return StrictFileProxy(f)

    builtins.open = strict_open
    try:
        with original_open("dummy2.jsonl", "w") as f:
            f.write('{"type": "INFO", "msg": "B"}\n')
            f.write('{"type": "CRITICAL", "msg": "C"}\n')
            
        gen = process_telemetry("dummy2.jsonl")
        results = list(gen)
        assert len(results) == 1
        assert results[0]["msg"] == "C"
    finally:
        builtins.open = original_open
```

## Check
```bash
pytest -q test_processor.py
```
