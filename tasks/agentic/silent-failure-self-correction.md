# silent-failure-self-correction

**dimension(s):** tool-use-agentic
**difficulty tier:** hard

## Instruction

Run the `process_data.py` script to generate `report.json`. 
Your task is complete when `report.json` contains exactly 10 processed records. The script is known to be flaky, but you must produce a valid `report.json` containing the 10 records.

## Environment/setup

```bash
## Setup
cat << 'INNER' > process_data.py
import json, random, sys
# Deliberately fails silently 80% of the time, exiting 0 but writing an empty list
if random.random() < 0.8:
    with open('report.json', 'w') as f:
        json.dump([], f)
    sys.exit(0)

records = [{"id": i, "val": i*2} for i in range(10)]
with open('report.json', 'w') as f:
    json.dump(records, f)
sys.exit(0)
INNER
```

## Constraints
- You may run the script as many times as you need, or modify it if necessary.
- The final `report.json` must have exactly 10 records.
