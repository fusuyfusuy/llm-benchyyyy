# Scope 2 — bcheck Universal Aggregator Audit (`llm_benchmark_aggregator.py`)

- **Auditor:** Scope 2 Auditor (Universal Aggregator — bcheck)
- **Boundary:** `checkers/llm_benchmark_aggregator.py` (2552 lines) + `checkers/test_llm_benchmark_aggregator.py` (532 lines); `checkers/benchmark_common.py` read as needed (shared `diff_model_catalog`, `load_previous_snapshot`, `find_*_for_model`, `variant_conflict`, `norm_id`, parse_*).
- **Method:** full read of the aggregator + test file; targeted reads of benchmark_common; offline probes against `docs/data/raw/` snapshots (livebench_20260901.csv, lmarena_20260901.html, artificial_analysis_20260901.html, openrouter_models_20260901.json); AST cyclomatic-complexity pass; grep call-site verification for `find_*`. No subagents. No edits made.
- **Test suite:** `26 passed` (`pytest checkers/test_llm_benchmark_aggregator.py -q`).

## Verdict

**Health score: 7.2 / 10 (Moderate band).** The statistical core honors every documented invariant — the AA live/static cohort split, missing-signal exclusion (never banked at z=0.0), weight renormalization, strict LMArena no-borrow, 3-stage LiveBench tier contract, offline-by-default, diff-before-pool-filter, and atomic baseline writes are all **verified correct** against real snapshots. Two **silent data-integrity defects** keep this out of the Minor band: the OpenRouter pricing join can never fire (0/425 keys match, 263 rows carry fabricated default prices), and the LiveBench loader merges **all** dated snapshots instead of the newest — injecting an 8-month-old January 2026 `mimo-v2-pro` row as a live 2026-09 signal. A third structural issue: the `find_livebench`/`find_lmarena`/`find_aa` matchers are orphaned from the production pipeline but still exercised by tests, and the inline matcher in `build_universal_catalog` has already drifted from their contract.

| Severity | Count |
|---|---|
| P1 (Critical) | 3 |
| P2 (Moderate) | 4 |
| P3 (Minor) | 4 |

All three prior-audit Criticals (scope2_aggregation.md) are **confirmed fixed** in the current tree: `if do_fetch:` → `if fetch:` (now `:1280`, `:1313`, `:1341`), substring-containment variant matching removed from the aggregator (inline matcher uses exact/base lookups only), and `save_baseline` now writes via `bc.atomic_write_text` (`:2423`).

---

## Prior-audit claims re-verified (do not trust blindly)

1. **`find_livebench`/`find_lmarena`/`find_aa` "orphaned dead code" — PARTIALLY TRUE.** Grep across `checkers/` shows the aggregator's own module has **zero internal call sites** for these three (only the defs at `:930`, `:970`, `:1000`; production signal attachment is the inline matcher at `:1166-1239`). However, `test_llm_benchmark_aggregator.py` calls them **12 times** (`:93,:96,:108,:111,:114,:116,:124,:127,:148,:151,:177`) — the tests lock in the LiveBench tier/variant contract (incl. the `mimo-v2-pro` never-links rule). So they are *production-orphaned but test-referenced*: deleting them requires migrating the contract assertions, and they must not be reported as fully unreferenced.
2. **`render_cli_table` extreme complexity — CONFIRMED.** AST cyclomatic complexity **CC = 86**, depth 4, 285 lines (`:1624-1908`). Also extreme: `build_universal_catalog` CC = 68 (`:1040-1241`), `render_html_report` CC = 39, `main` CC = 34 with nesting depth 10 (`:2431-2547`).
3. **`--fetch` NameError regression — FIXED** (verified `if fetch:` at `:1280/:1313/:1341`, WARN prints instead of bare `except: pass`).

---

## P1 — Critical findings

### P1-1 — OpenRouter pricing join is structurally dead: 0/425 keys match, 263 rows silently priced at fabricated defaults

**Where:** `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L888` (`load_openrouter_pricing_data`, keying at `:903`) and the join lookups at `:1093-1095` (AA fallback), `:1123` (LiveBench rows), `:1148` (LMArena rows).

