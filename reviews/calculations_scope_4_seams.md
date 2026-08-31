# Cross-Boundary Seam & Interface Audit

## 1. Free Tier Modeling & Semantic Integrity
**Files**: `checkers/opencode_cost_benefit_analyzer.py`, `checkers/commandcode_cost_benefit_analyzer.py`, `checkers/llm_benchmark_aggregator.py`
- **Seam Drift**: Handling of "Free" models (e.g., `ox-alpha-free`, `laguna-s-2.1-free`) across the architecture.
- **Mechanism**:
  - In `opencode` (L1814-1824) and `commandcode`, free pricing yields `v["effective_cost_per_request"] = None`.
  - The sorting and Pareto lambda `_eff_cost(r)` in `opencode` (L1863) and `commandcode` (L951) coerces `None` to a sentinel value: `return 999.0 if v is None else float(v)`.
  - **Impact**: Free models are treated as unknown cost (`999.0`). When pricing is `None` (unpriced/free tier), they are excluded from the Pareto frontier unless cost is explicitly identified as free ($0.0).
  - **Contrast**: `llm_benchmark_aggregator.py` (L1086-1090) calculates `effective_cost` for free tiers as `0.0`, dominating the Pareto frontier.

## 2. Interface & Contract Mismatches (Dictionary Shapes)
**Files**: `checkers/opencode_cost_benefit_analyzer.py`, `checkers/commandcode_cost_benefit_analyzer.py`, `checkers/benchmark_common.py`
- **Seam Drift**: `llm_benchmark_aggregator.py` operates on flat model dictionaries (`m["effective_cost"]`), allowing it to natively use `bc.compute_pareto_frontier(models_list)`. 
- **Mechanism**: `opencode` and `commandcode` use a nested dict structure (`r["value"]["effective_cost_per_request"]`).
- **Impact**: This forces `opencode` (L1850-1890) and `commandcode` (L945-965) to manually invoke `bc.pareto_dominated` inside custom sweeps rather than a unified entry point.

## 3. Mathematical Parse Seams
**Files**: `checkers/benchmark_common.py` vs `checkers/opencode_cost_benefit_analyzer.py` / `checkers/commandcode_cost_benefit_analyzer.py`
- **Seam Drift**: Deliberate divergence in `_safe_float`.
- **Mechanism**:
  - `benchmark_common.py` (L158-165) safely strips `$` and `,` before parsing `float(val)`.
  - `opencode` (L448-461) and `commandcode` (L338-350) explicitly abort and return `default` if the string starts with `$`: `if not s or s.startswith("$") ... return default` (noted in memory.md as S1-m3 deliberate design to separate currency parsing `parse_price` from bare float parsing).

## 4. Documentation vs Implementation
- **Result**: Exemplary. Documented formulas in CLI guide boxes, HTML headers, and README match runtime code identically (e.g., QVI: `log10(N_eff + 1) * (Q/70)^2.4 * 100`).

## 5. Test Coverage Blind Spots
- **Missing Tests**: `test_opencode_cost_benefit_analyzer.py` and `test_commandcode_cost_benefit_analyzer.py` test suite covers 91 scenarios, but lacks explicit assertions verifying free-tier Pareto frontier inclusion when `cost_per_request_usd` is `None` vs `0.0`.

## Remediation Roadmap
**Health Score**: 8.2 / 10.0 (Good - Minor invariant nuances on free-tier representation)
- **P1 (Free Tier Representation)**: In `ccheck` and `ocheck`, for models explicitly designated as free tier (e.g. `laguna-s-2.1-free`, `ox-alpha-free`), ensure `cost_per_request_usd` is cleanly distinguished between `0.0` (free, dominates cost) and `None` (unpriced/uncovered).
- **P2 (Contract Seams)**: Standardize Pareto frontier extraction adapter in `benchmark_common.py` to accept accessor functions `(cost_fn, q_fn)`.
- **P3 (Type Safety)**: Add `None` guards in `compute_p_success` and `compute_role_recommendations` in `benchmark_common.py` to prevent `TypeError` when unbenchmarked entries are passed directly.
