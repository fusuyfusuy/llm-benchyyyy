#!/usr/bin/env bash
set -euo pipefail

# 1. Create data_parser.py with parse_config(file_path) function
cat << 'PYEOF' > data_parser.py
import json

def parse_config(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
PYEOF

# 2. Fix config.json by removing trailing comma after "sk-456"
sed -i 's/"sk-456",/"sk-456"/' config.json
