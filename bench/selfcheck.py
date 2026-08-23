"""One runnable check for the non-trivial parsing/grading/report logic.

No pytest dependency for the bench package itself (pytest lives inside the
task sandbox for the coding tasks it grades) -- plain asserts, run with:
    python -m bench.selfcheck
"""
from __future__ import annotations

from pathlib import Path

from . import markdown as md
from . import report as report_mod
from . import results as results_mod
from . import sandbox as sandbox_mod
from . import task as task_mod
from .grading import exact_match as exact_grade
from .grading import spec as spec_mod

REPO_ROOT = Path(__file__).resolve().parent.parent


def check_markdown_helpers() -> None:
    # Bind sections to locals first: extract_section returns str | None, and
    # chained .strip() on the call result doesn't narrow.
    text = "## A\nfoo\nbar\n## B\nbaz\n"
    sec_a = md.extract_section(text, "A")
    sec_b = md.extract_section(text, "B")
    assert sec_a is not None and sec_a.strip() == "foo\nbar"
    assert sec_b is not None and sec_b.strip() == "baz"
    assert md.extract_section(text, "C") is None

    bold = "**dimension(s):** raw model, coding harness\n**difficulty tier:** easy\n"
    assert md.extract_bold_field(bold, "dimension(s)") == "raw model, coding harness"
    assert md.extract_bold_field(bold, "difficulty tier") == "easy"

    section = "```python\n# foo.py\nprint(1)\n```\n\n```python\n# empty.py\n```\n"
    seeds = md.extract_seed_files(section)
    assert seeds == [("foo.py", "print(1)\n")], seeds  # empty.py skipped: nothing to seed


def check_task_and_spec_parse_real_files() -> None:
    task_path = REPO_ROOT / "tasks" / "coding" / "fix-off-by-one-pagination.md"
    t = task_mod.parse_task(task_path)
    assert t.id == "fix-off-by-one-pagination"
    assert t.difficulty == "easy"
    assert any(f.path == "paginate.py" for f in t.seed_files), t.seed_files
    assert not any(f.path == "test_paginate.py" for f in t.seed_files), "held-out file must not be seeded"

    expected_path = REPO_ROOT / "expected" / "coding" / "fix-off-by-one-pagination.md"
    spec = spec_mod.parse_grading_spec(expected_path)
    assert spec.method == "unit-test"
    assert spec.check_script == "pytest -q test_paginate.py"
    assert any(p == "test_paginate.py" for p, _ in spec.seed_files), spec.seed_files

    setup_task_path = REPO_ROOT / "tasks" / "agentic" / "recover-from-wrong-command.md"
    st = task_mod.parse_task(setup_task_path)
    assert st.setup_script and "chmod 0444" in st.setup_script

    state_check_expected = REPO_ROOT / "expected" / "agentic" / "recover-from-wrong-command.md"
    scspec = spec_mod.parse_grading_spec(state_check_expected)
    assert scspec.method == "state-check"
    assert scspec.check_script and "archive-early-jan.tar.gz" in scspec.check_script


def check_exact_match() -> None:
    exact_path = REPO_ROOT / "expected" / "reasoning" / "multi-step-inventory-word-problem.md"
    spec = spec_mod.parse_grading_spec(exact_path)
    assert spec.method == "exact-match"
    assert spec.expected_value == "368", spec.expected_value

    ok = exact_grade.grade(spec, "The warehouse has 368 units left. (480-120+150-130-12=368)")
    assert ok.passed
    bad = exact_grade.grade(spec, "380 units remain.")
    assert not bad.passed
    # Last number wins: given figures restated in prose must not be graded.
    preamble = exact_grade.grade(spec, "Starting from 480 units, after all movements 368 remain.")
    assert preamble.passed and preamble.extracted == "368"


def check_raw_api_path_containment() -> None:
    import tempfile

    from .harness import raw_api

    with tempfile.TemporaryDirectory() as tmp:
        sb = sandbox_mod.Sandbox(workdir=Path(tmp))
        outside = raw_api._execute_tool(sb, "read_file", {"path": "/etc/hostname"})
        assert "error reading" in outside, outside
        traversal = raw_api._execute_tool(sb, "write_file", {"path": "../escaped.txt", "content": "x"})
        assert "error writing" in traversal, traversal
        assert not (Path(tmp).parent / "escaped.txt").exists()
        inside = raw_api._execute_tool(sb, "write_file", {"path": "ok.txt", "content": "fine"})
        assert inside == "wrote ok.txt"
        assert (Path(tmp) / "ok.txt").read_text() == "fine"


def check_run_record_schema_version() -> None:
    from dataclasses import asdict

    from .results import RunRecord

    r = RunRecord(
        task_id="t", model="m", harness="h", harness_version="v", tool_access="a",
        scaffold_notes="", trial_number=1, result="pass", grading_method="unit-test",
        constraint_violations="", wall_clock_seconds=1.0,
        input_tokens=None, output_tokens=None, cached_tokens=None,
        cost_usd=None, tool_call_count=None,
    )
    assert asdict(r)["schema_version"] == 1


def check_report_aggregation() -> None:
    rows = [
        {"task_id": "t1", "model": "m1", "harness": "h1", "tool_access": "a",
         "result": "pass", "cost_usd": 1.0, "wall_clock_seconds": 10.0},
        {"task_id": "t1", "model": "m1", "harness": "h1", "tool_access": "a",
         "result": "fail", "cost_usd": 1.0, "wall_clock_seconds": 10.0},
    ]
    agg = report_mod.aggregate(rows)
    assert len(agg) == 1
    row = agg[0]
    assert row["trials"] == 2
    assert row["pass_rate"] == 0.5
    assert row["cost_per_success_usd"] == 2.0  # (1.0 + 1.0) / 1 pass
    table = report_mod.format_table(agg)
    assert "t1" in table and "pass_rate" in table
    assert row["cost_per_trial_usd"] == 1.0 and row["time_per_trial_seconds"] == 10.0


def check_all_task_expected_pairs_parse() -> None:
    for task_path in sorted((REPO_ROOT / "tasks").rglob("*.md")):
        if task_path.name == "TEMPLATE.md":
            continue
        t = task_mod.parse_task(task_path)
        assert t.id, task_path
        assert t.instruction, f"{task_path}: empty instruction"

        parts = list(task_path.parts)
        parts[parts.index("tasks")] = "expected"
        expected_path = Path(*parts)
        assert expected_path.exists(), f"missing expected file for {task_path}"
        spec_mod.parse_grading_spec(expected_path)


def main() -> None:
    check_markdown_helpers()
    check_task_and_spec_parse_real_files()
    check_exact_match()
    check_raw_api_path_containment()
    check_run_record_schema_version()
    check_report_aggregation()
    check_all_task_expected_pairs_parse()
    print("selfcheck OK")


if __name__ == "__main__":
    main()
