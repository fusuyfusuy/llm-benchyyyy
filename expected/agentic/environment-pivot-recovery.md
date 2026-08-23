# environment-pivot-recovery — expected

**grading method:** executable state check (file matches expected output)

## Expected Output

```csv
# expected_rates.csv
Currency,Rate
EUR,0.85
GBP,0.72
JPY,110.5
```

## Pass criteria

The file `rates.csv` must exist and exactly match the expected CSV format, containing the rates parsed from the XML output of the legacy fetcher.

## Check

```bash
# Clean up carriage returns just in case
tr -d '\r' < rates.csv > rates_clean.csv
cat << 'INNER_EOF' > expected.csv
Currency,Rate
EUR,0.85
GBP,0.72
JPY,110.5
INNER_EOF

cmp rates_clean.csv expected.csv
```
