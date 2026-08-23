#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > users.py
import csv
import io

USERS = [
    {"id": 3, "name": "Cy", "email": "cy@example.com", "created_at": "2026-01-03"},
    {"id": 1, "name": "Al", "email": "al@example.com", "created_at": "2026-01-01"},
    {"id": 2, "name": "Bo", "email": "bo@example.com", "created_at": "2026-01-02"},
]

def export_users_csv(users):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id", "name", "email", "created_at"])
    writer.writeheader()
    for user in sorted(users, key=lambda u: u["id"]):
        writer.writerow(user)
    return output.getvalue()
PYEOF
