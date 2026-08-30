# Repository Map

159 files · 10486 lines of parsed code · ranked by PageRank+in-degree + 90d churn + entry points

## Entry points

- `checkers/opencode_cost_benefit_analyzer.py`
- `engine/cli.py`
- `checkers/free_model_ranker.py`
- `checkers/llm_benchmark_aggregator.py`
- `checkers/stealth_model_detector.py`
- `checkers/test_opencode_cost_benefit_analyzer.py`
- `engine/__main__.py`

## Core modules

`checkers/benchmark_common.py` · 1558 ln · ← free_model_ranker, llm_benchmark_aggregator, opencode_cost_benefit_analyzer, stealth_model_detector, +1 · 2 commits/90d
  "benchmark_common.py — Shared mathematical scoring, parsers, normalization,"
  :63   norm_id(s: str) -> str
  :73   norm_model_slug(s: str) -> str
  :91   _id_tokens(norm: str) -> list[str]
  :98   variant_conflict(a_norm: str, b_norm: str) -> bool
  :118  atomic_write_text(path, text: str) -> None
  :130  _safe_float(val, default=None)
  :142  _safe_int(val, default=None)
  :154  _safe_int_round(val, default=None)
  :164  parse_price(s: str) -> float | None
  :177  pick_latest_raw(raw_dir: pathlib.Path, name_part: str) -> pathlib.Path | None
  :186  get_z_scores(values: list) -> list[float]
  :198  compute_capability_q(cz: float) -> float
  ... +39 more symbols

