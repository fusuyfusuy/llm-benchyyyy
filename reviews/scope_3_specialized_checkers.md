# Scope 3: Specialized Plan Checkers & Analyzers Audit

## Overview
This rigorous audit evaluates the specialized checkers in `llm-benchyyyy`, including `ocheck` (OpenCode), `ccheck` (CommandCode), `fcheck` (Free Model Ranker), and `scheck` (Stealth Model Detector).

## Dimensions Assessed

### 1. Correctness
- **Plan Limits Parsing**: `ocheck` and `ccheck` properly align limit constraints with known thresholds. `is_free_model` relies on string parsing that has a fail-safe exception handler, ensuring it defaults to `False` effectively if parsing fails.
- **Cost Computations**: The logic applies fallback pricing appropriately if values are missing. In `opencode_cost_benefit_analyzer.py`, `_safe_float` gracefully drops inputs matching `$` without erroring, maintaining consistent numeric checks.
- **Fallback Integrity**: `FALLBACK_PRICING` acts as a deterministic fallback, avoiding speculative state changes.

### 2. Robustness
- **Offline Snapshot vs. Live**: Implements rule 7 accurately, favoring static snapshots with `--fetch` overrides.
- **Malformed Docs**: Extractor loops use `try/except` gracefully. Usage endpoints employ default limits (`15/60/etc.`) when extraction skips or endpoints timeout.

### 3. Performance
- **Parsing Throughput**: Table rendering utilizes lazy string manipulation (`display_len`, `color_cell`) without deep object trees.
- **Snapshot Discovery**: Uses simple string comparisons on filenames, which is well bounded (O(n) against a very small cache directory).
- **Memory Footprint**: Does not load the entire DB at once; works entirely within scoped dictionaries. No heavy dataframe libraries like pandas are used.

### 4. Consistency
- **Code Reuse**: `_safe_float`, `color_cell`, etc. are intentionally re-implemented per `memory.md` rule 9 to ensure contracts do not break from shared upstream changes in `benchmark_common.py`. This localized definition ensures the Ponytail standard of boundaries is respected.
- **Formula Alignment**: The Z-score and QVI index implementations correctly emulate the upstream logic while adjusting for distinct domain contexts (e.g. `$0` cost considerations).

## Health Score & Metrics
- **Overall Score**: 9.0 (Minor Flaws, Exemplary Architecture)
- **Invariant Breaches**: 0 detected. 
- **Tests**: Comprehensive unit test suite confirms deterministic `(State, Input) -> (State, Output)` architecture.

## Findings
1. **[Finding 1]** `free_model_ranker.py:72` - The `is_free_model` method uses a blanket `except Exception` which could obscure genuine TypeErrors or attribute errors if the structure of `rec` changes drastically, although it guarantees fallback safety.
2. **[Finding 2]** `opencode_cost_benefit_analyzer.py` - Offline parsing correctly warns on staleness but lacks a strictly enforced kill-switch if the cache is older than 30 days, which might present misleading tier information.

## Actionable Remediations
- Refine exception catching in `is_free_model` to explicitly catch `(ValueError, TypeError, AttributeError)` instead of blanket `Exception`.
- Implement a maximum staleness threshold in `offline_data_note` (e.g. >30 days implies critical warning/fail) to prevent stale cost analysis misleading long-term budget decisions.
