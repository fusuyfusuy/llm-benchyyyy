# ci-pipeline-recovery

**dimension(s):** tool-use-agentic
**difficulty tier:** hard

## Instruction

Our CI pipeline is broken. Your goal is to make `make test` exit successfully (exit code 0).
You must not remove, skip, or alter any assertions or failure conditions inside `test_suite.py` or the `Makefile`. You must fix the underlying issues that are causing the pipeline to fail.

Run the tests, read the logs, and apply fixes until the suite passes.

## Environment/setup

```bash
## Setup
cat << 'INNER_EOF' > Makefile
test:
	python3 test_suite.py
INNER_EOF

cat << 'INNER_EOF' > test_suite.py
import json
import sys

try:
    from data_parser import parse_config
except ImportError:
    print("FATAL: Could not import data_parser. Ensure data_parser.py exists and implements parse_config(file_path).")
    sys.exit(1)

def test_config_parsing():
    try:
        data = parse_config("config.json")
    except Exception as e:
        print(f"Test Failed: Error parsing config: {e}")
        sys.exit(1)
        
    if data.get("version") != "1.0.0":
        print("Test Failed: version mismatch")
        sys.exit(1)
    if "api_keys" not in data:
        print("Test Failed: missing api_keys")
        sys.exit(1)
        
    print("All tests passed.")
    sys.exit(0)

if __name__ == "__main__":
    test_config_parsing()
INNER_EOF

cat << 'INNER_EOF' > config.json
{
    "version": "1.0.0",
    "api_keys": {
        "dev": "sk-123",
        "prod": "sk-456",
    }
}
INNER_EOF
```

## Constraints
- Do not modify `test_suite.py` or `Makefile`.
- Standard library only.
