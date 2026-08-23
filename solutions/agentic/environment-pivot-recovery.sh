#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > convert_rates.py
import subprocess
import xml.etree.ElementTree as ET
import csv

out = subprocess.check_output(["./legacy_fetcher"]).decode("utf-8")
root = ET.fromstring(out)

with open("rates.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Currency", "Rate"])
    for rate in root.findall("Rate"):
        writer.writerow([rate.attrib["currency"], rate.text.strip()])
PYEOF

python3 convert_rates.py
