# Architectural Audit: Scope 3 — Quota & Cost Calculations

**Target Subsystems:**
- `checkers/commandcode_cost_benefit_analyzer.py` (`ccheck`)
- `checkers/opencode_cost_benefit_analyzer.py` (`ocheck`)

**Audit Dimensions:** Correctness & Mathematical Validity, Precision & Rounding, Edge Cases, Verification Proof.

## Executive Scorecard

| Score Band | Severity | Dimension evaluated | Findings |
| :---: | :---: | :--- | :--- |
| **9.5** | Exemplary | Correctness & Math Validity | Token cost and quota limits scale accurately. Zero-division guards are robust (`cost_req > 0`). |
| **9.0** | Minor | Precision & Rounding | Internal floating-point state is maintained; `_safe_int_round()` is correctly applied just before UI presentation. |
| **9.5** | Exemplary | Edge Cases & Fallbacks | Free-tier handling (`cost=None`, `usage=None`) is structurally sound, bypassing cost-dependent computations correctly. |
| **9.5** | Exemplary | Sorting & Stability | `build_sort_key` is strictly deterministic. Missing score fallbacks to `-1` safely push unbenchmarked models to the tail without crashing. |

---

## Detailed Findings & Citations

### 1. Token Cost Models (`compute_cost`)
The `compute_cost` function is identically implemented in both modules to accurately calculate the baseline API cost of one standard task.
- **Formula:** `(in * est_in / 1M) + (out * est_out / 1M) + (ca * est_ca / 1M) + (cw * est_cw / 1M)`
- **Mathematical Correctness:** Excellent. It properly normalizes pricing per 1M tokens without floating-point overflow.
- **Edge Cases:** Properly handles `None` limits by returning `None` immediately, escaping `TypeError` exceptions.
- **Citation:** 
  - [ocheck:L439-445](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L439-L445)
  - [ccheck:L329-335](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L329-L335)

### 2. Quota & Limit Models
The translation of monthly dollar quotas into shorter windows is mathematically sound.
- **CC GOAT Caps:** `$14/5h, $35/wk, $70/mo`. Scaled via `credits * (14/70)` (0.2) and `credits * (35/70)` (0.5).
  - [ccheck:L786-790](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L786-L790)
- **OpenCode Go Caps:** `$12/5h, $30/wk, $60/mo`. Scaled via `usage * 0.20` and `usage * 0.50`.
  - [ocheck:L1621-1627](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1621-L1627)
- **Request calculation (`cap / cost_req`):** Correctly guarded with `if cost_req and cost_req > 0`, neutralizing division-by-zero risks for cost-free models or anomalous API pricing responses.

### 3. Live Usage & Remaining Headroom (OpenCode Go)
Headroom calculations dynamically locate the most constrained time window.
- **Algorithm:**
  - Extracts `% used` for `rolling`, `weekly`, and `monthly` windows.
  - Remaining % = `max(0.0, 100.0 - pct_used)`.
  - Dollar cap remaining = `cap * pct_rem / 100.0`.
  - Overall bottleneck is correctly assigned via `min(remaining.values())` and `min(remaining_req.values())`.
- **Validation:** Handles missing usage keys gracefully by discarding that window without tanking the execution.
- **Citation:** [ocheck:L1678-1711](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1678-L1711)

### 4. Sorting & Ranking Algorithms (`build_sort_key`)
- **Algorithm:** `lambda r: (-_primary_metric(r), -_cq(r), r["model_id"])`
- **Stability:** Tiebreakers ensure completely deterministic UI ordering. The fallback to `-1` for missing scores prevents runtime errors and automatically sinks free or unbenchmarked tier entries to the bottom of sorted performance leaderboards.
- **Citation:** [ccheck:L602-L630](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L602-L630)

### 5. Role Recommendations & Leverage Multiplier
- **Algorithm:** `leverage = usage / 10.0` (or `credits / 10.0`).
- **Validity:** The math accurately computes the monetary advantage ratio of utilizing the full API credit cap against a presumed $10 base cost.
- **Citation:** [ocheck:L1670-L1672](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1670-L1672)

---

## Executive Summary
The quota models and token cost algorithms across both `ccheck` and `ocheck` are **mathematically correct, resilient to edge cases (division by zero, NoneTypes, missing benchmarks), and deterministic**. Tiebreaking strategies safely quarantine untested tiers. No architectural vulnerabilities or calculation bugs were identified in these boundary modules.
