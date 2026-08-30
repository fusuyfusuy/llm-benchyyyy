# Scope: Cross-Boundary Seam & Interface Audit

- **Auditor:** SeamAuditor (boundary/seam focus — no intra-scope logic verdicts)
- **Date:** 2026-08-30
- **State audited:** working tree incl. uncommitted changes to `checkers/llm_benchmark_aggregator.py` + tests + data files (`git status` verified)
- **Health score:** **6.8 / 10** (Critical seam breach present; zero code edits made)

## Method

Every seam below was probed against live code and data, not docs alone:
`parse_task`/`parse_grading_spec` executed on all 41 task/expected `.md` files (0 failures);
bcheck executed offline end-to-end (`--plain --pool all`, exit 0, 30-model table + staleness banner);
37 targeted checker unittests run (`checkers.test_llm_benchmark_aggregator`, `test_opencode_cost_benefit_analyzer`, `test_benchmark_common` — OK);
`python3 -m engine.selfcheck` run (OK);
shadowing verified programmatically (module-level defs vs `from benchmark_common import` names);
`results/runs.jsonl` (179 rows) analyzed against metrics.md; host `id -u devhax` checked against image `USER ubuntu`.

---

## SEAM 2 (flagship) — Judge decommission invariant ↔ live code

**Verdict: LIVE-WIRED (contract breach), currently data-unreachable.** Not dead code, not parked.

Dispatch evidence chain (each link verified on disk):

1. `.mimori/memory.md:24-26` — invariant: “NO LLM JUDGES ALLOWED … judge ensemble has been decommissioned”.
2. `engine/grading/spec.py:36-37` — `_classify_method` still *maps* any method string containing “judge” (not already matching exact-match/unit-test/state-check) to `"judge-ensemble"`, with no refusal anywhere in the parser.
3. `engine/cli.py:32` — `GRADERS["judge-ensemble"] = lambda spec, sb, text: judge_grade.grade(spec, text).passed`; dispatched unconditionally at `engine/cli.py:73` (`GRADERS[spec.method](...)`), guarded only by `:71` `not in GRADERS` (it *is* in GRADERS).
4. `engine/cli.py:112-115` + `:181-192` — `cmd_run` and argparse actively expose `--judge-harness` / `--judge-model`, writing `judge_grade.JUDGE_HARNESS/JUDGE_MODEL` (backed by `BENCH_JUDGE_HARNESS`/`BENCH_JUDGE_MODEL` env at `engine/grading/judge.py:35,40`).
5. `engine/grading/judge.py:109-146` → `:105 _call_judges` → `:89 _fetch_response` → `engine/harness/cli_adapter.py:221-235 run_host_text` — executes a **real host CLI process** (`pi-agent` default) per vote. No feature flag, no env kill-switch, no raise.
6. `engine/selfsolve.py:39-40` — second live route: golden solutions graded through the same judge.

Data-unreachability today: all 20 `expected/*/*.md` declare `unit test`/`state check`/`exact match` methods (verified by executing `parse_grading_spec` on each; several even say “executable, not judge”); 0 of 179 rows in `results/runs.jsonl` have `grading_method=judge-ensemble`. So no *committed* task triggers it — but **one new expected file with a “judge” word in `**grading method:**` silently reactivates LLM grading**, and the docs teach people to write exactly that (below).

Breach is amplified by canonical docs that still *instruct* judge use:

- `metrics.md:25-26` — `grading_method` enumeration lists `judge-ensemble`; “See `expected/grading-methodology.md` for judge protocol”.
- `scope.md:34-35` — reasoning tasks graded “by judge-ensemble where not [automatic]”; `scope.md:112-114` — “judge-ensemble rules”.
- `README.md:70-73` — “Adding a task”: write “a numbered `## Rubric` for **judge-graded** ones”; `README.md:12` — “needed for … judge-graded tasks”; `README.md:42-43` — “three graders (executable, exact-match, judge-ensemble)”.
- `expected/grading-methodology.md:19-41` — entire “When a judge is required” protocol with 6 required mitigations, presented as current policy.
- `README.md:84-85` — “judge-ensemble grading call the Anthropic API directly and only need `ANTHROPIC_API_KEY`” — **factually stale**: `judge.py:3-4` transport is the pi CLI (“No API key needed”). Docs describe a superseded transport for a decommissioned feature.

