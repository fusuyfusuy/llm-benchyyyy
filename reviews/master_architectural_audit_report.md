# Master Architectural Audit Report — llm-benchyyyy (Round 3, 2026-09-01)

Consolidated from 6 parallel boundary audits (`reviews/scope_1_shared_foundation.md`, `scope_2_bcheck_aggregator.md`, `scope_3_cost_analyzers.md`, `scope_4_rankers.md`, `scope_5_daemon_tests_docs.md`, `scope_seams.md`). All P1 findings independently verified by the orchestrator against live code and snapshots.

## Executive Scorecard

| Scope | Health | Band | Prior (R2) | Delta |
| :--- | :---: | :--- | :---: | :--- |
| 1 — Shared Foundation & Math | 8.6 | Minor | — | — |
| 2 — Universal Aggregator (bcheck) | 7.2 | Moderate | 8.2 | -1.0 |
| 3 — Cost Analyzers (ocheck/ccheck) | 7.8 | Moderate | — | — |
| 4 — Model Rankers (fcheck/scheck) | 6.4 | **Critical** | 9.0 | **-2.6** |
| 5 — Sync Daemon, Tests & Docs | 7.1 | Moderate | 7.5 | -0.4 |
| Seams & Interfaces | 8.6 | Minor | 6.5 | +2.1 |
| **Overall** | **7.4** | **Moderate** | — | — |

Prior-round Criticals confirmed remediated: atomic-write race (PID+ns temp name), daemon 30s polling loop, systemd/cron path quoting, UTC snapshot dates, fetch retry/backoff, daemon entrypoint bypass, fcheck/scheck offline-by-default.

## P1 — Critical (fix first)

### P1-A. ocheck fabricates capability scores for benchmark-uncovered models
- **Where**: `checkers/opencode_cost_benefit_analyzer.py#L1785-L1820`
- **What**: With no AA/LM/LiveBench coverage, `weights=[]` → `cz=0.0` → `compute_capability_q(0)` = **78.0** (z=0 center). Uncovered models get Q=78, P(Succ)=67.3%, AVI≈825 with 🥇 medals, effective_cost=$0, and enter the **Pareto frontier as undominated**. Verified live: `ox-alpha-free` (free, no pricing, no benchmarks) renders all of these.
- **Why it's a breach**: ccheck has the identical branch with a no-coverage guard (`commandcode_cost_benefit_analyzer.py#L885-L905`) that nulls all scores. Same boundary, opposite contracts → silent wrong output. The fix was tested in ccheck but never ported to ocheck.
- **Fix**: port ccheck's `if not weights:` null-out guard to ocheck + shared regression test asserting uncovered models show `—`, win no medals, never hit Pareto.

### P1-B. OpenRouter pricing join is structurally dead → fabricated prices in rankings
- **Where**: `checkers/llm_benchmark_aggregator.py#L888-L910` (index build) vs `#L1093-1095, 1123, 1148` (join sites)
- **What**: `load_openrouter_pricing_data` keys the index with `bc.norm_id(full_id)` — the regex strips `/` and `:` so provider and id glue together (`tencenthy4-preview`, `z-aiglm-5.3-flash`). But AA slugs are bare (`hy4-preview`, `glm-4-5v`) and join sites look up `or_pricing.get(nid)` with those bare slugs. **Measured: 0/625 AA slugs, 0/541 API rows ever match.** The fallback fabricates `price_in=1.0, price_out=3.0` for every unmatched model, which propagates into blended price → effective_cost → AVI/BFI/Pareto rankings.
- **Fix**: index OR pricing on provider-stripped suffix (`norm_id(mid.split("/")[-1].split(":")[0])`) with full-id fallback; add a join unit test.

### P1-C. `parse_openrouter` normalized subset broke the fcheck/scheck OR seam (regression from 4c23c01)
- **Where**: `checkers/benchmark_common.py#L724-L763` vs `checkers/free_model_ranker.py#L501, 540, 578` and `checkers/stealth_model_detector.py`
- **What**: `parse_openrouter` returns a normalized subset (id/name/context/prompt_price_1m/completion_price_1m/is_free/is_stealth) that **drops `pricing`, `context_length`, `architecture`** — the raw fields fcheck/scheck read back. Result: `is_free_model` is vacuously true for **425/425** records (incl. paid `ibm-granite/granite-4.2-8b` at $0.10/$0.15), `_free_key` carries `context_length=None`/`pricing=None`, `Ctx` renders `—` for all 10 fcheck rows, and the S3-F3-1 Cline-validation gate can never fire. scheck equally affected (`price_str` always `0.00/0.00`, `modality` always `—`). A paid model in Cline's free list would now be listed with fabricated $0 — latent scope-invariant breach.
- **Fix**: carry `pricing`/`context_length`/`architecture` through `parse_openrouter`; strict `is_free_model` (require `:free` suffix or explicit `== 0.0` on real numbers; missing/negative ⇒ not free); build `or_free_by_key` only from free-filtered records preferring `:free` twin; WARN when no record has real pricing. Add OR-path unit tests (currently zero coverage).