**Mechanism (empirically proven on `openrouter_models_20260901.json`):** every one of the 425 OpenRouter ids carries a provider prefix + path (`ibm-granite/granite-4.2-8b`, `tencent/hy4-preview`, `inclusionai/ling-3.0-flash-fin:free`). `load_openrouter_pricing_data` keys the index with `bc.norm_id(mid)`, and `norm_id` strips `/` **and the provider prefix** — producing fused keys like `tencenthy4-preview`. The catalog join sites look up **bare model slugs** (`bc.norm_id(slug)` of `hy4-preview`, `glm-5.3`, …). No catalog key can ever equal a fused provider+id key: **0 of 625 AA slugs and 0 of 541 api catalog rows hit the OR index** (measured). Result: 270 of 541 api rows (263 of the benchmarked `models` list — e.g. JT-35B-Flash, Gemini 2.0 Flash Thinking Experimental, Qwen2.5 Coder, Sonar Reasoning) fall through to the hard-coded `1.0 / 3.0` fallback (`:1094-1095`, `:1130-1131`, `:1155-1156`). Blended price → `effective_cost` → AVI/BFI/Pareto are all derived from these fabricated prices, so ranks and gold-row highlighting shift silently. No unit test exercises the OR join (only `test_build_universal_catalog` counts rows).