Split memory files (governance seam): the repo carries **two contradictory project-memory files**. `.mimori/memory.md:24-26` has the NO-JUDGES invariant; `.agents/memory.md` **lacks it entirely** and instead states `:23` “`## Rubric` numbered list = **judge-graded criteria**” and `:6-8` keeps the judge as an open epic (“judge.py untested live”). Neither `.mimori/decisions.md` nor `.agents/decisions.md` contains an ADR recording the decommission — the rule exists in exactly one file, contradicted by its twin, unenforced by code.

---

## Drift table

| # | Seam | Declared contract | Live state | Verdict | file:line |
|---|------|-----------------|------------|---------|-----------|
| 1 | judge invariant ↔ engine | NO LLM judges (memory.md:24-26) | judge-ensemble registered in GRADERS, argparse, selfsolve; transport executes host CLI | **Breach (live-wired, data-unreachable)** | engine/cli.py:32,112-115,181-192; engine/selfsolve.py:39-40; engine/grading/spec.py:36-37; engine/grading/judge.py:89 |
| 2 | judge ↔ docs | decommissioned | metrics/scope/README/grading-methodology still teach judge protocol; README describes dead Anthropic-API transport | Breach (doc-side) | metrics.md:25-26; scope.md:34-35,112-114; README.md:12,70-73,84-85; expected/grading-methodology.md:19-41 |
| 3 | memory ↔ memory | single source of rules | `.agents/memory.md` lacks NO-JUDGES rule, mandates `## Rubric`=judge | Contradiction | .mimori/memory.md:24-26 vs .agents/memory.md:23 |
| 4 | N≥3 trials ↔ CLI | “Every run must repeat N>=3” (memory.md:27); “must be ≥ 3” (TUTORIAL.md:40) | `--trials` default **1**, no validator anywhere; real data already violates (3/61 groups <3 trials) | Breach (unenforced) | engine/cli.py:179; results/runs.jsonl (289 trials/179 rows analysis) |
| 5 | layer attribution ↔ score.py | pass_rate per (task,model,harness,tool_access); different tool_access incomparable (metrics.md:14-16,43) | report.py groups correctly; score.py leaderboard keys only (harness,model,task) → mixes incomparable runs | Breach | engine/report.py:8 vs engine/score.py:42-49,69 |
| 6 | metrics required fields ↔ engine | constraint_violations tracked separately; cached tokens “should not be hidden”; result may be `partial` (metrics.md:23-29,34-35) | `constraint_violations=""` and `scaffold_notes=""` hardcoded; `cached_tokens=None` hardcoded (raw_api.py only reads input/output usage); result only pass/fail | Breach (no producers) | engine/cli.py:83,85,87,91; engine/harness/raw_api.py:108-109; results/runs.jsonl 179/179 empty |
| 7 | model-id no-date ↔ docs/engine | `claude-sonnet-5`, no date suffix (memory.md:37-39; docs/models.md:41) | metrics.md example uses `claude-sonnet-5-20260115`; pricing table keyed by dated `claude-haiku-4-5-20251001` — undated alias silently falls to Sonnet rates (≈3.75× input overcharge) | Doc drift + engine inconsistency | metrics.md:9; engine/pricing.py:13,15,21 |
| 8 | spec vocabulary ↔ metrics vocabulary | `grading_method` ∈ {exact-match, unit-test, judge-ensemble, human} (metrics.md:25) | parser accepts only phrase forms (“exact match”, “unit test”, “state check”, “judge”); `human` → ValueError; hyphenated metrics.md spellings rejected | Drift (Minor) | engine/grading/spec.py:30-38 vs metrics.md:25 |
| 9 | task-suite ↔ parser | all 42 md conform to schema | 41/41 parse OK; ids = stem↔stem aligned; all `## Setup`/`## Check` are bash-fenced; all seed headers `# x.py` well-formed | **Conform** | engine/task.py:27-56; engine/markdown.py:12; probe log above |
| 10 | contamination invariant | “Nothing about … how it’s graded belongs in this file” (scope.md:62; README.md:30-32) | 6 task files name held-out test files / grader mechanics (no answers leaked; `368` absent) | Drift (Minor) | tasks/coding/fix-off-by-one-pagination.md:27,36; add-csv-export-endpoint.md:28; hotpath-quadratic-bottleneck.md:62-66; jsonpatch-rfc6902-hardened.md:168; wal-torn-write-recovery.md:142,146 |
| 11 | Dockerfile ↔ sandbox ↔ configs | non-root uid-1000, creds ro, image name | `USER ubuntu` (uid 1000), no `--user` needed; host devhax uid=1000 ✓; `BASE_IMAGE="llm-bench-harness"` == build tags in README:13/TUTORIAL:17 ✓; all 5 config dirs covered (.claude,.claude.json,.codex,.config/opencode,.gemini,.pi/agent) | **Conform** | docker/harness-base.Dockerfile:43; engine/sandbox.py:18,27-34,74-95 |
| 12 | rw-mount exception ↔ invariant text | memory.md:31-33 + :44-46 cite only `~/.pi/agent` rw | `RW_MOUNTS={".pi/agent",".gemini"}`; `.gemini` rw legitimized by TUTORIAL:28,32 | Invariant text lag (Minor) | engine/sandbox.py:37 vs .mimori/memory.md:31-33 |
| 13 | checkers JSON writer/reader | bcheck→benchmarks.json(dict first_seen+catalog_diff); ocheck→ocgo_live.json; fcheck→free_models.json; scheck→stealth_models.json | all dict payloads correct; per-model `first_seen` present (22/30); only reader of each file is its own producer’s `load_previous_snapshot` (self-referential, no cross-consumer drift); stealth lacks catalog_diff **as documented** (memory.md:78) | **Conform** | checkers/llm_benchmark_aggregator.py:1844-1857,1945; …/opencode_cost_benefit_analyzer.py:2010,2080; free_model_ranker.py:724,764; stealth_model_detector.py:486 |
| 14 | bcheck offline loader ↔ data on disk | “runs fully offline by default; >24h = warning banner” | Executed offline: full 30-row table, ARC filled (arc_agi_20260830.json fresh), staleness banner names LiveBench/LMArena/AA; no silent-empty path found | **Conform (verified by run)** | checkers/llm_benchmark_aggregator.py:1945-1953,1030-1047 |
| 15 | ADR-2026-08-27 consolidation ↔ ocheck imports | shadowing migrated to shared funcs | ocheck imports display_len,color_cell,norm_id,_safe_float/_safe_int/_safe_int_round,parse_aa/parse_livebench/parse_openrouter,C_RESET (lines 40-54) then **redefines all 10 locally** (:381,385,487,564,659,676,683,783-784,796) → dead imports, shared helpers shadowed; bcheck/fcheck/scheck clean | Breach of claim (intentional divergence per memory.md:79-93, but import lines make it invisible) | checkers/opencode_cost_benefit_analyzer.py:40-54,381-796 |
| 16 | offline-by-default checker convention | bcheck model (memory.md:73-78) | ocheck/fcheck/scheck still default-online (`--offline` opt-in: ocheck:1439, fcheck/scheck fetch_or_load_cached_json:99-100); ocheck writes docs/data+docs/reports on every default run (`do_write=not --check` :1465) | Asymmetric convention (Minor) | checkers/opencode_cost_benefit_analyzer.py:1439-1441,1465,2055-2095; checkers/stealth_model_detector.py:295-297 |
| 17 | docs commands ↔ CLI reality | quickstart + run scripts runnable | `pyproject` scripts `engine`/`bench` → engine.cli:main ✓; `python -m engine` ✓ (`__main__.py`); every flag in run_suite_parallel.sh/run_benchmarks.sh exists in argparse; verify/report/self-solve subcommands present; `python` (no 3) absent on reference host — quickstart literal fails here | Conform except interpreter nit (Minor) | pyproject.toml:9-11; run_suite_parallel.sh:23,31-36; README.md:15 |
| 18 | memory/repo_map paths ↔ tree | engine/ since c25454d | `.mimori/repo_map.md` entirely `bench/`-prefixed (~20 entries) with stale line maps (judge `_client` at :65 no longer exists); `.mimori/memory.md:6,20` and `.agents/memory.md:3-4,19` cite `bench/harness/configs.py`, `bench/markdown.py` | Stale paths (Minor, grouped) | .mimori/repo_map.md:7-86; .mimori/memory.md:6,20 |
| 19 | TUTORIAL harness count | “4 supported harnesses / pre-installed with all 4 CLI tools” (TUTORIAL:3,19) | REGISTRY + image install 5 CLIs (codex-cli missing from TUTORIAL) | Doc drift (Minor) | engine/harness/configs.py:111-117; docker/harness-base.Dockerfile:30-35 |
| 20 | --task TEMPLATE guard | templates are non-runnable scaffolds | glob path filters TEMPLATE.md; explicit `--task tasks/team-workflows/TEMPLATE.md` reaches missing `expected/team-workflows/TEMPLATE.md` → per-trial ERROR print (loud, contained) | Nit (P3) | engine/cli.py:101-107 |