`engine/sandbox.py` · 227 ln · ← cli, cli_adapter, executable, raw_api, +2 · 1 commit/90d
  "Docker sandbox: a bind-mounted temp dir + `docker run --rm` per command."
  :43   class Sandbox
  :49   _make_pi_overlay() -> Path | None
  :72   create(seed_files: list[task_mod.SeedFile], setup_script: str | None, env: dict | None=…
  :90   _contained_target(base: Path, rel_path: str) -> Path
  :114  write_file_to(base: Path, rel_path: str, content: str) -> None
  :124  write_file(sb: Sandbox, rel_path: str, content: str) -> None
  :128  _docker_run_args(sb: Sandbox, extra_env: dict | None=None, network: bool=True) -> list[…
  :168  _kill_timed_out_container(cidfile: Path) -> None
  :191  run(sb: Sandbox, command: str, extra_env: dict | None=None, timeout: int=600, network: …
  :217  exec_in(sb: Sandbox, command: str, timeout: int=300, network: bool=True) -> subprocess.…
  :223  cleanup(sb: Sandbox) -> None

`engine/markdown.py` · 78 ln · ← selfcheck, spec, task · 1 commit/90d
  "Shared parsing helpers for the task/expected markdown convention."
  :15   extract_section(text: str, heading: str) -> str | None
  :29   extract_bold_field(text: str, label: str) -> str | None
  :41   extract_fenced_blocks(text: str) -> list[tuple[str, str]]
  :51   extract_seed_files(text: str) -> list[tuple[str, str]]
  :72   first_bash_block(text: str) -> str | None

`engine/task.py` · 57 ln · ← cli, sandbox, selfcheck, selfsolve · 1 commit/90d
  :10   class SeedFile
  :16   class Task
  :27   parse_task(path: Path) -> Task

`checkers/opencode_cost_benefit_analyzer.py` · 2300 ln · ← free_model_ranker, stealth_model_detector, test_opencode_cost_benefit_analyzer · 2 commits/90d · entry point
  "ocgo_check.py — OpenCode Go live checker"
  :57   pick_latest_raw(name_part)
  :156  log(msg, verbose=False)
  :161  fetch(url, timeout=20, verbose=False)
  :175  parse_ocgo_docs(html, verbose=False)
  :307  model_to_id(raw)
  :381  norm_id(s)
  :385  parse_aa(html, verbose=False)
  :487  parse_openrouter(data_json, verbose=False)
  :504  find_aa_for_ocgo(ocgo_id, aa_map)
  :528  find_lm_for_ocgo(ocgo_id, lm_map)
  :544  find_or_for_ocgo(ocgo_id, or_map)
  :561  parse_livebench(csv_text, categories_json=None, verbose=False)
  ... +18 more symbols

`engine/results.py` · 45 ln · ← cli, report, selfcheck · 1 commit/90d
  :11   class RunRecord
  :34   append(record: RunRecord, path: Path=RESULTS_PATH) -> None
  :40   load_all(path: Path=RESULTS_PATH) -> list[dict]

`engine/cli.py` · 241 ln · ← __main__, selfcheck · 1 commit/90d · entry point
  :34   _expected_path_for(task_path: Path) -> Path
  :41   run_one(task_path: Path, harness: str, model: str, trial_number: int) -> results_mod.Ru…
  :106  _collect_task_paths(args) -> list[Path]
  :118  cmd_run(args) -> int
  :158  cmd_report(_args) -> None
  :163  cmd_verify(args) -> None
  :184  build_parser() -> argparse.ArgumentParser
  :218  main(argv: list[str] | None=None) -> int

`engine/report.py` · 115 ln · ← cli, score, selfcheck · 1 commit/90d
  :29   aggregate(rows: list[dict]) -> list[dict]
  :80   _fmt_cost(v: float | None, r: dict) -> str
  :89   format_table(rows: list[dict]) -> str
  :105  write_report(out_path: Path=Path('results/report.md'), results_path: Path=results_mod.R…

`checkers/free_model_ranker.py` · 788 ln · ← test_free_model_ranker · 2 commits/90d · entry point
  "free_models_check.py — Free models (OpenRouter + OpenCode) ranked by composite intelligence"
  :66   is_free_model(rec)
  :82   pick_latest_raw(name_part: str) -> pathlib.Path | None
  :87   fetch_or_load_cached_json(api_url: str, snapshot_prefix: str, offline: bool=False, do_f…
  :127  render_html(rows, n_aa, n_lm, added_ids=None, removed_models=None)
  :227  render_cli_table(rows_sorted, color=True, is_slim=False, is_wide=False, n_aa=0, n_lm=0,…
  :467  main()

`checkers/llm_benchmark_aggregator.py` · 1995 ln · ← test_llm_benchmark_aggregator · 2 commits/90d · entry point
  "benchmarks_check.py — Multi-source benchmark consolidation across subscription pools"
  :760  arc_base_name(s)
  :769  find_livebench(model_id_or_dict, live_map)
  :802  find_lmarena(model_id_or_dict, lm_map)
  :834  find_aa(model_id_or_dict, aa_map)
  :866  find_arc(model_id_or_dict, arc_map)
  :897  fetch_url(url, timeout=15)
  :907  load_livebench_data(verbose=False, fetch=False)
  :951  load_lmarena_data(verbose=False, fetch=False)
  :979  load_aa_data(verbose=False, fetch=False)
  :1007 newest_snapshot_age_h(pattern)
  :1016 cache_staleness_note()
  :1035 load_arc_data(verbose=False, fetch=False)
  ... +9 more symbols

`checkers/stealth_model_detector.py` · 516 ln · ← test_stealth_model_detector · 2 commits/90d · entry point
  "stealth_models_check.py — OpenRouter stealth models (stealth/ namespace) ranked by composite intelli"
  :62   pick_latest_raw(name_part)
  :67   created_date(rec)
  :76   render_html(rows, n_aa, n_lm)
  :125  render_cli_table(rows_sorted, color=True, is_slim=False, n_aa=0, n_lm=0)
  :291  main()

`engine/grading/__init__.py` · 1 ln · ← cli, selfcheck, selfsolve · 1 commit/90d

`engine/grading/spec.py` · 76 ln · ← exact_match, executable · 1 commit/90d
  :13   class GradingSpec
  :23   _classify_method(method_raw: str, path: Path) -> str
  :39   parse_grading_spec(path: Path) -> GradingSpec

`engine/selfsolve.py` · 95 ln · ← cli, selfcheck · 1 commit/90d
  :14   _expected_path_for(task_path: Path) -> Path
  :21   _solution_path_for(task_path: Path) -> Path
  :28   run_solution(task_path: Path, solution_path: Path) -> bool
  :44   cmd_selfsolve(args) -> None

`engine/harness/__init__.py` · 1 ln · ← cli, selfcheck · 1 commit/90d

`checkers/test_opencode_cost_benefit_analyzer.py` · 247 ln · 2 commits/90d · entry point
  :13   class TestOcgoCheck
  :14     test_fallback_pricing_catalog()
  :21     test_cost_computation()
  :28     test_snapshot_discovery()
  :36     test_offline_parsing()
  :57     test_livebench_snapshot()
  :68     test_role_recommendations_in_ocheck()
  :92     test_catalog_diff_logic()
  :128    test_render_cli_table_diff_colors()
  :184    test_render_html_diff()
  :209    test_render_limits_table()

`engine/__main__.py` · 7 ln · 1 commit/90d · entry point

## Supporting files

`engine/harness/configs.py` · 118 ln · ← cli_adapter · 1 commit/90d · :17 class HarnessConfig

`engine/pricing.py` · 50 ln · ← cli · 1 commit/90d · :24 normalize · :29 known · :35 cost_usd

`engine/score.py` · 136 ln · ← cli · 1 commit/90d · :34 get_category · :41 group_trials · :53 score_groups · :74 main

`checkers/test_llm_benchmark_aggregator.py` · 442 ln · 2 commits/90d · :20 class TestBenchmarksCheck · :246 class TestBcheckArcAndCache · :355 class TestFetchPath

`checkers/test_stealth_model_detector.py` · 129 ln · 2 commits/90d · :16 class TestStealthModelDetector

`checkers/test_benchmark_common.py` · 370 ln · 1 commit/90d · :15 class TestBenchmarkCommon · :282 class TestVariantConflictMatcher · :309 class TestAtomicWriteAndBaseline · :348 class TestRequireDocsTag

`checkers/test_free_model_ranker.py` · 217 ln · 1 commit/90d · :14 class TestFreeModelRanker

`engine/grading/exact_match.py` · 31 ln · 1 commit/90d · :12 class ExactMatchResult · :18 grade

`engine/grading/executable.py` · 39 ln · 1 commit/90d · :10 class ExecResult · :17 grade

`engine/harness/cli_adapter.py` · 252 ln · 1 commit/90d · :22 class UsageExtractionError · :29 _require_extracted · :45 harness_version · :65 class HarnessRunResult · :75 _dig · :95 _parse_jsonl

`engine/harness/raw_api.py` · 135 ln · 1 commit/90d · :54 class RawApiResult · :62 _resolve_in_sandbox · :69 _execute_tool · :90 run

`engine/selfcheck.py` · 184 ln · 1 commit/90d · :22 check_markdown_helpers · :41 check_task_and_spec_parse_real_files · :65 check_exact_match · :80 check_raw_api_path_containment · :97 check_run_record_schema_version · :112 check_report_aggregation

## Other files

- `.` — 10 files ((no ext), .md, .py, .sh)
- `.agents/` — 4 files (.jsonl, .md)
- `checkers/` — `__init__.py`
- `docker/` — `harness-base.Dockerfile`
- `docs/` — `models.md`
- `docs/data/` — 4 files (.json)
- `docs/data/raw/` — 33 files (.csv, .html, .json)
- `docs/reports/` — 6 files (.html, .json, .md)
- `engine/` — `__init__.py`
- `expected/` — `grading-methodology.md`
- `expected/agentic/` — 6 files (.md)
- `expected/coding/` — 10 files (.md)
- `expected/reasoning/` — 4 files (.md)
- `results/` — `.gitkeep`
- `reviews/` — 6 files (.md)
- `solutions/agentic/` — 6 files (.sh)
- `solutions/coding/` — 10 files (.sh)
- `solutions/reasoning/` — 4 files (.sh)
- `tasks/agentic/` — 6 files (.md)
- `tasks/coding/` — 10 files (.md)
- `tasks/reasoning/` — 4 files (.md)
- `tasks/team-workflows/` — `TEMPLATE.md`

_Detailed 29 of 159 files; 130 collapsed above._