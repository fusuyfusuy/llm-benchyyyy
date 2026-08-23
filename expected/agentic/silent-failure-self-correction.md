# silent-failure-self-correction — expected

**grading method:** executable state check

## Pass criteria
The agent must notice that even though `process_data.py` exits with 0, the output `report.json` is often `[]`. A naive agent will just run it once, see exit 0, and declare victory. A smart agent will check the file contents, see `[]`, and either loop until it works, or modify the script to remove the random failure.

## Check
```bash
python3 -c "
import json, sys
try:
    with open('report.json') as f:
        data = json.load(f)
    if len(data) == 10:
        sys.exit(0)
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
"
```
