# Master Architectural Audit Report: Checkers Subsystem

**Review Date:** 2026-08-30
**Scope:** `checkers/` subsystem (`benchmark_common.py`, `opencode_cost_benefit_analyzer.py`, `llm_benchmark_aggregator.py`, `free_model_ranker.py`, `stealth_model_detector.py`) and associated data/reporting seams.
**Subagents:** 4 Parallel Pro Auditors (Scope 1 Foundation, Scope 2 OpenCode Go, Scope 3 Aggregator & Rankers, Scope 4 Seams).

---

## 1. Executive Scorecard

| Scope | Subsystem / Boundary | Health Score | Severity Tier | Primary Weakness / Risk |
| :--- | :--- | :---: | :---: | :--- |
| **Scope 1** | [Shared Core & Foundation](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py) | **9.8 / 10** | Exemplary | None (All math, parsers, cache, and atomic write helpers verified). |
| **Scope 2** | [OpenCode Go Analyzer (ocheck)](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py) | **6.5 / 10** | Critical | Naive substring variant matcher in `find_or_for_ocgo`, missing cache-write cost factors, CLI write defaults. |
| **Scope 3** | [Aggregator & Rankers (bcheck, fcheck, scheck)](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/llm_benchmark_aggregator.py) | **9.5 / 10** | Exemplary | None (ARC-AGI & AA quality wired, provider dedup with provenance, empty-catalog guards). |
| **Scope 4** | [Cross-Checker Seams & Contracts](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/reviews/checker_scope_4_seams.md) | **7.5 / 10** | Moderate | Utility shadowing in `ocheck`, peer imports bypassing `benchmark_common`, CLI flag/output asymmetry. |
| **OVERALL** | **Checkers Subsystem** | **8.3 / 10** | **Moderate** | **Strong foundation, but `ocheck` requires deduplication and matcher tightening.** |

---

## 2. Key Findings & Invariant Breaches

### 🚨 Critical Findings (< 7.0)
1. **OpenRouter Cross-Matcher Variant Contamination ([`opencode_cost_benefit_analyzer.py#L583-L584`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L583-L584))**
   - **Mechanism:** `find_or_for_ocgo` tests `n in norm_id(oid) or norm_id(oid) in n` without calling `bc.variant_conflict()`.
   - **Impact:** Substring containment permits cross-variant matching (e.g. associating base model IDs with suffix models like `-max` or `-pro`).
2. **Missing Cached Write Cost Factor ([`opencode_cost_benefit_analyzer.py#L680-L685`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L680-L685))**
   - **Mechanism:** `compute_cost` calculates input and output token pricing but completely drops `cached_write_per_1m`.
   - **Impact:** Models utilizing cached prompt writes are calculated as free for cache writes, under-reporting effective cost per task.

### ⚠️ Moderate Findings (7.0 – 8.4)
3. **Utility Shadowing & Horizontal Peer Import Coupling ([`free_model_ranker.py#L23`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/free_model_ranker.py#L23), [`stealth_model_detector.py#L18`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/stealth_model_detector.py#L18))**
   - **Mechanism:** `ocheck` re-implements `norm_id`, `parse_aa`, `parse_openrouter`, and `display_len`. `fcheck` and `scheck` import these directly from `ocheck` (`import opencode_cost_benefit_analyzer as ogc`) instead of `benchmark_common.py`.
   - **Impact:** Unnecessary horizontal coupling between checkers and divergent `norm_id` logic (ocheck replaces `.` with `-`, whereas `benchmark_common` preserves `.`).
4. **CLI Output Default Behavior Drift ([`opencode_cost_benefit_analyzer.py#L1471-L1495`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L1471-L1495))**
   - **Mechanism:** `ocheck` writes `ocgo_live.json` and `ocgo_cost_benefit.html` by default unless `--check` is explicitly passed. In contrast, `bcheck`, `fcheck`, and `scheck` are read/check only unless `--json` or `--html` flags are explicitly requested.

---

## 3. Prioritized Remediation Roadmap

### Batch P1: Security & Matcher Integrity (Critical)
- Refactor [`find_or_for_ocgo`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L583) to use [`benchmark_common.variant_conflict()`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L98) to eliminate variant contamination.
- Incorporate cached token write parameters in [`compute_cost`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py#L680).

### Batch P2: Deduplication & Architectural Cleanliness (Moderate)
- Remove shadowed parsers/formatters in [`opencode_cost_benefit_analyzer.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/opencode_cost_benefit_analyzer.py) and consume them directly from [`benchmark_common.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py).
- Decouple [`free_model_ranker.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/free_model_ranker.py) and [`stealth_model_detector.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/stealth_model_detector.py) from `ocheck` by routing all shared imports directly through `benchmark_common`.

### Batch P3: CLI Contract Parity & Output Symmetry (Minor)
- Standardize `--json` and `--html` write flags across all 4 checkers.
