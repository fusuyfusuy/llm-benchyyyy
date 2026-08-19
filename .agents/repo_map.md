# Repository Map

44 files · 1249 lines of parsed code · ranked by import in-degree + 90d churn + entry points

## Entry points

- `bench/cli.py`
- `bench/__main__.py`

## Core modules

`bench/sandbox.py` · 104 ln · ← cli, cli_adapter, executable, raw_api · 1 commit/90d
  "Docker sandbox: a bind-mounted temp dir + `docker run --rm` per command."
  :33   class Sandbox
  :38   create(seed_files: list[task_mod.SeedFile], setup_script: str | None, env: dict | None=…
  :56   write_file_to(base: Path, rel_path: str, content: str) -> None
  :62   write_file(sb: Sandbox, rel_path: str, content: str) -> None
  :66   _docker_run_args(sb: Sandbox, extra_env: dict | None=None) -> list[str]
  :88   run(sb: Sandbox, command: str, extra_env: dict | None=None, timeout: int=600) -> subpro…
  :98   exec_in(sb: Sandbox, command: str, timeout: int=300) -> subprocess.CompletedProcess
  :102  cleanup(sb: Sandbox) -> None

`bench/grading/spec.py` · 95 ln · ← exact_match, executable, judge · 1 commit/90d
  :15   class GradingSpec
  :28   _classify_method(method_raw: str, path: Path) -> str
  :41   parse_grading_spec(path: Path) -> GradingSpec

`bench/markdown.py` · 73 ln · ← selfcheck, spec, task · 1 commit/90d
  "Shared parsing helpers for the task/expected markdown convention."
  :15   extract_section(text: str, heading: str) -> str | None
  :29   extract_bold_field(text: str, label: str) -> str | None
  :41   extract_fenced_blocks(text: str) -> list[tuple[str, str]]
  :46   extract_seed_files(text: str) -> list[tuple[str, str]]
  :67   first_bash_block(text: str) -> str | None

`bench/task.py` · 52 ln · ← cli, sandbox, selfcheck · 1 commit/90d
  :10   class SeedFile
  :16   class Task
  :27   parse_task(path: Path) -> Task

`bench/cli.py` · 148 ln · ← __main__ · 1 commit/90d · entry point
  :25   _expected_path_for(task_path: Path) -> Path
  :32   run_one(task_path: Path, harness: str, model: str, trial_number: int) -> results_mod.Ru…
  :96   _collect_task_paths(args) -> list[Path]
  :108  cmd_run(args) -> None
  :115  cmd_report(_args) -> None
  :119  build_parser() -> argparse.ArgumentParser
  :137  main(argv: list[str] | None=None) -> int

`bench/report.py` · 72 ln · ← cli, selfcheck · 1 commit/90d
  :21   aggregate(rows: list[dict]) -> list[dict]
  :49   format_table(rows: list[dict]) -> str
  :62   write_report(out_path: Path=Path('results/report.md'), results_path: Path=results_mod.R…

`bench/results.py` · 43 ln · ← cli, report · 1 commit/90d
  :11   class RunRecord
  :32   append(record: RunRecord, path: Path=RESULTS_PATH) -> None
  :38   load_all(path: Path=RESULTS_PATH) -> list[dict]

`bench/grading/__init__.py` · 1 ln · ← cli, selfcheck · 1 commit/90d

`bench/__main__.py` · 7 ln · 1 commit/90d · entry point

## Supporting files

`bench/harness/configs.py` · 104 ln · ← cli_adapter · 1 commit/90d · :24 class HarnessConfig

`bench/pricing.py` · 23 ln · ← cli · 1 commit/90d · :18 cost_usd

`bench/grading/exact_match.py` · 28 ln · 1 commit/90d · :12 class ExactMatchResult · :18 grade

`bench/grading/executable.py` · 29 ln · 1 commit/90d · :10 class ExecResult · :17 grade

`bench/grading/judge.py` · 111 ln · 1 commit/90d · :57 class JudgeVerdict · :65 _client · :71 _call_judge · :85 grade

`bench/harness/cli_adapter.py` · 111 ln · 1 commit/90d · :18 class HarnessRunResult · :28 _dig · :40 _parse_jsonl · :55 _find_last · :65 _build_argv · :72 run

`bench/harness/raw_api.py` · 122 ln · 1 commit/90d · :53 class RawApiResult · :61 _execute_tool · :77 run

`bench/selfcheck.py` · 124 ln · 1 commit/90d · :20 check_markdown_helpers · :35 check_task_and_spec_parse_real_files · :69 check_exact_match · :81 check_report_aggregation · :98 check_all_task_expected_pairs_parse · :113 main

## Other files

- `.` — 5 files ((no ext), .md, .toml)
- `.agents/` — 4 files (.jsonl, .md)
- `bench/` — `__init__.py`
- `bench/harness/` — `__init__.py`
- `docker/` — `harness-base.Dockerfile`
- `expected/` — `grading-methodology.md`
- `expected/agentic/` — `recover-from-wrong-command.md`, `policy-adherence-under-tool-failure.md`
- `expected/coding/` — `add-csv-export-endpoint.md`, `fix-off-by-one-pagination.md`
- `expected/reasoning/` — `multi-step-inventory-word-problem.md`, `underspecified-feature-request.md`
- `results/` — `.gitkeep`
- `tasks/agentic/` — `policy-adherence-under-tool-failure.md`, `recover-from-wrong-command.md`
- `tasks/coding/` — `add-csv-export-endpoint.md`, `fix-off-by-one-pagination.md`
- `tasks/reasoning/` — `multi-step-inventory-word-problem.md`, `underspecified-feature-request.md`
- `tasks/team-workflows/` — `TEMPLATE.md`

_Detailed 17 of 44 files; 27 collapsed above._