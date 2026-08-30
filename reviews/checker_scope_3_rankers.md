# Scope 3: Aggregator & Rankers Audit Report

**Date:** 2026-08-30
**Target Files:**
- `checkers/llm_benchmark_aggregator.py` (bcheck)
- `checkers/free_model_ranker.py` (fcheck)
- `checkers/stealth_model_detector.py` (scheck)
- `checkers/test_llm_benchmark_aggregator.py`
- `checkers/test_free_model_ranker.py`
- `checkers/test_stealth_model_detector.py`

**Health Score:** 9.5 / 10 (Exemplary)

---

## 1. Executive Summary

The aggregator and ranking checkers (`bcheck`, `fcheck`, and `scheck`) demonstrate solid algorithmic rigor, comprehensive test coverage, and strict compliance with the project's offline-by-default architecture and Ponytail principles.

### Key Strengths
1. **Aggregator (bcheck) Rigor:**
   - Multi-benchmark synthesis across LiveBench, LMArena, Artificial Analysis, and ARC-AGI is mathematically robust.
   - Composite scoring properly integrates ARC-AGI-2 (`z_arc`) and AA quality (`z_aa_qual`) into `capability_q` and overall composite weights.
   - Baseline diffing runs catalog-wide *before* pool filtering, eliminating false-removal bugs when views are scoped to specific provider pools.
   - 7-day self-expiring green badges for new models prevent permanent UI badge debt.
2. **Free Model Ranker (fcheck) Rigor:**
   - `is_free_model` strictly validates free models ($0.0 input/output pricing or explicit free tier) across OpenRouter, OpenCode Zen, OpenCode Go, and Cline.
   - `_free_key` cleanly deduplicates provider prefixes while tracking provenance via `also_listed` metadata.
3. **Stealth Model Detector (scheck) Rigor:**
   - Stealth heuristics reliably identify unbranded / provisional endpoints (such as `stealth/` namespace and synthetic tags).
   - Empty catalog safeguards prevent partial/failed fetches from corrupting on-disk JSON/HTML artifacts.
   - Offline fallback guarantees zero runtime network dependencies by default.

---

## 2. Dimension Breakdown

| Tool / Dimension | Score | Assessment |
| :--- | :---: | :--- |
| **bcheck (Aggregator)** | **9.6 / 10** | Robust ARC-AGI & AA quality scoring, pool filtering, baseline persistence, full offline support. |
| **fcheck (Free Models)** | **9.5 / 10** | Accurate free model filtering, provider deduplication with provenance, clean composite ranking. |
| **scheck (Stealth Models)** | **9.4 / 10** | Safe empty-catalog fallback, robust heuristic classification, resilient table rendering. |
| **Test Coverage & Isolation** | **9.7 / 10** | 73 unit tests across checkers verifying offline defaults, mock network fetches, and edge cases. |

---

## 3. Actionable Remediations
- None required. All critical architectural invariants (P1/P2) are verified and resilient.
