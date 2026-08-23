# streaming-memory-optimization

**dimension(s):** raw model
**difficulty tier:** hard

## Instruction

The `process_telemetry` function in `processor.py` analyzes telemetry logs. However, it crashes with an Out-Of-Memory (OOM) error in production because the log files are over 50GB.
Your task is to refactor `process_telemetry` to use an $O(1)$ memory footprint (streaming/generator) instead of $O(N)$. 
It should yield the exact same parsed results, but one by one.

## Environment/setup

```python
# processor.py
import json
from typing import List, Dict, Any

def process_telemetry(filepath: str) -> List[Dict[str, Any]]:
    """
    Reads a JSONL file and returns a list of parsed events 
    where the event type is 'CRITICAL'.
    """
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if event.get("type") == "CRITICAL":
            results.append(event)
            
    return results
```

## Constraints
- Standard library only.
- Change the return type hint and implementation to return an Iterator/Generator.
- Do not hold the entire file or large lists in memory.
