# Master Architectural Audit Report — llm-benchyyyy

**Date**: 2026-08-30 · **Protocol**: boundary-review (6 parallel auditors, flat execution, offline probes) · **Mode**: diagnostic — no code modified.
**Evidence base**: 6 scope reports (`reviews/`), 866 ln, every finding probe-verified or marked `[INFERENCE]`. Working tree included uncommitted checker changes (flagged where relevant).

## Executive Scorecard

| Scope | Boundary | Health | Band | Crit | Mod | Min | Report |
|-------|----------|:------:|:----:|:----:|:---:|:---:|--------|
| S4 | Engine pipeline (task/sandbox/grading/cli) | **4.5** | Critical | 2 | 5 | 5 | [scope4_engine.md](reviews/scope4_engine.md) |
| S2 | Core aggregation (bcheck + benchmark_common) | **5.0** | Critical | 3 | 3 | 3 | [scope2_aggregation.md](reviews/scope2_aggregation.md) |
| S1 | Live scrapers (ocheck) | **5.4** | Critical | 4 | 3 | 3 | [scope1_ocheck.md](reviews/scope1_ocheck.md) |
| S3 | Rankers/detectors (fcheck + scheck) | **5.5** | Critical | 2 | 4 | 2 | [scope3_rankers.md](reviews/scope3_rankers.md) |
| S5 | Harness adapters + infra | **5.5** | Critical | 1 | 7 | 4 | [scope5_harness_infra.md](reviews/scope5_harness_infra.md) |
| SEAM | Cross-boundary contracts (20 seams) | **6.8** | Critical | 1 | 5 | 8 | [scope_seams.md](reviews/scope_seams.md) |
| **Aggregate** | | **5.45** | **Critical** | **13** | **27** | **25** | |

Refuted hypotheses (do NOT remediate): XSS in generated HTML reports — all scraped strings escaped (S1/S3 probes); bcheck offline never-fetch guarantee holds; diff-before-pool-filter ordering correct; silent-zero AA regression not recurring (623 recs parsed, 0 fingerprint rows); task-suite ↔ parser conforming (41/41 md parse, ids aligned, seeds only at grade time); Dockerfile ↔ sandbox uid-1000/image-name/config-dir seams conforming; checkers JSON writer/reader schema conforming; `--sort` None-crash refuted by execution.

## Cross-Cutting Failure Themes