### P1-D. Daemon accepts any HTTP body as success → 404s saved as authoritative snapshots
- **Where**: `checkers/benchmark_sync_daemon.py#L71-L85` (fetch_url_content) + `#L88-L205` (sync_all_sources writes)
- **What**: `fetch_url_content` returns any body (14-byte "404 Not Found") as success; each feed writes it via atomic write. **Evidence in `docs/data/sync_daemon.log`**: all 8 feeds saved as `(14 bytes)`, baseline collapsed 1146 → 30 → 35 models.
- **Fix**: per-feed min-size + HTTP-status + content-sniff validation before `atomic_write_text`; refuse to overwrite today's snapshot with garbage.

### P1-E. Daemon has no pid/lock → concurrent syncs race, one process's 404 can clobber another's fresh snapshot
- **Where**: `checkers/benchmark_sync_daemon.py#L217-L248, 381-413`
- **What**: no lock file; log shows multiple overlapping runs per minute (daemon + cron + manual). Combined with P1-D, concurrent runs amplify corruption.
- **Fix**: exclusive lock (`flock` or `O_EXCL` with stale-PID reclaim), released on signal.

### P1-F. Daemon's mocked test overwrites the real tracked `benchmarks.json`
- **Where**: `checkers/test_benchmark_sync_daemon.py#L58-73` patches `bsd.RAW/DATA` but **not `lba.DATA`**; the baseline-refresh step (`benchmark_sync_daemon.py#L187-202` → `save_baseline` default path, `llm_benchmark_aggregator.py#L2410-2424`) writes the real file. **Verified live**: md5 of `docs/data/benchmarks.json` changed across one test run (restored after audit). Breaches the "data never touches tracked files" invariant.
- **Fix**: patch `lba.DATA` (or inject `path=`) in the mocked sync test; assert no tracked file written.

### P1-G. LiveBench loader merges ALL dated snapshots, injecting stale rows as live signals
- **Where**: `checkers/llm_benchmark_aggregator.py#L1262-1263` (`for p_csv in csv_matches:`) vs newest-only `matches[-1:]` in the other two loaders (`#L1302, 1330`)
- **What**: `livebench_20260108.csv` is the only source of `mimo-v2-pro` (overall 58.35) in today's 2026-09-01 data; via the catalog alias `mimo-v2-pro` (`#L776`) MiMo-V2.5 is reported tri-verified with a stale January LiveBench score.
- **Fix**: newest-only LiveBench snapshot selection; drop stale CSVs from the merge.

## P2 — Moderate

- **P2-A. LiveBench matching contract lives only in orphaned matchers; production drifted.** `find_livebench`/`find_lmarena`/`find_aa` (`#L930/970/1000`) have **zero internal call sites** (production uses inline matcher `#L1166-1239` which omits stage-3 `variant_conflict`), but tests call them 12× — so they are test-referenced, not unreferenced. Prior "dead code" report was imprecise. Fix: port contract assertions onto the inline matcher, decide deliberately whether stage-3 belongs in production.
- **P2-B. "Tri-Verified" overstates live verification.** `partition_models_by_benchmark_coverage` (`#L1523-1524`) counts static catalog seeds (`lm_elo`, `aa_quality`) as arena/AA verification; 40 models labeled tri-verified though several lack a live match. Fix: label static-seed legs.
- **P2-C. Remain column unit inversion (ocheck).** `opencode_cost_benefit_analyzer.py#L798-812`: cached usage says 79% used, but every row displays green `21%` in a column titled "Remain" — read as 21% remaining. Internal math right; label/format/color invert semantics. Fix: show used% or correctly-label remaining%.
- **P2-D. `--json`/`--html`/`--podium` are no-ops; unconditional writes dirty tracked files** (both ocheck/ccheck). Confirmed in git status. Fix: honor flags to stop unconditional writes.
- **P2-E. `get_z_scores` zero-fills missing at cohort mean (z=0.0 → Q=78)** — `benchmark_common.py#L272-281`: exactly what the "never bank missing at cohort mean" invariant forbids; currently masked by consumer `is not None` guards, and it's why the aggregator reimplemented a correct `_z_scores` (`llm_benchmark_aggregator.py#L1385-1399`) — two divergent z-primitives. Also `stdev` vs `pstdev` inconsistency (`#L278` vs `#L432-434`).
- **P2-F. `_free_key` paid/free twin collisions.** 12 OR keys collide between paid model and `:free` twin; `setdefault` (`free_model_ranker.py#L502`) order-dependent → paid pricing can land on free rows.
- **P2-G. Stale divergence documentation.** `memory.md#L57-L71` + ocheck comment `#L54-L61` claim norm_id converts dots→hyphens and display_len differs by 1 on emoji — both false today (both re-export `bc.norm_id`; display_len provably identical). Only `_safe_float` `$`-rejection divergence is real. Fix: correct the docs; keep or explicitly annotate duplicated helpers (`_safe_float`/`_safe_int`/`_safe_int_round`/`display_len`/`color_cell` still duplicated in ocheck/ccheck; `_safe_int_round` lacks bc's `default=` param; `display_len` uses `\033` vs bc's `\x1b`).
- **P2-H. LiveBench cache-writer name collision.** ocheck/ccheck write `livebench_YYYYMMDD.csv` (`opencode…:1521-1526`) while bcheck writes `livebench_<epoch>.csv` (`#L1281-1282`); bcheck's loader globs both and mis-derives the categories-pair date. Fix: standardize on `livebench_YYYYMMDD.csv`.
- **P2-I. DST-naive scheduler** (`benchmark_sync_daemon.py#L208-214`): Europe/Berlin spring-forward computes 6.5h when real elapsed is 6h; self-corrects via ≤30s poll but untested. Fix: zone-aware scheduling + DST test.
- **P2-J. Baseline refresh swallows degradation** (`#L187-202` broad `except`, no per-feed failure tally); `bsync` undocumented in README while docstring claims "6 feeds" (actual: 8).
- **P2-K. `render_cli_table` extreme complexity: CC=86** (AST-measured), 285 lines at `llm_benchmark_aggregator.py#L1624`; also `build_universal_catalog` CC=68, `main` CC=34/depth 10. Violates CC≤10/depth≤3 (prior-audit CC claims for fcheck/scheck overstated — AST recount: fcheck main ≈75, scheck ≈52).

