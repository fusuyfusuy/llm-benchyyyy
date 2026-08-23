import re

with open("bench/cli.py", "r") as f:
    text = f.read()

pattern = re.compile(r"<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> subagent-Runner-Architect-self-e6a4151e", re.DOTALL)
text = pattern.sub(r"\1\n\2", text)

with open("bench/cli.py", "w") as f:
    f.write(text)
