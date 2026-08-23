import os, glob, re

print("| Category | Task | Difficulty | Grading Method | Brief |\n|---|---|---|---|---|")

for cat in ["coding", "reasoning", "agentic"]:
    for filepath in sorted(glob.glob(f"tasks/{cat}/*.md")):
        with open(filepath) as f:
            content = f.read()
        name = os.path.basename(filepath)
        
        diff_match = re.search(r"\*\*difficulty tier:\*\*\s*(.+)", content)
        diff = diff_match.group(1).strip() if diff_match else "?"
        
        exp_path = f"expected/{cat}/{name}"
        grading = "?"
        if os.path.exists(exp_path):
            with open(exp_path) as ef:
                exp_content = ef.read()
                g_match = re.search(r"\*\*grading method:\*\*\s*([^\n]+)", exp_content)
                if g_match:
                    grading = g_match.group(1).split("—")[0].strip()
        
        # Brief description (first sentence of instruction)
        instr_match = re.search(r"## Instruction\n+(.+?)(?:\n|\. )", content, re.DOTALL)
        brief = "..."
        if instr_match:
            brief = instr_match.group(1).replace('\n', ' ')[:80] + "..."
            
        print(f"| {cat} | {name.replace('.md', '')} | {diff} | {grading} | {brief} |")

