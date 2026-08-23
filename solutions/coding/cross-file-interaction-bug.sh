#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > service.py
from db import save_to_db
from cache import invalidate_cache

def update_profile(user_id: int, new_data: dict):
    success = save_to_db(user_id, new_data)
    if success:
        invalidate_cache(user_id)
PYEOF