### T1 — Sandbox isolation collapses at two boundaries (S4, S5)
1. [`engine/sandbox.py:64-67`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/sandbox.py#L64) `write_file_to` has no resolve/containment check: `# ../x.txt` or absolute seed headers in task/expected markdown write arbitrary host files — proven by mktemp probe; post-agent-run grading seeds ( [`grading/executable.py:18-19`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/grading/executable.py#L18) ) add a symlink-pivot vector through the rw-mounted workdir. The repo already contains the correct pattern: [`harness/raw_api.py:62-66`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/harness/raw_api.py#L62).
2. [`engine/sandbox.py:20-37,86-90`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/sandbox.py#L20) host credential trees bind-mounted into containers running model-authored bash with unrestricted network; `.gemini` RW is unjustified vs documented rationale; `~/.pi/agent` RW + packages auto-install = model→host settings.json→host code-exec at next pi launch (S5). Zero env-var crossing today (good) — mounts are the surface.
3. [`engine/sandbox.py:106-116`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/sandbox.py#L106) timeout SIGKILLs the docker CLI, not the container → orphaned credential-mounted, networked containers run forever under an rmtree'd workdir.

### T2 — Variant-string matching misattributes model scores (S1 × S2, same class, both files)
ocheck [`find_aa_for_ocgo:504-528`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L504) / [`find_lm_for_ocgo:531-544`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L531) / [`find_livebench_for_ocgo:643-647`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L643) and bcheck [`find_livebench/find_lmarena/find_aa/find_arc:797-908`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L797) all do contains/prefix substring fallback. Live-corrupted today: MiMo-V2.5 carries mimo-v2-5-pro's AA 42.88 (byte-identical in tracked `ocgo_live.json`, overwriting static 80.5); GPT-5.2-Codex carries GPT-5.2(XHigh)'s ARC 52.9; ~14/34 ocheck rows and 9/28 Arena rows mislabeled; digits-stripped fallback resurrects 7-month-old retired CSV rows. Composite weighting (AA 0.65) propagates the corruption into every shipped artifact. Single fix: one variant-guarded matcher in `benchmark_common` (token-level; surplus tokens must be in tier allow-list; None on ambiguity), migrate both files' call sites.

### T3 — Destructive output behind success banners (S2, S3, S5)
- [`llm_benchmark_aggregator.py:948,982,1011`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L948): `--fetch` raises `NameError` on undefined `do_fetch` (uncommitted-diff regression) swallowed by bare `except Exception: pass` → live payloads discarded, no snapshots saved, "updated NEW-baseline" printed; caches 53-59h stale, cannot self-heal. Zero test coverage of `fetch=True` paths admitted it (27/27 green).
- [`report.py:37`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/report.py#L37) coerces null cost→$0.00: antigravity reports **$0 per success** on the live leaderboard (59/59 rows cost_null probe-verified); [`cli_adapter.py:158-161`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/harness/cli_adapter.py#L158) extraction failures silent on configured paths.
- [`free_model_ranker.py:541-570`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/free_model_ranker.py#L541): two actually-paid Cline models committed into `free_models.json` with fabricated zero pricing (is_free_model never applied); [`free_model_ranker.py:723-728` × `benchmark_common.py:1366`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/free_model_ranker.py#L723): catalog diff permanently broken (ocheck-only `is_docs_model` filter) → every run marks all 31 rows NEW, removals silently dropped; [`stealth_model_detector.py:334-347,472-488`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/stealth_model_detector.py#L334): one network blip overwrites last-good `stealth_models.json` with an empty catalog.
- [`engine/cli.py:126-135`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/cli.py#L126): all trials error → no records, **exit 0** (proven with missing SDK); infra rc 125/126 recorded as model "fail" → poisons `runs.jsonl`.

### T4 — Judge decommission is documentation-only (S4, S5, SEAM — triple-confirmed)
Invariant "NO LLM JUDGES" ([`.mimori/memory.md:24-26`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/.mimori/memory.md#L24)) vs code: [`spec.py:36-37`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/grading/spec.py#L36) substring → [`cli.py:32,73`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/cli.py#L32) GRADERS → [`judge.py:89`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/grading/judge.py#L89) → host CLI spawn (`run_host_text`, unsandboxed); plus `--judge-*` flags (cli.py:181-192) and `selfsolve.py:39-40`. Dormant only because 0/20 expected files say "judge" — a one-line markdown edit by any contributor following metrics.md:25 / README:70-73 reactivates LLM grading. Ships with contradictory twin memory (`.agents/memory.md:23` mandates judge rubrics) and no ADR.

### T5 — Attribution protocol unenforced (SEAM, S5, S4)
`--trials` defaults **1** ([`cli.py:179`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/cli.py#L179)) vs N≥3 invariant (3/61 live groups already <3); [`score.py:42-49`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/score.py#L42) groups on (harness,model,task) — drops `tool_access`/`harness_version` while [`report.py:8`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/report.py#L8) keys correctly: the two official aggregators implement incompatible comparability contracts, a 1-trial task earns full points; `constraint_violations`/`scaffold_notes`/`cached_tokens` required by metrics.md have no producer (179/179 rows empty); `harness_version` captured on host while harnesses run in-container (codex → silent bare-name fallback).

### T6 — Durability of tracked data (S2, S1)
`save_baseline` direct `write_text` ([`llm_benchmark_aggregator.py:1857`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1857)) + silent corrupt-JSON→None fallback ([`benchmark_common.py:1279-1287`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L1279)): one torn write irrecoverably erases the only `first_seen`/7-day-green history. Same for `ocgo_live.json`/reports. Staleness keyed on file mtime → fresh clone masks weeks-old data (S2 M2).

### T7 — Credential handling in checkers (S1, conditional)
[`opencode_cost_benefit_analyzer.py:691-704,725-731`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L691) `_find_key_recursive` harvests the *first* key/token/secret from multi-provider `auth.json` and sends it as Bearer to opencode.ai — third-party credential exfil on any multi-provider host (benign single-provider today); secrets also cross via `--key` argv.

## Remediation Roadmap

### P1 — Security / silent data corruption / false success (11 items)
| # | Fix | Files · lines | Source |
|---|-----|---------------|--------|
| 1.1 | Path containment in `write_file_to` (resolve + is_relative_to + no-symlink), covers grading seeds + pivot | engine/sandbox.py:64-67 | S4 F-01 |
| 1.2 | Drop `.gemini` RW; overlay-throwaway `~/.pi/agent`; `--network none` for setup/check phases | engine/sandbox.py:20-37,86-90 | S4 F-02, S5 |
| 1.3 | `--cidfile` + docker-kill on TimeoutExpired before returning rc 124 | engine/sandbox.py:106-116 | S4 F-04 |
| 1.4 | One variant-guarded matcher in bc; migrate ocheck+bcheck (8 call sites); regenerate corrupted tracked artifacts offline | checkers/*.py (T2 lines) | S1 C1-C3, S2 C2 |
| 1.5 | `if do_fetch:` → `if fetch:`; bare excepts → logged WARNs; add fetch=True test | checkers/llm_benchmark_aggregator.py:948,982,1011,962,991,1020 | S2 C1 |
| 1.6 | Cline free-path validation via `is_free_model`; scope `is_docs_model` filter (or explicit flag); scheck refuse `--json` write on source failure | checkers/free_model_ranker.py:541-570,723-728; checkers/stealth_model_detector.py:334-347; checkers/benchmark_common.py:1366 | S3 F3-1/2/6 |
| 1.7 | Atomic tmp+`os.replace` for all tracked JSON writes; loud corrupt-baseline warning distinct from cold start | llm_benchmark_aggregator.py:1857; ocheck:2079-2095; benchmark_common.py:1279-1287 | S2 C3, S1 M2 |
| 1.8 | Fail-loud on null configured-field extraction; render "unpriced" not $0; no silent null→0 coercion | engine/harness/cli_adapter.py:158-161; engine/report.py:37; engine/cli.py:66-68 | S5 |
| 1.9 | Error accounting: result="error" records, non-zero exit when trials errored, rc 125/126 + docker-stderr → skip record, not "fail" | engine/cli.py:71-73,126-135; engine/sandbox.py | S4 F-05/06, S5 |
| 1.10 | Gate judge seam: raise at `judge-ensemble` dispatch; delete `--judge-*` flags, GRADERS entry, selfsolve route (or ADR-sanctioned opt-in) | engine/cli.py:32,112-115,181-192; engine/grading/spec.py:36-37; engine/selfsolve.py:39-42 | S4 F-03, S5, SEAM C1 |
| 1.11 | Targeted opencode-go provider lookup (copy pi pattern at :718-722); stop `--key` argv | checkers/opencode_cost_benefit_analyzer.py:691-704,725-731,740 | S1 C4 |

*Also P1-adjacent (S5): `anthropic` unpinned in Dockerfile and absent from the host `python3` that run scripts invoke — raw-api is 100% broken (ModuleNotFoundError proven).*

### P2 — Invariants / robustness (10 items)
| # | Fix | Source |
|---|-----|--------|
| 2.1 | Enforce N≥3: reject/warn `--trials<3`; score.py annotate under-trialed | SEAM M1 |
| 2.2 | score.py group on (task,model,harness,tool_access,harness_version); dedupe trial_numbers — align with report.py contract | SEAM M2, S4 F-07 |
| 2.3 | harness_version captured in-container via exec_in; fallback loud; pin 5 CLIs in Dockerfile | S5 |
| 2.4 | Pareto `or`-chain → explicit None handling so cost 0.0 keeps frontier gold | S2 M1 (benchmark_common.py:233,237) |
| 2.5 | Pricing: canonical undated keys + unknown-model warning (dated-only Haiku key silently bills Sonnet rates ≈3.75×) | SEAM M5 (engine/pricing.py:13,21) |
| 2.6 | Producers for metrics.md fields (cached_tokens at minimum) or documented ceiling markers | SEAM M3 |
| 2.7 | Offline-by-default parity: fcheck/scheck/ocheck adopt bcheck's 24h-cache contract; `--check` writes nothing; mtime→content-date staleness | S3 F3-5/3, S2 M2, SEAM m5 |
| 2.8 | raw_api: timeout/retry on `client.messages.create`, turn-loop bound, error records carry billed tokens; cli_adapter honor returncode/124 | S5 |
| 2.9 | run_suite_parallel.sh: per-PID wait + exit aggregation | S5 |
| 2.10 | fcheck provider-prefix dedup; ocheck first_seen re-stamp for 6 legacy models; dead zen price clause; sandbox tempdir leaks + CRLF + parse_task field validation | S3 F3-3/4, S1 M1, S4 F-08/09/10 |

### P3 — Docs / hygiene (batch)
Strike judge + dated-id instructions (metrics.md:9,25-26; scope.md:34-35,112-114; README.md:12,70-73,84-85; grading-methodology.md:19-41) · reconcile `.agents/` twin memory + record judge-decommission ADR · regenerate `.mimori/repo_map.md` (bench/→engine/) · ocheck: remove 10 dead shadowed imports, fix `--out` dead flag + `--check --fetch` write claim, stale-snapshot warning (SEAM M4; S1 m1-m3) · spec.py accept hyphenated spellings + `human` or fail with guidance (SEAM m6) · task-file contamination notes → expected/ (SEAM m2) · TUTORIAL 4→5 harnesses, `python`→`python3` (SEAM m3/m4) · summarize_tasks.py reuse engine.markdown (SEAM m7) · pyproject `bench` alias removal · test gaps: fetch=True, std=0 z-scores, corrupt-baseline fallback, diff ordering, template guard.

## Recommended execution order
P1.1–1.3 (isolation) → P1.4–1.7 + 1.5 (data-integrity of shipped artifacts, incl. regeneration) → P1.8–1.9 (+SDK pin) → P1.10–1.11 → P2 batches → P3 sweep. Verification per batch: targeted unittests + offline bcheck/ocheck/fcheck re-runs + path-traversal probe re-run + `mimori debt check`. Note: P1.4/1.5/1.6/1.7 touch files with uncommitted working-tree changes — confirm those WIP edits are yours to supersede before executing.

---

## Execution Status (2026-08-30/31)

| Batch | State | Verification |
|-------|-------|--------------|
| P1 (11 items + adjacent) | ✅ executed | containment re-probe (3 vectors rejected); judge grep → raise-guard only; all-error run rc=1, runs.jsonl 179→179; network-none probe; 64→64 checker tests |
| P2 (10 items) | ✅ executed | trials-<3 → rc=2; score 5-key grouping + U-flags on real 179-row data; pareto probe FreeX holds gold; --check triple docs-untouched (porcelain+md5); dedup 31→28 distinct; first_seen stable across 3 regen runs; staleness filename-authoritative |
| P3 (batch) | ✅ executed incl. residual ocheck pareto-chain + selfcheck extensions (score-grouping, pricing-warn) | 73/73 checker tests; compileall rc=0; selfcheck full-corpus rc=0 post task-file moves; docs judge-grep → deprecation contexts only; bench alias gone; scripts bash -n |

**Outstanding (design-grade, not batch-fixable)**: harness-phase egress proxy allowlist; per-harness credential fragments (ro whole-dir trees still readable in-container); live verification of the 5 unpinned CLI field-maps + Dockerfile rebuild (`.mimori/memory.md` KNOWN DEBT); `benchmarks.json` baseline still carries pre-fix persisted `arc_display` until one networked `--fetch`.
