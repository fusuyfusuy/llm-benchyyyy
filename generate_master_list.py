import sys
with open("/tmp/agy-models.txt") as f:
    agy_lines = f.readlines()
with open("/tmp/pi-models.txt") as f:
    pi_lines = f.readlines()

agy_models = []
for line in agy_lines:
    parts = line.strip().split()
    if parts:
        if not parts[0].startswith("\u280b") and "Fetching" not in parts[0]:
            agy_models.append(parts[0])

pi_models = []
for line in pi_lines:
    parts = line.strip().split()
    if len(parts) >= 2:
        if parts[0] in ["openrouter", "anthropic", "google", "openai"]:
            pi_models.append(parts[1])

with open("/home/devhax/.gemini/antigravity-cli/brain/6dcd4e6f-1d91-4612-9974-0b0771957542/master-model-list.md", "w") as out:
    out.write("# Master Model List\n\n")
    out.write("## 1. Antigravity Models (`agy models`)\n")
    for m in agy_models:
        out.write(f"- `{m}`\n")
    
    out.write("\n## 2. Pi Agent Models (`pi --list-models`)\n")
    for m in sorted(list(set(pi_models))):
        out.write(f"- `{m}`\n")
    
    out.write("\n## 3. Claude Code Models\n")
    out.write("- `claude-sonnet-5`\n")
    out.write("- `claude-opus-5`\n")
    out.write("- `claude-fable-5`\n")
