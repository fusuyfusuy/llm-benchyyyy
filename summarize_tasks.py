"""One-row-per-task summary table over tasks/ + expected/ metadata.

Reads the markdown convention through engine.markdown (the shared parser) instead
of a second hand-rolled copy of its regexes (SEAM m7). Output format unchanged.
"""
import glob
import os
import re
from pathlib import Path

from engine.markdown import extract_bold_field, extract_section

ROOT = Path(__file__).resolve().parent

print("| Category | Task | Difficulty | Grading Method | Brief |\n|---|---|---|---|---|")

for cat in ["coding", "reasoning", "agentic"]:
    for filepath in sorted(glob.glob(str(ROOT / f"tasks/{cat}/*.md"))):
        name = os.path.basename(filepath)
        content = Path(filepath).read_text()

        diff = extract_bold_field(content, "difficulty tier") or "?"

        grading = "?"
        exp_path = ROOT / "expected" / cat / name
        if exp_path.exists():
            method = extract_bold_field(exp_path.read_text(), "grading method")
            if method:
                grading = method.split("—")[0].strip()

        # First sentence of the instruction, truncated — prose heuristic, not
        # part of the shared markdown convention.
        instruction = extract_section(content, "Instruction") or ""
        sent = re.search(r"(.+?)(?:\n|\. )", instruction.lstrip("\n"), re.DOTALL)
        brief = sent.group(1).replace("\n", " ")[:80] + "..." if sent else "..."

        print(f"| {cat} | {name.replace('.md', '')} | {diff} | {grading} | {brief} |")