## P3 — Minor / Polish

- **P3-A. Parser truncation class (Scope 1 F1/F2)**: `parse_lmarena` block-end via escape-unaware `find("}]")` (`benchmark_common.py#L554-561`); `parse_aa` unescapes *before* bracket-scanning breaking quote tracking (`#L651, 672-689`). Any `}]` in a string field or `\"` in a name → `{}` → silent whole-source loss, swallowed by `except Exception: pass`. Fix: scan raw text, unescape only extracted segment; loud WARN when a found source parses to <1 models.
- **P3-B. NaN/`nan`/`inf` fabricate Q=99.9 or crash**: `_safe_float("nan")` → `nan` (`#L166-175`); `compute_capability_q(nan)` → 99.9, `get_z_scores([nan])` → ValueError. Fix: `math.isfinite` in `_safe_float`/`parse_price`; guard `get_z_scores`.
- **P3-C. Staleness helpers crash on missing/None paths** (`#L232-250`; FileNotFoundError/TypeError, reachable via `llm_benchmark_aggregator.py:1364`); `parse_openrouter` crashes on non-dict records; `find_aa/lm/livebench` stage-1 links non-reasoning variant when map sparse (because `non`/`reasoning` sit in `TIER_TOKENS` `#L97-101` despite memory contract classifying them as variant tokens).
- **P3-D. `compute_cost` never passes `cached_write_per_1m`** (`opencode_cost_benefit_analyzer.py:1619`) — docs cached-write prices don't enter per-request cost.
- **P3-E. Minor dead code**: `lcod` (`llm_benchmark_aggregator.py:1786`), `LIVEBENCH_URL` (`#L795`); WARN instead of `pass` on OR parse failure; HERE-hacks redundant behind tests; stale docstrings citing deleted `ocgo_check.py`.

## Verified Green (for the record)

- Offline-by-default structurally enforced (all network sites behind fetch paths; tests contain zero urlopen/requests/socket).
- `--check` never writes (all 5 checkers, live-smoked).
- Keys env-only (zero hardcoded credentials in tracked files; usage snapshots store only numeric `usage` object).
- Pure stdlib, no 3rd-party runtime deps.
- Staleness from filename `_YYYYMMDD`, UTC snapshot dates.
- fcheck lists OC/CLN free tiers only (10 rows, zero `[OR]`).
- ocheck `usage_note` provenance in every limits view.
- All 9 shared `compute_*` formulas identity-verified as the same benchmark_common objects in every checker (only the input branch diverges — see P1-A).
- atomic_write_text atomic + traversal-safe; variant_conflict semantics correct; cohort-split enforcement correct.
- Full test suite: **102 passed** (via `uv run pytest checkers/`).

## Remediation Roadmap

- **P1 batch** (fix first): A (ocheck guard) → B (OR pricing index) → C (parse_openrouter richness + strict is_free_model) → D (fetch validation) → E (daemon lock) → F (test isolation) → G (newest-only LiveBench).
- **P2 batch**: E (z-primitives) → A (matcher contract) → C (Remain column) → D (write flags) → F (twin collisions) → B (tri-verified labeling) → G/H/I/J/K.
- **P3 batch**: A (parser truncation) → B (NaN) → C (total helpers) → D/E (polish).

Prioritization note: P1-A, P1-B, P1-C, P1-G are correctness defects that silently corrupt *current* output; P1-D, P1-E, P1-F are data-integrity/ops defects that already fired in production. All P1s should land before trusting the daemon as an unattended 08:00 service.
