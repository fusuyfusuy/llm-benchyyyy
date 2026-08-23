#!/usr/bin/env bash
set -euo pipefail

# Recover permissions if read-only
chmod 0644 logs/app-2026-01-10.log 2>/dev/null || true

FILES=()
for n in $(seq -w 1 14); do
  FILES+=("app-2026-01-${n}.log")
done

tar -czf logs/archive-early-jan.tar.gz -C logs "${FILES[@]}"

for f in "${FILES[@]}"; do
  rm -f "logs/$f"
done
