#!/usr/bin/env bash
set -euo pipefail

grep -roh 'SECRET_FLAG={[a-zA-Z0-9_]*}' logs/ > solution.txt
