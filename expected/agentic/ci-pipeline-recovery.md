# ci-pipeline-recovery — expected

**grading method:** executable state check

## Pass criteria
1. The `test_suite.py` file must remain unmodified.
2. Running `python3 test_suite.py` must exit 0 and output "All tests passed."

To achieve this, the agent must sequentially create `data_parser.py` with a valid JSON parsing function, and then discover and fix the syntax error (trailing comma) in `config.json`.

## Check
```bash
# Verify test_suite.py wasn't modified to cheat
HASH_CURRENT=$(sha256sum test_suite.py | awk '{print $1}')
cat << 'INNER_EOF' > test_suite_original.py
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
HASH_EXPECTED=$(sha256sum test_suite_original.py | awk '{print $1}')

if [ "$HASH_CURRENT" != "$HASH_EXPECTED" ]; then
    echo "test_suite.py was modified!"
    exit 1
fi

# Run the test suite
python3 test_suite.py
```
