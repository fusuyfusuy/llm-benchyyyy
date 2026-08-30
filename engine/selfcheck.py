"""One runnable check for the non-trivial parsing/grading/report logic.

No pytest dependency for the engine package itself (pytest lives inside the
task sandbox for the coding tasks it grades) -- plain asserts, run with:
    python -m engine.selfcheck
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
        {"task_id": "t1", "model": "m1", "harness": "h1", "harness_version": "v1",
         "tool_access": "a", "trial_number": 1,
         "result": "pass", "cost_usd": 1.0, "wall_clock_seconds": 10.0},
        {"task_id": "t1", "model": "m1", "harness": "h1", "harness_version": "v1",
         "tool_access": "a", "trial_number": 2,
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


def check_score_grouping() -> None:
    """The comparability contract: score groups on the 5 GROUP_KEYS, dedupes
    repeated trial_number (keep last), and flags <3-trial groups."""
    from . import score as score_mod

    assert score_mod.GROUP_KEYS is report_mod.GROUP_KEYS  # one shared constant
    base = {"task_id": "fix-off-by-one-pagination", "model": "m", "harness": "h",
            "harness_version": "1.0", "tool_access": "a", "trial_number": 1,
            "result": "pass"}
    rows = [{**base, "trial_number": 1}, {**base, "trial_number": 2},
            {**base, "trial_number": 3},
            # re-run of trial 1 (a correction): keep last, group stays 3 trials
            {**base, "trial_number": 1, "result": "fail"},
            # version bump: NOT pooled with the 1.0 trials (F-07)
            {**base, "harness_version": "2.0", "result": "fail"},
            # different tool_access: separate group too, single trial -> flagged
            {**base, "trial_number": 1, "tool_access": "read-only"}]
    groups = {(g["harness"], g["harness_version"], g["tool_access"]): g
              for g in score_mod.score_groups(rows)}
    assert len(groups) == 3, groups
    g1 = groups[("h", "1.0", "a")]
    assert g1["trials"] == 3 and g1["passes"] == 2, g1
    assert abs(g1["points"] - (2 / 3) * 5.0) < 1e-9 and not g1["under_trialed"]
    g2 = groups[("h", "2.0", "a")]
    assert g2["trials"] == 1 and g2["under_trialed"] and g2["pass_rate"] == 0.0
    g3 = groups[("h", "1.0", "read-only")]
    assert g3["trials"] == 1 and g3["under_trialed"]


def check_pricing_canonical_and_warn() -> None:
    """Canonical undated keys resolve; dated legacy ids alias; unknown ids
    warn exactly once and never claim to be priced silently."""
    import contextlib
    import io

    from . import pricing

    assert pricing.cost_usd("claude-haiku-4-5", 1_000_000, 0) == 0.8
    assert pricing.cost_usd("claude-haiku-4-5-20251001", 1_000_000, 0) == 0.8
    assert pricing.known("claude-haiku-4-5-20251001")
    assert not pricing.known("gemini-3.7-flash")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        v1 = pricing.cost_usd("claude-opus-9", 1_000_000, 0)  # unknown -> default tier + WARN
        v2 = pricing.cost_usd("claude-opus-9", 1_000_000, 0)
    assert v1 == v2 == 3.0  # default Sonnet-rate input (best-effort, now loud)
    assert err.getvalue().count("no entry for claude-opus-9") == 1, err.getvalue()


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


def check_selfsolve_path_mapping() -> None:
    from . import selfsolve
    task_path = REPO_ROOT / "tasks" / "coding" / "fix-off-by-one-pagination.md"
    exp_path = selfsolve._expected_path_for(task_path)
    assert exp_path == REPO_ROOT / "expected" / "coding" / "fix-off-by-one-pagination.md"
    sol_path = selfsolve._solution_path_for(task_path)
    assert sol_path == REPO_ROOT / "solutions" / "coding" / "fix-off-by-one-pagination.sh"


def check_engine_cli_and_package_contract() -> None:
    from . import cli as cli_mod
    parser = cli_mod.build_parser()
    assert parser.prog == "engine"
    # Ensure all expected subcommands are wired
    subparser_actions = [
        action for action in parser._actions 
        if isinstance(action, cli_mod.argparse._SubParsersAction)
    ]
    assert len(subparser_actions) == 1
    subcommands = set(subparser_actions[0].choices.keys())
    assert {"run", "report", "score", "verify", "self-solve"}.issubset(subcommands), subcommands


def main() -> None:
    check_markdown_helpers()
    check_task_and_spec_parse_real_files()
    check_exact_match()
    check_raw_api_path_containment()
    check_run_record_schema_version()
    check_report_aggregation()
    check_score_grouping()
    check_pricing_canonical_and_warn()
    check_all_task_expected_pairs_parse()
    check_selfsolve_path_mapping()
    check_engine_cli_and_package_contract()
    print("selfcheck OK")


if __name__ == "__main__":
    main()