---

## Findings

### Critical

**C1 — Judge ensemble is decommissioned by invariant but live-wired end-to-end by engine and docs.**
Dispatch is complete from argparse → GRADERS → `judge.grade` → host `pi` CLI spawn (chain §SEAM-2 items 1-6); the only thing keeping it dormant today is that no expected file says “judge”. Four canonical docs actively instruct authoring judge-graded tasks, `README.md:84-85` documents a transport the code no longer has, and `.agents/memory.md` (a second copy of project memory the repo ships) asserts the opposite rule set with no decommission clause and no ADR anywhere recording the decision. Any contributor following README:70-73 or metrics.md:25 can re-enable LLM grading with a one-line markdown edit. Fix (P1): refuse `method == "judge-ensemble"` at dispatch (raise with pointer to invariant), delete the `--judge-*` flags and `judge.py`/`GRADERS` entry (or gate behind an explicit opt-in env + ADR), strike the judge instructions from metrics.md/scope.md/README/grading-methodology, and reconcile or delete `.agents/`.

### Moderate

**M1 — N≥3 trials invariant has zero enforcement and CLI defaults to 1** (`engine/cli.py:179` vs `.mimori/memory.md:27`, `TUTORIAL.md:40`, `metrics.md:19`). The run scripts pass 3 by convention; historical data already contains groups with 1 and 2 trials (3 of 61). `score.py` awards a single-trial task full proportional points. Fix: reject `--trials < 3` in `cmd_run` (or loudly warn + tag), and let score.py annotate under-trialed rows.

