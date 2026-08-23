import re

with open("bench/selfcheck.py", "r") as f:
    text = f.read()

# Replace the conflict block
pattern = re.compile(r"<<<<<<< HEAD\n=======\n.*?(def check_selfsolve_path_mapping\(\) -> None:.*?)\n>>>>>>> subagent-Runner-Architect-self-e6a4151e", re.DOTALL)
text = pattern.sub(r"\1", text)

with open("bench/selfcheck.py", "w") as f:
    f.write(text)
