# Scope 2: OpenCode Go Analyzer Audit Report

**Date:** 2026-08-30
**Target Files:**
- `checkers/opencode_cost_benefit_analyzer.py`
- `checkers/test_opencode_cost_benefit_analyzer.py`

**Health Score:** 6.5 / 10 (Critical)

---

## 1. Executive Summary

The OpenCode Go catalog checker (`ocheck`) provides valuable cost-benefit, Pareto frontier, and usage limit calculations. However, this audit reveals critical variant-matching leaks, missing cost factors in token modeling, peer duplication, and CLI argument parity gaps.

### Key Invariant Breaches & Findings
1. **Variant Contamination (L583–584):** `find_or_for_ocgo` uses naive substring matching (`n in norm_id(oid) or norm_id(oid) in n`) rather than the standardized `bc.variant_conflict()` matcher. This risks misassociating base models with variant endpoints (e.g. `glm-5` matching `glm-5.3-max`).
2. **Missing Cached Write Cost Factor (L680–685):** `compute_cost` calculates input and output token pricing but completely omits `cached_write_per_1m` token pricing. For models with non-zero cache write rates, effective cost per task is underestimated.
3. **CLI Contract Drift (L1471–1495):** `ocheck` defaults to writing output files (`docs/data/ocgo_live.json` and `docs/reports/ocgo_cost_benefit.html`) on every run unless `--check` is explicitly given, unlike `bcheck`/`fcheck`/`scheck` which require explicit `--json`/`--html` flags. Furthermore, `--podium` and explicit output destination overrides are missing.
4. **Duplicate Shadowed Primitives:** As noted in Scope 4, `ocheck` re-implements `norm_id`, `parse_aa`, `parse_openrouter`, `display_len`, and `color_cell` rather than using `benchmark_common.py`.

---

## 2. Dimension Breakdown

| Dimension | Score | Assessment |
| :--- | :---: | :--- |
| **Domain Logic & Quota Math** | **8.0 / 10** | Quota math ($12/5h, $30/wk, $60/mo) and Pareto computations are solid, but cached write pricing is missing. |
| **Scraping & Cross-Matching** | **6.0 / 10** | OpenRouter cross-matcher uses naive substring matching instead of `variant_conflict`. |
| **CLI & Offline Parity** | **6.5 / 10** | Defaults to mutating files without explicit flags; lacks flag parity with other checkers. |
| **Output Rendering & Code Duplication** | **6.0 / 10** | Shadows `benchmark_common` utilities; peer rankers import from `ocheck`. |

---

## 3. Actionable Remediations
1. **Variant Decoupling:** Refactor `find_or_for_ocgo` to use `bc.variant_conflict()` to prevent model ID cross-contamination.
2. **Complete Cost Modeling:** Update `compute_cost` to incorporate cached token read/write pricing factors.
3. **Deduplicate into `benchmark_common`:** Remove local shadows of `norm_id`, `parse_aa`, `parse_openrouter`, and `display_len`.
4. **Align CLI Output Contract:** Bring `--json`, `--html`, `--podium`, and dry-run flags into parity with `bcheck`.
