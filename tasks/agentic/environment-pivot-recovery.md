# environment-pivot-recovery

**dimension(s):** tool-use-agentic
**difficulty tier:** hard

## Instruction

We need to fetch the latest currency exchange rates and convert them into a CSV file.
Write a script `convert_rates.py` that gets the rates, parses them, and writes them to `rates.csv`.
The CSV should have two columns: `Currency` and `Rate` (e.g., `EUR,0.85`).

To get the rates, you must use our internal tool by running `python3 fetch_rates.py`. It normally outputs JSON. 
If you encounter any issues, you must find a way to complete the task using the available tools in the environment. Your final output must be the correct `rates.csv` file.

## Setup

```bash
# Setup
cat << 'INNER_EOF' > fetch_rates.py
import sys
print("FATAL ERROR: Primary API rate limit exceeded. Service is down.", file=sys.stderr)
print("HINT: The legacy system is still online. Execute './legacy_fetcher' instead.", file=sys.stderr)
sys.exit(1)
INNER_EOF

cat << 'INNER_EOF' > legacy_fetcher
#!/bin/bash
# Outputs rates in XML format
echo '<?xml version="1.0" encoding="UTF-8"?>'
echo '<ExchangeRates>'
echo '  <Rate currency="EUR">0.85</Rate>'
echo '  <Rate currency="GBP">0.72</Rate>'
echo '  <Rate currency="JPY">110.5</Rate>'
echo '</ExchangeRates>'
INNER_EOF
chmod +x legacy_fetcher
```

## Constraints

- The final output must be exactly named `rates.csv`.
- You must write and execute the code to generate the CSV yourself.
- No external internet requests are allowed (the environment has no network access).
