# Master Architectural & Algorithmic Audit Report: Mathematical Scoring & Subscription Models

**Date:** 2026-09-01  
**Audit Protocol:** `boundary-review` (4 Parallel Pro Subagents)  
**Target Codebase:** `llm-benchyyyy` (`checkers/`)

---

## Executive Scorecard

| Scope | Subsystem / Focus | Health Score | Status | Key Findings |
| :---: | :--- | :---: | :---: | :--- |
| **Scope 1** | **Core Mathematical Scoring & Indices**<br>[`checkers/benchmark_common.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py) | **9.1 / 10** | **Green** | Robust zero-division and exponent overflow protection; strict clamping [40, 99.9]; QVI formula mathematically sound; minor `None` propagation sensitivity. |
| **Scope 2** | **Aggregator & Multi-Source Synthesis**<br>[`checkers/llm_benchmark_aggregator.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py) | **8.8 / 10** | **Green** | Dynamic weight renormalization when signals are missing; safe 3-stage LiveBench tier matcher; 80/20 blended pricing standard. |
| **Scope 3** | **Subscription Quotas & Cost Calculators**<br>[`checkers/commandcode_cost_benefit_analyzer.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py)<br>[`checkers/opencode_cost_benefit_analyzer.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py) | **9.5 / 10** | **Green** | Accurate multi-window quota scaling ($14/5h CC GOAT, $12/5h OpenCode Go); bottleneck detection algorithm; deterministic 3-tier tiebreaking sorting. |
| **Scope 4** | **Cross-Module Seams & Algorithmic Invariants**<br>Across all 6 modules & test suite | **8.4 / 10** | **Green** | Documented formulas match runtime code 1:1; identified seam nuance regarding `None` vs `0.0` cost representations on free-tier Pareto highlighting. |
| **Overall** | **System Architectural Health** | **8.95 / 10** | **EXEMPLARY** | Mathematically sound, resilient to edge cases, and deterministic. |

---

## Key Diagnostic Findings

### 1. Mathematical Rigor & Numerical Stability ([`checkers/benchmark_common.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py))
- **Quota Value Index ($\text{QVI}$)**:
  $$\text{QVI} = \log_{10}(N_{\text{eff}} + 1) \times \left(\frac{Q(\text{Cap})}{70.0}\right)^{2.4} \times 100$$
  - Guard clauses safely short-circuit non-positive, zero, or `None` inputs to `0.0` ([L334-L343](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L334-L343)).
  - Sensitivity analysis confirms $(Q/70)^{2.4}$ properly balances intelligence against raw request volume.
- **Logistic Pass Rate & Multiplier Bounds**:
  - `compute_p_success` defensively clamps the exponent to `[-50.0, 50.0]` ([L288](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L288)), preventing `OverflowError`.
  - `compute_token_multiplier` bounds $P_{\text{succ}} \ge 0.02$ ([L298](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L298)), guaranteeing the retry overhead multiplier cannot explode above $\approx 108.8$.
- **Agentic Value Index ($\text{AVI}$)**:
  - Denominator floor `log10(max(0.0, eff_cost) + 1.5)` guarantees minimum divisor $\approx 0.176$ ([L313](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L313)), eliminating division-by-zero on free tiers.

### 2. Multi-Source Normalization ([`checkers/llm_benchmark_aggregator.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py))
- **Z-Score Normalization**: Correctly purges missing `None` entries before computing cohort mean/std ([L998-L1012](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L998-L1012)).
- **Dynamic Weight Renormalization**: If a model lacks LMArena ELO or LiveBench scores, the surviving weights are renormalized dynamically via running denominator tracking ([L1040-L1070](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1040-L1070)), preventing artificial deflation.

### 3. Subscription Modeling & Quotas ([`ccheck`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py) / [`ocheck`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py))
- **Quota Scaling**:
  - Command Code GOAT: $14/5h, $35/wk, $70/mo pool; per-model 5h cap formula `$14 * (credits / 70)` ([ccheck:L786-L790](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/commandcode_cost_benefit_analyzer.py#L786-L790)).
  - OpenCode Go: $12/5h, $30/wk, $60/mo pool; per-model allowance `usage * 0.20` and `usage * 0.50` ([ocheck:L1621-L1627](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1621-L1627)).
- **Live Headroom Bottleneck Detection**: OpenCode Go usage analyzer calculates remaining capacity across rolling 5h, weekly, and monthly windows, selecting the active bottleneck constraint via `min()` ([ocheck:L1705-L1710](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1705-L1710)).
- **Deterministic Sort Tiebreakers**: `build_sort_key` consistently uses `(-primary, -capability_q, model_id)` with safe `-1` fallbacks for unscored models.

---

## Seam Auditing & Minor Invariant Discrepancies

1. **Free Tier vs Unknown Pricing Representation**:
   - In `ccheck` and `ocheck`, unpriced models and free models both set `cost_per_request_usd = None`. When evaluating Pareto frontier dominance, `_eff_cost` coerces `None` to `999.0` (treated as unknown cost).
   - In `bcheck`, free models set cost to `0.0`, dominating the Pareto curve.
   - *Recommendation*: Cleanly separate explicit Free tiers (`cost = 0.0`) from unbenchmarked/unpriced tiers (`cost = None`).
2. **Type Safety on Direct Helper Invocations**:
   - `compute_p_success(q_score)` and `compute_effective_cost(price, t_mult)` in `benchmark_common.py` assume float inputs. While higher-level loops sanitize `None` upstream, adding defensive `if val is None: return None` directly in these functions improves standalone resilience.
3. **Intentional Divergence in `_safe_float`**:
   - Documented in `.mimori/memory.md` (S1-m3): `benchmark_common.py` strips `$` while `ocheck`/`ccheck` reject `$` in bare float conversions to enforce use of `parse_price`. Verified intentional and non-breaking.

---

## Prioritized Remediation Roadmap

- [ ] **Batch 1 (Type-Safety & Free-Tier Resilience)**:
  - Add defensive `None` guards to `compute_p_success`, `compute_token_multiplier`, `compute_effective_cost`, and `compute_role_recommendations` in [`checkers/benchmark_common.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py).
  - Explicitly represent free tiers as `cost_per_request = 0.0` in `ccheck` and `ocheck` when marked free, distinguishing them from unpriced `None`.
- [ ] **Batch 2 (Test Coverage Expansion)**:
  - Add unit tests for free-tier Pareto frontier inclusion and standalone `None` input handling in [`checkers/test_benchmark_common.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/test_benchmark_common.py).
- [ ] **Batch 3 (Docs & Cleanliness)**:
  - Keep docstrings and metric guides fully synchronized with latest formula calibrations.
