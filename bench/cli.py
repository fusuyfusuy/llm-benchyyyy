from __future__ import annotations

import argparse
import glob as globmod
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import pricing
from . import results as results_mod
from . import report as report_mod
from . import sandbox as sandbox_mod
from . import selfsolve as selfsolve_mod
from . import task as task_mod
from .grading import exact_match as exact_grade
from .grading import executable as exec_grade
from .grading import judge as judge_grade
from .grading import spec as spec_mod
from .harness import cli_adapter
from .harness import configs as harness_configs
from .harness import raw_api

DEFAULT_MODEL = "claude-sonnet-5"
TOOL_ACCESS = "read+write+bash"

# Grader registry: method name -> grade(spec, sb, response_text) -> passed.
GRADERS = {
    "unit-test": lambda spec, sb, text: exec_grade.grade(spec, sb).passed,
    "state-check": lambda spec, sb, text: exec_grade.grade(spec, sb).passed,
    "exact-match": lambda spec, sb, text: exact_grade.grade(spec, text).passed,
    "judge-ensemble": lambda spec, sb, text: judge_grade.grade(spec, text).passed,
}


def _expected_path_for(task_path: Path) -> Path:
    parts = list(task_path.parts)
    idx = parts.index("tasks")
    parts[idx] = "expected"
    return Path(*parts)


def run_one(task_path: Path, harness: str, model: str, trial_number: int) -> results_mod.RunRecord:
    t = task_mod.parse_task(task_path)
    spec = spec_mod.parse_grading_spec(_expected_path_for(task_path))

    sb = sandbox_mod.create(t.seed_files, t.setup_script)
    try:
        if harness == "raw-api":
            hr = raw_api.run(sb, t.instruction, model)
            response_text = hr.response_text
            input_tokens = hr.input_tokens
            output_tokens = hr.output_tokens
            tool_call_count = hr.tool_call_count
            wall_clock = hr.wall_clock_seconds
            cost = pricing.cost_usd(model, input_tokens, output_tokens)
            harness_version = "raw-api"
        else:
            config = harness_configs.REGISTRY[harness]
            hr = cli_adapter.run(config, sb, t.instruction, model=model)
            response_text = hr.response_text
            input_tokens = hr.input_tokens
            output_tokens = hr.output_tokens
            tool_call_count = hr.tool_call_count
            wall_clock = hr.wall_clock_seconds
            cost = hr.cost_usd
            if cost is None and model in pricing.PRICING_PER_MTOK:
                cost = pricing.cost_usd(model, input_tokens, output_tokens)
            harness_version = cli_adapter.harness_version(config)

        if spec.method not in GRADERS:
            raise ValueError(f"unknown grading method {spec.method}")
        passed = GRADERS[spec.method](spec, sb, response_text)
    finally:
        sandbox_mod.cleanup(sb)

    record = results_mod.RunRecord(
        task_id=t.id,
        model=model,
        harness=harness,
        harness_version=harness_version,
        tool_access=TOOL_ACCESS,
        scaffold_notes="",
        trial_number=trial_number,
        result="pass" if passed else "fail",
        grading_method=spec.method,
        constraint_violations="",
        wall_clock_seconds=wall_clock,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=None,
        cost_usd=cost,
        tool_call_count=tool_call_count,
    )
    results_mod.append(record)
    return record


def _collect_task_paths(args) -> list[Path]:
    paths = []
    if args.task:
        paths.append(Path(args.task))
    if args.task_glob:
        paths += [
            Path(p) for p in sorted(globmod.glob(args.task_glob, recursive=True))
            if not p.endswith("TEMPLATE.md")
        ]
    return paths


def cmd_run(args) -> None:
    if args.judge_harness:
        judge_grade.JUDGE_HARNESS = args.judge_harness
    if args.judge_model:
        judge_grade.JUDGE_MODEL = args.judge_model
    # Each (task, trial) pair owns an isolated tempdir + container, so trials
    # run in threads; results_mod.append is a single-line file append per call.
    pairs = [
        (task_path, trial)
        for task_path in _collect_task_paths(args)
        for trial in range(1, args.trials + 1)
    ]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(run_one, task_path, args.harness, args.model, trial): (task_path, trial)
            for task_path, trial in pairs
        }
        for fut in as_completed(futures):
            task_path, trial = futures[fut]
            try:
                record = fut.result()
            except Exception as e:  # noqa: BLE001 - one bad run must not kill the batch
                print(
                    f"{task_path} trial={trial} harness={args.harness} model={args.model}"
                    f" -> ERROR: {type(e).__name__}: {e}"
                )
                continue
            print(
                f"{task_path} trial={trial} harness={args.harness} model={args.model}"
                f" -> {record.result}"
            )


def cmd_report(_args) -> None:
    print(report_mod.write_report())



def cmd_verify(args) -> None:
    print(f"Verifying harness={args.harness} model={args.model}...")
    from .sandbox import create
    from .harness import raw_api, cli_adapter
    from .harness import configs as harness_configs
    
    sb = create([], None)
    try:
        if args.harness == "raw-api":
            raw_api.run(sb, "Say OK", args.model)
        else:
            conf = harness_configs.REGISTRY[args.harness]
            res = cli_adapter.run(conf, sb, "Say OK", args.model)
            if res.raw_exit_code != 0:
                raise RuntimeError(f"Harness exited with code {res.raw_exit_code}. Output: {res.response_text}")
        print("✅ Verification passed.")
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bench")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="run a task against a model+harness")
    run_p.add_argument("--task", help="path to a single task .md file")
    run_p.add_argument("--task-glob", help="glob of task .md files, e.g. 'tasks/**/*.md'")
    run_p.add_argument("--harness", required=True, choices=["raw-api", *harness_configs.REGISTRY.keys()])
    run_p.add_argument("--model", default=DEFAULT_MODEL)
    run_p.add_argument("--trials", type=int, default=1)
    run_p.add_argument("--jobs", type=int, default=4, help="parallel task-trial runs")
    run_p.add_argument(
        "--judge-harness",
        default=judge_grade.JUDGE_HARNESS,
        choices=[*harness_configs.REGISTRY.keys()],
        help="CLI harness that casts judge-ensemble votes (uses its existing login, no API key)",
    )
    run_p.add_argument(
        "--judge-model",
        default=judge_grade.JUDGE_MODEL or "",
        help="provider-scoped model for judge votes (e.g. anthropic/claude-opus-5); "
        "default: the judge harness's own default model",
    )
    run_p.set_defaults(func=cmd_run)

    report_p = sub.add_parser("report", help="aggregate results/runs.jsonl into a report")
    report_p.set_defaults(func=cmd_report)

    
    verify_p = sub.add_parser("verify", help="verify a harness/model pair works before running a full suite")
    verify_p.add_argument("--harness", required=True, choices=["raw-api"] + list(harness_configs.REGISTRY.keys()))
    verify_p.add_argument("--model", required=True, help="Model identifier to test")
    verify_p.set_defaults(func=cmd_verify)
    selfsolve_p = sub.add_parser("self-solve", help="run golden solutions against task grading rubrics")
    selfsolve_p.add_argument("--task", help="path to a single task .md file")
    selfsolve_p.add_argument("--task-glob", help="glob of task .md files, e.g. 'tasks/**/*.md'")
    selfsolve_p.set_defaults(func=selfsolve_mod.cmd_selfsolve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run" and not args.task and not args.task_glob:
        parser.error("run requires --task or --task-glob")
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
