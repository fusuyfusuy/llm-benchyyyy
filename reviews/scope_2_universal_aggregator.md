# Scope 2: Universal LLM Benchmark Aggregator (`bcheck`) - Audit Report

## 1. Executive Summary

- **Health Score**: 8.2 / 10.0 (Moderate)
- **Invariant Breaches**:
  - **Dead Code Paths**: Legacy version-safe matching functions (`find_livebench`, `find_lmarena`, `find_aa`) are implemented and tested, but entirely bypassed by the new O(1) dictionary logic in `build_universal_catalog`.
  - **Duplication & Complexity**: Massive code duplication and cyclomatic complexity exist across the various table and report renderers (CLI, MD, HTML).
- **Top Findings**:
  - `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L930`: `find_livebench` (and peers) are dead code. They exhibit O(N^2) string-matching complexity internally but are orphaned from the main control flow.
  - `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1069`: `build_universal_catalog` correctly avoids the O(N^2) matching trap by pre-indexing maps, making lookups O(1).
  - `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1403`: `_z_scores` correctly implements zero-variance (`std_val == 0.0`) and single-element protection.
  - `file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py#L1642`: High cyclomatic complexity in `render_cli_table` (~300 lines) with inline sub-table rendering strings and duplication of coloring logic.
- **Actionable Remediations**:
  1. **Prune Dead Code**: Delete the unused `find_livebench`, `find_lmarena`, and `find_aa` functions to reduce cognitive load and remove false-positive O(N^2) concerns.
  2. **Refactor Renderers**: Extract common model data formatting (e.g., metric stringification, badge assignment, and coloring) into a reusable helper function to reduce duplication between `render_cli_table`, `render_sub_table_cli`, `render_markdown_report`, and `render_html_report`.
  3. **Update Test Suite**: Remove or repurpose the unit tests that specifically target the orphaned `find_*` functions in `test_llm_benchmark_aggregator.py` to test the actual matching behavior in `build_universal_catalog`.

---

## 2. Dimensional Analysis

### 2.1 Correctness
- **Mathematical Integrity**: The composite capability formulas (Q, P_succ, T_mult, AVI, FGI, BFI) are structurally sound and imported correctly from `benchmark_common.py`. `_z_scores` implements correct zero-variance protection (`std_val == 0.0 -> 1.0`) and filters out `None` values or invalid types. Missing signals are correctly excluded from the weighted sum, and the remaining weights are renormalized appropriately so that missing metrics do not drag down a model's score.
- **Tri-Verified Partitioning**: The `partition_models_by_benchmark_coverage` function correctly separates models into `tri_verified`, `missing_livebench`, `missing_lmarena`, `missing_aa`, and `single_source` cohorts based on strict boolean checks.
- **Master Catalog Normalization**: `build_universal_catalog` uses extensive and correct alias binding logic (live, lm, aa aliases) and strips effort suffixes to link downstream metrics to upstream canonical models.

### 2.2 Robustness
- **Missing Benchmark Handling**: The `calculate_composite_scores` function properly handles missing benchmarks by omitting them from the z-score calculations and the weighted denominator, ensuring no model is unfairly penalized (or rewarded via the cohort mean) for missing data.
- **Input Tolerance**: The CLI renderer gracefully handles missing or string-typed metrics (e.g., `isinstance(spd, (int, float))`) defaulting to safe string conversions or `0` when required. Price fallbacks are securely nested (e.g., checking OpenRouter pricing when upstream Artificial Analysis omits costs).

### 2.3 Performance
- **Catalog Construction Complexity**: The main build function, `build_universal_catalog`, implements highly efficient O(1) dictionary lookups (`live_norm`, `lm_norm`, `aa_norm`) by pre-computing normalized keys. This resolves potential O(N^2) regex normalization bottlenecks.
- **Terminal Render Efficiency**: The `render_cli_table` dynamically adapts column visibility via `is_slim = slim if slim is not None else (term_cols < 120 and not wide)`, safely dropping `Arena`, `Speed`, and `Price` metrics on smaller viewports.

### 2.4 Cleanliness & Modularity
- **Dead Code Paths**: The functions `find_livebench`, `find_lmarena`, and `find_aa` represent over 100 lines of dead code. They are tested extensively but never executed in the main catalog construction loop.
- **Cyclomatic Complexity**: `render_cli_table` suffers from extreme cyclomatic complexity and monolithic design. Display logic, ANSI color computation, partition extraction, and table bordering are intertwined. `render_sub_table_cli`, `render_markdown_report`, and `render_html_report` duplicate much of this value-extraction and formatting logic.
