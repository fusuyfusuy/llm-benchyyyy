# Architectural Audit: Scope 1 — Core Mathematical Formulas & Scoring Models

**Target File:** `checkers/benchmark_common.py`
**Audit Dimensions:** Correctness & Mathematical Validity, Edge-Case Robustness, Performance & Complexity, Test Coverage.

## Executive Scorecard

| Score Band | Severity | Dimension evaluated | Findings |
| :---: | :---: | :--- | :--- |
| **9.0** | Minor | Correctness & Math Validity | Formulas are mathematically sound with excellent zero-division guards and safe clamping. Small divergences from prompt spec (e.g. linear vs logistic for capability Q, log offset +1.5 vs +1.05 in AVI). |
| **8.0** | Moderate | Edge-Case Robustness | Excellent numerical stability (exponential clamp to [-50, 50], denominator floors). However, several functions (`compute_p_success`, `compute_effective_cost`, `compute_role_recommendations`) raise `TypeError` if passed `None` instead of sanitizing to defaults. |
| **9.8** | Exemplary | Performance & Complexity | O(N) operations throughout; builds and transforms lists in single passes using optimized Python builtins. |
| **8.8** | Minor | Test Coverage | High unit test coverage in `test_benchmark_common.py`, with edge cases like 0 std covered. Missing direct assertion suites for `None` propagation in `compute_p_success` and `compute_pareto_frontier`. |

---

## Detailed Findings & Line Citations

### 1. `get_z_scores` ([L264-L273](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L264-L273))
- **Correctness & Math**: Valid standard deviation calculation.
- **Robustness**: Properly handles empty lists and 1-element lists, short-circuiting to return `[0.0]`. Correctly handles a 0.0 standard deviation (identical elements) by setting `std_val = 1.0`, effectively yielding `0.0` z-scores. Properly skips non-numeric and `None` entries when building the calculation set.
- **Performance**: O(N) operations, utilizing `statistics` built-ins. Optimal.

### 2. `compute_capability_q` ([L276-L281](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L276-L281))
- **Correctness & Math**: The implementation uses linear scaling via `78.0 + (cz * 8.5)`, with a scaling factor of 8.5. 
- **Robustness**: The hard clamps `[40.0, 99.9]` operate as expected to contain bounds. Mathematically stable.

### 3. `compute_p_success` ([L284-L291](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L284-L291))
- **Correctness & Math**: Implements the standard logistic function `1 / (1 + e^-k(x-x0))`. Midpoint is accurately 72.0 with slope 0.12.
- **Robustness**: The exponent is defensively clamped to `[-50.0, 50.0]`. This correctly prevents `math.exp(exponent)` from `OverflowError` (which occurs in Python near 709).
- **Edge cases**: Will fail with a `TypeError` if `q_score` is `None`.

### 4. `compute_token_multiplier` ([L294-L301](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L294-L301))
- **Correctness & Math**: Accurately maps the specified retry formula `(1 + α * (1 - P)) / P`.
- **Robustness**: Asymptotic behavior as `p -> 0` is safely bounded by clamping `p_succ` to a minimum of `0.02`. The maximum possible multiplier is thus hard-capped at ~108.8. As `p -> 100`, it correctly resolves to a 1.0 overhead multiplier.

### 5. `compute_effective_cost` ([L304-L306](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L304-L306))
- **Correctness**: Accurate straightforward multiplication.
- **Robustness**: `blended_price = 0.0` (free tier models) will correctly map to `0.0`. Missing values (`None`) will cause an uncaught `TypeError`.

### 6. `compute_avi` ([L309-L314](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L309-L314))
- **Correctness & Math**: Formula executes `Q^2.2 / (100 * log10(max(0.0, effective_cost) + 1.5))`.
- **Robustness**: The +1.5 floor correctly ensures the denominator evaluates to at least ~0.176 (log10 of 1.5), guaranteeing stability and protection against zero-division for `eff_cost=0.0`.

### 7. `compute_fgi` ([L317-L323](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L317-L323)) & 8. `compute_bfi` ([L326-L331](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L326-L331))
- **Correctness**: Both models map precisely to their target formulas.
- **Robustness**: Safe fractional exponentiation. A negative value inside a fractional power would yield a complex float in Python, but both functions use `max(0.0, ...)` gates protecting both exponentiation and denominator zero-divisions.

### 9. `compute_qvi` ([L334-L343](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L334-L343))
- **Correctness**: Maps exactly to the formula `log10(N_eff + 1) * (Q / 70.0)^2.4 * 100`.
- **Robustness**: Exceptionally robust handling for missing/negative inputs (`if q_score is None or n_eff_tasks is None or n_eff_tasks <= 0: return 0.0`). The highest standard of edge-case protection in the file.

### 10. `pareto_dominated` & `compute_pareto_frontier` ([L346-L392](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L346-L392))
- **Correctness**: Reliable logic for defining Pareto boundaries across cost vs capabilities.
- **Robustness**: The relative cost diff utilizes `max(cost_epsilon, a_cost)` specifically resolving the free-tier division-by-zero vulnerability. However, in `compute_pareto_frontier`, `b.get("capability_q", 0)` only falls back to 0 if the key is missing entirely; if the key is present but maps to `None`, this yields `None`. In Python 3, the subsequent `b_q >= a_q` check can raise a `TypeError` if not sanitized upstream.

### 11. `compute_role_recommendations` ([L1375-L1504](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L1375-L1504))
- **Correctness**: Employs an exact multi-metric linear weighted model using unified Z-scores.
- **Robustness**: Features back-filling (mapping missing coding and reasoning indexes to `f["q"]`) is highly robust. However, `inv_log_costs = [-math.log10(max(0.00001, f["eff_cost"])) ...]` is vulnerable to a `TypeError` if a model is entirely missing pricing data and reports `None` for `eff_cost`.

### 12. `compute_column_medals` ([L1001-L1022](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L1001-L1022))
- **Correctness**: Performs correct algorithmic top-3 slicing.
- **Robustness**: Defers entirely to the caller via the `filt` functional argument to sanitize `None` fields. If a caller omits the filter, Python's `sorted()` function will crash with a `TypeError` when comparing mixed float/None values.