**M2 — `engine/score.py:42-49` aggregates leaderboard rows on (harness, model, task) only.** metrics.md:14-16 and :43 require tool_access to be part of every comparability group; `report.py:8` gets this right (`GROUP_KEYS` includes tool_access), so the two official aggregators disagree on the grouping contract. Re-running the same task with different tool access silently merges into one row and dilutes pass rates. Also ignores `harness_version` (metrics.md:12-13: unpinned versions invalidate comparison over time) and counts duplicate `trial_number`s.

**M3 — metrics.md required fields have no producer.** `constraint_violations` and `scaffold_notes` hardcoded `""`, `result="partial"` unreachable, `cached_tokens` hardcoded `None` at `engine/cli.py:83-91` even though Anthropic `usage` reports cache fields (raw_api.py:108-109 reads only input/output) — metrics.md:34-35 explicitly says cached tokens “should not be hidden”. 179/179 rows in `results/runs.jsonl` confirm. Either populate them or mark them provisionally-unavailable in metrics.md; the RunRecord docstring “fields matching metrics.md exactly” (engine/results.py:12) overpromises.

**M4 — ocheck shadows 10 imported `benchmark_common` helpers** (`checkers/opencode_cost_benefit_analyzer.py:40-54` imports, `:381,385,487,564,659,676,683,783,784,796` redefine). The 2026-08-27 ADR says shadowed helpers were migrated onto shared functions; the divergence itself is deliberate per memory.md:79-93, but the *imports remain*, so the module header reads as “shared helpers in use” while every call binds the local copy. A shared fix (e.g. display_len emoji-width, memory.md:88) silently won’t reach ocheck. Fix: drop the 10 dead import names and annotate intentional locals, or genuinely de-duplicate.

**M5 — model-id no-date invariant vs pricing + metrics example.** `metrics.md:9` prescribes `claude-sonnet-5-20260115` — the exact string invariant 4 declares invalid (`.mimori/memory.md:37-39`, `docs/models.md:41`). Meanwhile `engine/pricing.py:13` keys Haiku by a dated id only, so the invariant-conformant `claude-haiku-4-5` silently falls through `PRICING_PER_MTOK.get(..., _DEFAULT_RATES)` (pricing.py:21) to Sonnet rates → ~3.75× input / ~3.75× output cost overstatement, undetectable in `runs.jsonl`. Fix: normalize pricing keys to canonical ids and add unknown-model warning; correct metrics.md example.

