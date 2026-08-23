# needle-in-file-haystack

**dimension(s):** tool-use-agentic
**difficulty tier:** medium

## Instruction

We have lost a cryptographic secret in our logging directory.
The directory `logs/` contains 500 automatically generated text files spread across multiple nested subdirectories.
Exactly one of these files contains a string formatted as `SECRET_FLAG={...}`.
Find the secret flag and write ONLY the full `SECRET_FLAG={...}` string into a new file named `solution.txt` in the root directory.

## Setup

```bash
# Setup
mkdir -p logs
for i in {1..50}; do
    mkdir -p logs/dir_$i
    for j in {1..10}; do
        head -c 100 /dev/urandom | base64 > logs/dir_$i/file_$j.log
    done
done
# Insert the needle
echo "some random noise SECRET_FLAG={0xDEADBEEF_9912} and more noise" >> logs/dir_37/file_4.log
```

## Constraints
- Output must be exactly in `solution.txt`.
- Output must be exactly the string starting with `SECRET_FLAG={` and ending with `}`.
