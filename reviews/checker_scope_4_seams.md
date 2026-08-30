# Checkers Subsystem: Cross-Checker Seam & Interface Audit

**Target:** `checkers/` subsystem (`bcheck`, `ocheck`, `fcheck`, `scheck`) and `docs/` data interfaces.
**Score:** 7.5 (Moderate) - Significant utility shadowing, peer-to-peer import violations, and CLI contract drift.

## 1. CLI Contract Consistency
- **Flag Parity:**
  - `bcheck` supports `--fetch` and `--refresh`, while the others only support `--fetch`.
  - `bcheck` has `--md` to output Markdown; `ocheck`, `fcheck`, and `scheck` do not.
  - All support `--plain`/`--no-color`, `--slim`, and `--wide`.
- **Default Output Behaviors (The Drift):**
  - `fcheck`, `scheck`, and `bcheck` operate in a "check only" mode by default; they require explicit `--json` and `--html` flags to mutate the `docs/data/` or `docs/reports/` directories.
  - `ocheck` violates this pattern: it mutates `docs/data/ocgo_live.json` and `docs/reports/ocgo_cost_benefit.html` *by default* on every run unless explicitly blocked with `--check`.

## 2. Shared Utility Shadowing vs Deduplication (The Critical Violation)
- `opencode_cost_benefit_analyzer.py` (`ocheck`) heavily shadows `benchmark_common.py`, reimplementing core parsing and formatting functions rather than importing them:
  - `norm_id`
  - `parse_aa`
  - `parse_openrouter`
  - `parse_livebench`
  - `display_len`
  - `color_cell`
  - `render_cli_table` (partial)
- **Peer-to-Peer Import Coupling:** `free_model_ranker.py` (`fcheck`) and `stealth_model_detector.py` (`scheck`) both import `opencode_cost_benefit_analyzer.py` as `ogc` to consume these duplicated parsers instead of importing from `benchmark_common.py`. This creates horizontal coupling between independent checkers and bypasses the shared common module.
- **Divergent Logic:** The shadowed `norm_id` in `ocheck` uses `.replace(".", "-")`, mutating IDs like `claude-3.5` into `claude-3-5`. The canonical `benchmark_common.norm_id` intentionally preserves dots, leading to ID mismatch seams.

## 3. File & Data Store Seams
- **Atomic File Writing:** Excellent consistency. All checkers use `bc.atomic_write_text` to prevent race conditions or torn writes.
- **Raw Snapshot Interface:** Naming conventions (`*_YYYYMMDD.ext`) and the >24h offline-by-default logic correctly map to `docs/data/raw/` across all checkers.
- **Output Data Interface:** Files correctly output to `docs/data/*.json` and `docs/reports/*.html`.

## 4. Alignment with Engine & Memory Invariants
- **Pricing & Engine Alignment:** `engine/pricing.py` natively maps only Anthropic models. `ocheck` establishes a sprawling internal `FALLBACK_PRICING` dict and `model_to_id` alias resolution mechanism independent of the engine.
- **Memory Invariants:** 24h cache window, 7d green expiry (tracked via `added_ids` from the prev snapshot logic in `benchmark_common.py`), and offline-by-default execution are globally maintained.

## Actionable Remediations
1. **Deduplicate `ocheck`:** Remove the duplicated parsers and CLI formatters in `opencode_cost_benefit_analyzer.py` and replace them with calls to `benchmark_common.py`.
2. **Break Peer Coupling:** Refactor `free_model_ranker.py` and `stealth_model_detector.py` to import `parse_aa`, `parse_openrouter`, and `parse_lmarena` from `benchmark_common.py` rather than `opencode_cost_benefit_analyzer.py`.
3. **Harmonize CLI Outputs:** Modify `ocheck` to require explicit `--json` and `--html` flags to write files, restoring parity with the other checkers.
4. **Unify `norm_id`:** Enforce the use of `bc.norm_id` in `ocheck` to prevent dots from being transliterated into dashes, preserving canonical model IDs across the system.