**Fix:** strip the provider prefix when keying: index on `bc.norm_id(mid.split("/")[-1].split(":")[0])` (the suffix — matching `find_or_for_model`'s suffix logic in benchmark_common `:840-843`), and also index full-id so nothing regresses; add a unit test that builds a catalog with a prefixed OR payload and asserts the real price lands on the upstream row.

### P1-2 — LiveBench loader merges ALL dated snapshots; an 8-month-old row is served as a live 2026-09 signal

**Where:** `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1261` — `for p_csv in csv_matches:` (all files) with `out.update(data)`, vs the newest-only `matches[-1:]` used by `load_lmarena_data` (`:1302`) and `load_aa_data` (`:1330`).

**Mechanism (proven):** `docs/data/raw/` holds six livebench CSVs including `livebench_20260108.csv` (a January snapshot). The 2026-09-01 file contains **no** mimo rows, yet the merged `live_map` contains `mimo-v2-pro` (overall 58.35) — it survives only from the stale January file. `build_universal_catalog` then attaches that January record to the catalog's `mimo-v2.5` row via its `live_aliases` entry `mimo-v2-pro` (`:776`), so the current offline report shows `MiMo-V2.5 LiveBench 58.35%` as a verified live signal and the model lands in the **tri-verified** cohort (`partition` counts confirmed: tri_verified=40 with mimo-v2.5 among them). Same mechanism silently resurrects any other model that vanished from newer leaderboards. The three loaders are inconsistent by construction.

**Fix:** newest-only selection for LiveBench like the other two loaders (`matches[-1:]`, plus skip `cost` files), or merge only snapshots within CACHE_TTL_H. Re-run the offline report and re-assert `test_build_universal_catalog_includes_upstream_models` / partition counts.

### P1-3 — Production matcher and test matcher have already drifted; the "3-stage" LiveBench contract is enforced only in dead code

**Where:** dead-but-tested `find_livebench` `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L930` (variant_conflict stage `:963-966`) vs production inline matcher in `build_universal_catalog` `:1166-1239` (exact → tier-base → `strip_effort_suffix`-base only, **no variant_conflict stage**).

**Mechanism:** the aggregator's own signal attachment (`:1166-1239`) implements only 2 of the 3 documented LiveBench stages — the `variant_conflict` stage exists solely in `find_livebench`, which production never calls. Today the two paths happen to agree on the curated aliases (catalog-declared aliases carry the linking), but any future catalog row without an alias for a variant-suffixed LiveBench listing will get **no** LiveBench signal, while the test-only matcher would have linked it — or vice versa if the inline path were ever given fuzzy fallback. The memory.md contract ("3 stages exact → tier-stripped base → variant_conflict") is enforced by tests that run against the *orphaned* implementation, so the contract is green while production behaves differently. This is the accurate statement of the "dead code" finding: not unreferenced, but **drifted duplication**.

**Fix (choose one):** (a) delete `find_livebench`/`find_lmarena`/`find_aa` and port their assertions onto the inline matcher (add the variant_conflict stage there deliberately, or document its intentional absence); or (b) re-wire `build_universal_catalog` to call the `find_*` functions. Either way the contract must live on the code path that runs.

---

## P2 — Moderate findings

### P2-1 — `render_cli_table` extreme cyclomatic complexity (CC = 86)
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1624` — 285 lines, CC 86 (measured by AST). One function owns banner, diff notices, adaptive-width header selection, medal computation, per-row color/format branching, three render modes, sub-table orchestration, metric guide, and role recommendations. Also `build_universal_catalog` CC = 68 (`:1040`), `main` CC = 34 / depth 10 (`:2431`). No correctness bug found, but each prior audit's fixes landed here, and any future branch (e.g. a 13th column) is where regressions will hide. Suggest extracting row-cell construction and the header/width selection into helpers.

### P2-2 — "Tri-Verified" overstates live verification: static seeds count as verified signals
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1523` — `has_arena` is true whenever `base_metrics.lm_elo` exists, and `has_aa` whenever `aa_quality` exists; the catalog's **static seeds** (e.g. `lm_elo` 1435, `aa_quality` 96.0 for Opus 5) therefore count as arena/AA verification. In the default offline run 40 models are "tri-verified" although several carry no live match for one or two sources. The LiveBench leg is genuinely live (`has_live` requires the `livebench` record), but the label overstates the other two legs. Not a crash — a reporting-accuracy concern for a headline metric.

### P2-3 — Stale hardcoded insights prose in the Markdown report
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L2203` — "## 5. Key Insights" hardcodes model-specific claims ("Claude Fable 5 (LiveBench 83.4%)", "DeepSeek V4 Flash (AVI 538.9)") that are not derived from the computed rows; they will silently go stale as the catalog and scores move. Compute these from `primary_models` or drop the section.

### P2-4 — LiveBench staleness check pattern can key on the cost file
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1371` — pattern `*livebench*20*.csv` matches `livebench_cost_*.csv` too (the loader explicitly skips cost files at `:1264`, the staleness probe does not). Currently harmless (`min` age picks the newest), but a cost file dated later than the real CSV would silently suppress the staleness WARN. Align the pattern with the loader's skip rule.

---

## P3 — Minor findings

1. **Unused locals/constants:** `lcod = bm.get("lm_coding", "-")` at `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1786` is never read; `LIVEBENCH_URL = "https://livebench.ai"` at `:795` is never referenced (fetch uses `LIVEBENCH_CSV_URL`/`LIVEBENCH_CAT_URL`).
2. **OR parse failure is silent:** `load_openrouter_pricing_data` wraps the whole loop in `except Exception: pass` (`:908-909`); a single non-numeric `pricing.prompt` string would discard the entire 425-row index with no warning. (Current snapshot is all numeric strings, so the fuse is unlit — but the parse is the one piece of the join that does work.)
3. **`calculate_composite_scores` coerces prices with bare `float()`:** `:1473-1474` (`float(m.get("price_in", 0.0))`) raises on any non-numeric price type. Today all producers emit numbers, but a malformed upstream row (or a string like `"$5"`) would crash the whole run rather than degrade. Use `bc._safe_float`-style guards.
4. **`_z_scores` len-1 semantics:** `:1393-1394` returns `0.0` for a single valid value — a one-model cohort scores at Q=78.0 neutral. Consistent with `compute_capability_q(None)=78.0` and acceptable, but worth an explicit comment that a 1-row cohort is a degenerate distribution by design.

---

## Invariant verification (all green unless noted)

| Invariant | Result | Evidence |
|---|---|---|
| AA live/static never mixed in one z-distribution | ✅ | `:1425-1434` splits on `aa_live_quality` presence; live cohort (453 models, 1.0–63.1) and static cohort (5 models, 80.5–93.5) never share a distribution (measured) |
| Missing signals never banked at cohort mean (z=0.0) | ✅ | `_z_scores` `:1392-1399` keeps `None`; weighted sum skips + renormalizes `:1456-1462` |
| `_z_scores` zero-variance | ✅ | `std_val == 0.0 → 1.0` `:1397-1398`; `[85,85,85] → [0.0,0.0,0.0]` verified |
| LiveBench 3-stage tier contract (exact → tier-stripped → variant_conflict) | ⚠️ P1-3 | enforced only in test-referenced orphan `find_livebench`; production inline matcher omits stage 3 |
| Tier tokens ≠ model-variant tokens (mimo-v2-pro never auto-links) | ✅ | `LIVEBENCH_TIER_TOKENS` `:916-919` excludes pro/mini/nano/codex; test `:127` asserts None; production link of `mimo-v2.5`→`mimo-v2-pro` is via **catalog-declared alias** `:776` (intentional), not matcher inference |
| LMArena strict no-borrow | ✅ | inline matcher `:1186-1206` exact/base only; `variant_conflict` guards in `find_lmarena` `:994-996`; test `:151` asserts None |
| Offline by default; `--fetch` only writes; `--check` never writes | ✅ | `--fetch` gates snapshot saves `:1276-1290` and `save_baseline` `:2486-2488`; no write path otherwise |
| Diff catalog-wide BEFORE `--pool` filtering | ✅ | `:2482-2496` — diff on full `models`, filter after |
| `first_seen` carry-over catalog-wide | ✅ | `diff_model_catalog` `benchmark_common.py:1739-1782`; round-trip test `:291-312` |
| Baseline written atomically | ✅ | `bc.atomic_write_text` `:2423` (prior C3 fixed) |
| Price fallback (OR join) | ❌ P1-1 | structurally dead — 0/425 join hits |
| Coverage partitioning (tri/missing/single) | ✅ semantics, ⚠️ P2-2 | counts correct (40/31/15/5/461 measured); static seeds inflate "verified" claim |
| CC ≤ 10, depth ≤ 3, fail-fast | ❌ | `render_cli_table` CC 86; `build_universal_catalog` CC 68; `main` depth 10 |

---

## Remediation plan

**P1 (do first):**
1. `load_openrouter_pricing_data`: key the OR index on the provider-stripped suffix (`norm_id(mid.split("/")[-1].split(":")[0])`), keep full-id keys as a secondary index; add a unit test proving a prefixed OR payload prices an upstream row. (~`llm_benchmark_aggregator.py:888-910`, `:1093-1156`)
2. `load_livebench_data`: newest-only snapshot selection (`matches[-1:]`) mirroring `load_lmarena_data`/`load_aa_data`; drop stale `livebench_20260108.csv` from the merge; re-assert the offline report's mimo row. (~`:1261-1274`)
3. Resolve the matcher duplication: delete `find_livebench`/`find_lmarena`/`find_aa` and port their contract assertions onto the inline `build_universal_catalog` matcher (deciding deliberately whether stage-3 variant_conflict belongs in production), or re-wire production to call them. (~`:930-1027`, `:1166-1239`; tests `test_livebench_parsing`/`test_version_safe_matching`/`test_lmarena_parsing_and_matching`/`test_aa_parsing_and_matching`)

**P2:**
4. Split `render_cli_table` into banner/header/row/guide helpers (target CC ≤ 40). (`:1624-1908`)
5. Make coverage "verified" honest: label static-seed legs in `partition_models_by_benchmark_coverage` (e.g. a `tri_verified_live` vs `tri_verified_seeded` split) or track per-source provenance. (`:1513-1545`)
6. Derive the Key Insights section from computed rows. (`:2203-2210`)
7. Exclude `livebench_cost_*` from the staleness probe pattern. (`:1371`)

**P3:** drop `lcod`/`LIVEBENCH_URL`; WARN (not `pass`) on OR parse failure; `_safe_float`-guard price coercion in `calculate_composite_scores`; document `_z_scores` degenerate-1-row semantics.

*Generated by the Scope 2 bcheck auditor. All measurements are offline against `docs/data/raw/` snapshots as of the audit run; no files modified.*
