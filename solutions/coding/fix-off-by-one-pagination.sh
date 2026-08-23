#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > paginate.py
def paginate(items, page, page_size):
    start = page * page_size
    end = start + page_size
    return items[start:end]
PYEOF
