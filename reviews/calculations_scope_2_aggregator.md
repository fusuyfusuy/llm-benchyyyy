# Algorithmic and Data-Processing Audit of `llm_benchmark_aggregator.py`

## 1. Normalization & Cross-Matching Algorithms
- **`find_livebench`**: Effectively handles LiveBench's tier-based suffixes (`-max-effort`, `-preview`) by stripping tokens to find the base name, then executing a 3-stage fallback (exact match → tier-base match → variant safe-matcher `bc.variant_conflict`).
- **`find_lmarena` / `find_aa`**: Properly rely on the S2-C2 token-safe matcher from `benchmark_common` to prevent false cross-matching between completely different size/variant tiers.
- **Conclusion**: Highly robust normalization. Prevents provider prefix or tier suffix from breaking cross-referencing.

## 2. Score Aggregation & Composite Calculations
- **Z-Scores (`_z_scores`)**: Appropriately drops missing `None` values before computing mean and standard deviation. Prevents unbenchmarked models from being penalized with 0 values, evaluating them strictly on what metrics they do possess.
- **Composite Weights**: `calculate_composite_scores` tracks a running denominator `den` and computes `num / den`, ensuring that if a benchmark signal is missing, the surviving weights are mathematically renormalized perfectly. 
- **Discrepancy**: The theoretical weights (AA 45%, AA Coding 20%, AA Agentic 15%, LMArena 15%, LiveBench 20%) differ from the active implementation values: `lm_elo` (12.5%), `lm_cod` (12.5%), `aa_qual` (15%), `aa_cod` (12.5%), `aa_reas` (12.5%), `z_live` (17.5%). The sum is 0.825, but the ratio logic dynamically corrects it.

## 3. Cost & Price Calculation Models
- **Blended Pricing**: Fixes a strict 80/20 ratio via `(0.80 * pin) + (0.20 * pout)`, standardizing typical dense-prompt, sparse-completion agentic workloads.
- **Effective Cost Models**: The application of a capability threshold floor (`p_success`) feeding into a token multiplier (`t_mult`) accurately estimates real-world API consumption, preventing cheap but incapable models from appearing economical.

## 4. Outlier Handling & Numerical Stability
- **Numerical Stability**: Standard deviation of 0 is properly caught and defaulted to 1.0 to avoid `ZeroDivisionError` in cohorts with duplicate scores. 
- **Cache Staleness**: Checks snapshot age and yields visible warnings (`cache_staleness_note`) without fatally blocking the offline fallback execution path.

## Calibrated Scoring Matrix
- **Correctness & Mathematical Validity: 9/10** — Dynamic denominator renormalization and zero-division protection are excellent. Minus 1 point due to the spec vs code mismatch on signal weights.
- **Cross-source alignment: 9/10** — Strong handling of LiveBench suffixes.
- **Edge cases and failure modes: 8/10** — Excellent data normalization, but network fetch exceptions are logged to stderr rather than leveraging exponential backoff retry. 
- **Test coverage & verification proof: 6/10** — Lacks inline assert-based checks for edge-case composite verification.