### Minor (grouped)

**m1 — stale-path inventory:** `.mimori/repo_map.md` uses `bench/` throughout (~20 entries incl. `:74` `bench/grading/judge.py` with a `_client` symbol that no longer exists); `.mimori/memory.md:6,20`; `.agents/memory.md:3-4,19`. Re-generate repo_map; sed memory rules to `engine/`.
**m2 — contamination hygiene:** held-out test names / grading mechanics referenced inside 6 task files (rows 10 of drift table); no answers leak, but it contradicts README.md:30-32 and scope.md:62. Move operator notes into expected/.
**m3 — TUTORIAL:3,19 says 4 harnesses/“4 CLI tools”; image installs 5 (codex-cli omitted from the tutorial and its auth story).**
**m4 — `python` vs `python3`:** quickstart (README:15,18; TUTORIAL:48-82) uses `python`, absent on the reference host; scripts correctly use `python3`.
**m5 — checker mode asymmetry:** bcheck offline-by-default; ocheck/fcheck/scheck still fetch by default, and ocheck rewrites `docs/data/ocgo_live.json` + `docs/reports/*` on every plain run (M-adjacent nuisance for CI).
**m6 — spec vocabulary:** hyphenated `exact-match`/`unit-test` spellings from metrics.md:25 and the `human` method have no parser acceptance (spec.py:30-38 raises) — a contributor writing an expected file verbatim from metrics.md crashes `engine run` at parse time.
**m7 — `summarize_tasks.py:10-31` hand-rolls a third regex copy of the markdown convention** (bold-field, `## Instruction`) instead of importing `engine.markdown`, the one seam ADR (“single shared parser”) was meant to remove.
**m8 — TEMPLATE nit** (drift row 20).

### Confirmed conforming (refuted hypotheses)

- All 41 task/expected files parse through the real engine parser; id stems align 1:1 across tasks/expected/solutions (20/20 with .sh oracles); every `## Setup`/`## Check` is a `bash` fence; every seed header matches `# \S+\.\w+`; held-out test files are seeded only at grade time (`executable.py:18-19`), never visible to the solver.
- No dated model ids were ever recorded in `runs.jsonl`; judge never invoked in 179 committed runs.
- Image name/tag identical in `sandbox.py:18`, README:13, TUTORIAL:17; uid 1000 matches host; mount set covers all 5 CLIs (`.gemini` = agy per TUTORIAL:28).
- bcheck offline run produces a correct populated table against the current (uncommitted-refreshed) data files; benchmarks.json dict shape + per-model `first_seen` match memory.md:73-78; 37 targeted tests + selfcheck green.

## Verification log (commands run)

- `python3` probe: `parse_task` × 21 + `parse_grading_spec` × 20 → 0 failures (method/section/fence inventory)
- `python3 checkers/llm_benchmark_aggregator.py --plain --pool all` → exit 0, output archived `/tmp/bcheck_out.txt`
- `python3 -m unittest checkers.test_llm_benchmark_aggregator checkers.test_opencode_cost_benefit_analyzer checkers.test_benchmark_common` → 37 OK
- `python3 -m engine.selfcheck` → OK
- JSON schema probes on `docs/data/*.json`; runs.jsonl aggregation; `id -u`; import-shadow script; `git status`/`git diff`

## P1/P2 backlog

- **P1:** C1 judge gate: raise on `judge-ensemble` dispatch + remove `--judge-*` flags + strike judge instructions from metrics.md:25-26/scope.md:34-35,112-114/README.md:12,70-73,84-85 + reconcile `.agents/` vs `.mimori/` memory + add decommission ADR.
- **P1:** M1 `--trials < 3` refusal in cmd_run.
- **P2:** M2 score.py grouping (+tool_access, +harness_version, min-trials annotation); M3 populate or document-away the four dead metrics fields; M4 remove ocheck’s 10 dead imports; M5 pricing canonical-key normalization + metrics.md:9 example fix.
- **P3:** m1-m8.
