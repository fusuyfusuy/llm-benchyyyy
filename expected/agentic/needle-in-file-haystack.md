# needle-in-file-haystack — expected

**grading method:** executable state check

## Pass criteria
The file `solution.txt` must exist and contain exactly `SECRET_FLAG={0xDEADBEEF_9912}`.

## Check
```bash
if [ ! -f "solution.txt" ]; then
    echo "solution.txt not found"
    exit 1
fi

CONTENT=$(cat solution.txt | tr -d '\n' | tr -d '\r')
if [ "$CONTENT" != "SECRET_FLAG={0xDEADBEEF_9912}" ]; then
    echo "Incorrect content: $CONTENT"
    exit 1
fi
exit 0
```
