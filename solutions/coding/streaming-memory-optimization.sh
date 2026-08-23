#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > processor.py
import json
from typing import Iterator, Dict, Any


def process_telemetry(filepath: str) -> Iterator[Dict[str, Any]]:
    """
    Reads a JSONL file and yields parsed events 
    where the event type is 'CRITICAL'.
    """
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("type") == "CRITICAL":
                yield event
PYEOF
chmod +x solutions/coding/streaming-memory-optimization.sh
