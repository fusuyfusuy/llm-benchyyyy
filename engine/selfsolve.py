from __future__ import annotations

import glob as globmod
import sys
from pathlib import Path

from . import sandbox as sandbox_mod
from . import task as task_mod
from .grading import exact_match as exact_grade
from .grading import executable as exec_grade
from .grading import judge as judge_grade
from .grading import spec as spec_mod


def _expected_path_for(task_path: Path) -> Path:
    parts = list(task_path.parts)
    idx = parts.index("tasks")
    parts[idx] = "expected"
    return Path(*parts)


def _solution_path_for(task_path: Path) -> Path:
    parts = list(task_path.parts)
    idx = parts.index("tasks")
    parts[idx] = "solutions"
    return Path(*parts).with_suffix(".sh")


def run_solution(task_path: Path, solution_path: Path) -> bool:
    t = task_mod.parse_task(task_path)
    spec = spec_mod.parse_grading_spec(_expected_path_for(task_path))
    script_content = solution_path.read_text()

    sb = sandbox_mod.create(t.seed_files, t.setup_script)
    try:
        proc = sandbox_mod.exec_in(sb, script_content)
        if spec.method == "exact-match":
            return exact_grade.grade(spec, proc.stdout).passed
        if spec.method == "judge-ensemble":
            return judge_grade.grade(spec, proc.stdout).passed
        result = exec_grade.grade(spec, sb)
        return result.passed
    finally:
        sandbox_mod.cleanup(sb)


def cmd_selfsolve(args) -> None:
    if getattr(args, "task", None):
        task_paths = [Path(args.task)]
    elif getattr(args, "task_glob", None):
        task_paths = [
            Path(p)
            for p in sorted(globmod.glob(args.task_glob, recursive=True))
            if not p.endswith("TEMPLATE.md")
        ]
    else:
        task_paths = [
            Path(p)
            for p in sorted(globmod.glob("tasks/**/*.md", recursive=True))
            if not p.endswith("TEMPLATE.md")
        ]

    passed_count = 0
    failed_count = 0
    tested_count = 0

    for task_path in task_paths:
        try:
            sol_path = _solution_path_for(task_path)
        except ValueError:
            continue

        if not sol_path.exists():
            continue

        tested_count += 1
        try:
            passed = run_solution(task_path, sol_path)
        except Exception as e:
            print(f"{task_path} -> FAIL ({type(e).__name__}: {e})")
            failed_count += 1
            continue

        if passed:
            print(f"{task_path} -> PASS")
            passed_count += 1
        else:
            print(f"{task_path} -> FAIL")
            failed_count += 1

    if tested_count == 0:
        print("No solutions found to test.")
        return

    print(f"\nSelf-solve results: {passed_count}/{tested_count} passed")
    if failed_count > 0:
        sys.exit(1)
