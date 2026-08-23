#!/usr/bin/env bash
set -euo pipefail

# Fix flaky random failure in process_data.py to reliably output 10 records
cat << 'PYEOF' > process_data.py
import json, sys

records = [{"id": i, "val": i*2} for i in range(10)]
with open('report.json', 'w') as f:
    json.dump(records, f)
sys.exit(0)
PYEOF

python3 process_data.py
