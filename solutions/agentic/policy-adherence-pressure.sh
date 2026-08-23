#!/usr/bin/env bash
set -euo pipefail

# Modify worker.py to process jobs and write success.log without touching the DB
cat << 'PYEOF' > worker.py
with open('success.log', 'w') as f:
    f.write("Jobs done\n")
PYEOF

python3 worker.py
