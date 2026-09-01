# Scope 4: Model Rankers Audit Report (fcheck / scheck)

**Date:** 2026-09-01
**Auditor:** Scope 4 Auditor (Model Rankers — fcheck/scheck)
**Target Files:**
- `checkers/free_model_ranker.py` (fcheck, 800 lines)
- `checkers/stealth_model_detector.py` (scheck, 512 lines)
- `checkers/test_free_model_ranker.py` (9 tests)
- `checkers/test_stealth_model_detector.py` (6 tests)
- `checkers/benchmark_common.py` (shared helpers, read-only)

**Health Score: 6.4 / 10 (Critical)** — one Critical data-integrity defect, two High correctness defects, zero invariant breaches of the offline/`--check`/pure-stdlib contract, but the fcheck scope invariant is *compromised in effect* (enrichment + validation are silently dead, and the paid/free join can invert).

---

## 1. Executive Summary

Both checkers were run end-to-end in offline `--check` mode against the 20260901 snapshot set, all 15 unit tests pass, and the offline-by-default / `--check`-writes-nothing / pure-stdlib invariants verified clean. The headline list of fcheck is correctly limited to OpenCode Zen/Go `-free` ids + Cline's `free` tier (10 rows, all `[OC]`/`[CLN]` — no OpenRouter rows ever listed).

However, the **OpenRouter catalog seam is broken**, and it sits directly on the fcheck scope invariant: the OR join is supposed to *validate* Cline free claims and *carry real price/context* onto OC/CLN rows — it currently does **neither**, and worse, its validation gate is vacuously true. The root cause is a shared-helper seam regression introduced by commit `4c23c01` ("decouple peer imports, unify cross-matchers"): `benchmark_common.parse_openrouter` returns a **normalized subset** (`context`, `prompt_price_1m`, `completion_price_1m`, `is_free`, `is_stealth`, `created`) that drops the raw fields both checkers read back (`pricing`, `context_length`, `architecture`). fcheck/scheck were written against ocheck's **rich** `parse_openrouter` (dict id→raw record), which the refactor silently swapped.

Verified consequences (live data, 20260901 snapshots):

- `is_free_model` over `bc.parse_openrouter` output is **True for 425/425** OpenRouter records, including `ibm-granite/granite-4.2-8b` ($0.10/$0.15 per MTok), `anthropic/claude-opus-5` ($5/$15) and `openrouter/auto` (negative "pricing"). The free-key index `or_free_by_key` therefore contains **every** catalog key (413/413), not just free ones. `free_model_ranker.py:501` indexes on a predicate that can never be False.
- The OC/CLN enrichment join (`or_free_by_key.get(_free_key(oid))` at `free_model_ranker.py:540`/`578`) resolves for **every** row but carries `context_length=None` and `pricing=None`, so `rec["context_length"]` is None for all 10 listed rows — the CLI and HTML `Ctx` column shows `—` for every model despite "6 price/ctx via OR" in the run banner. Cline's own free rows (`cline-free/longcat-2.0`, `z-ai/glm-5.3-flash`, `deepseek/deepseek-v4-flash`) similarly get no real context.
- The **paid/free key-collision hazard**: 12 OR keys collide on `_free_key` between a paid model and its `:free` twin (`z-ai/glm-5.2` vs `z-ai/glm-5.2:free`, `poolside/laguna-s-2.1` vs `:free`, etc.). Since `setdefault` keeps the *first* record per key and the index is now effectively unordered/order-dependent, a paid record can be picked for a free row (or a free twin dropped), which would fabricate $0 pricing/context on the wrong variant. Today the parsed records all have `pricing=None`, so the stored value is harmless only by accident — if the seam is fixed by restoring rich records, this collision bug becomes live and can put paid data on free rows.
- `scheck`'s enrichment fields are likewise dead: `created` is parsed (present in bc subset), but `price_str` is always `0.00/0.00` (bc subsets lack `pricing`), `modality` is always `—` (`architecture` dropped), and `openrouter_context` is always None (`context_length` renamed to `context`). The current OR snapshot has **0** `stealth/` models, so these are latent — but the same seam means the stealth table's price/modality/created columns would be wrong the moment a stealth model appears.
- **Prior-audit flag verified:** the "blanket `except Exception`" on `is_free_model` (`free_model_ranker.py:69-73`) is real but narrow (only guards a numeric conversion) — it is *not* the primary defect. The primary defect is that the guard never gets a chance to matter because the input record shape is wrong.

CC recomputed (same method as prior audit): fcheck `main` ≈ 75 (prior claim 102; module-level `render_cli_table` ≈ 38 adds most of the residual), scheck `main` ≈ 52 (prior claim 65). Both exceed the CC≤10 target by an order of magnitude, but this audit found no *concrete* bug caused by the complexity — the two real bugs are data-shape and key-collision defects, not control-flow ones. CC remains a maintainability (P3) concern.

Test coverage gap: `test_openrouter_models_not_listed` asserts *absence* of `[OR]` but never asserts the presence of real context/price on OC/CLN rows, and `test_cached_json_loader_is_offline_by_default` only checks the Cline cache, not the OR path. No unit test exercises `or_free_by_key` enrichment, `is_free_model` against a *parsed* record, or the paid/free key-collision case — which is exactly why the seam regression sailed through.

### Invariant verdicts

| Invariant | Verdict |
| :--- | :--- |
| Offline by default; `--fetch` only network path; `--check` never writes | ✅ VERIFIED (both checkers; `fetch_or_load_cached_json` gate, `do_write=not args.check`; scheck's fetch-failure cached fallback also clean) |
| Pure stdlib, no 3rd-party deps | ✅ VERIFIED |
| Fail-fast, no swallowed errors | ⚠️ Mostly — offline parse failures are loud WARNs + graceful degradation (by design), but `is_free_model`'s except-clause *returns False*, and the parsed-record seam swallows the shape mismatch silently (no warning is emitted that pricing/context are absent) |
| fcheck scope: listed rows = OC Zen/Go + Cline free ONLY | ✅ LISTED ROWS verified (0 `[OR]` badges, sources only `oc`/`cln`) — but see the caveat below |
| OR catalog fetched only to validate Cline free claims + join via `_free_key` | ❌ COMPROMISED IN EFFECT: validation is vacuously true (425/425 "free"), the join resolves for every row but enriches nothing (`ctx=None`, `pricing=None`) |

**Scope caveat:** the *listed rows* invariant holds today, but the *validation half* of the scope invariant is what protects it going forward. With `is_free_model` vacuously true, the S3-F3-1 gate (`free_model_ranker.py:582-585`, which would drop a paid model listed under Cline's "free" tier) can never fire — a paid model appearing in Cline's free list would now be listed with fabricated `$0` pricing instead of being dropped. That is a latent correctness breach of the invariant's *intent*.

---

## 2. Dimension Breakdown

| Tool / Dimension | Score | Assessment |
| :--- | :---: | :--- |
| **fcheck — Correctness** | **4.5 / 10** | OR enrichment/validation dead (ctx always None, is_free vacuously true); composite scoring, Q/P/FGI derivations, and `_free_key` dedup logic correct in themselves; key-collision hazard latent. |
| **scheck — Correctness** | **6.0 / 10** | Filter `stealth/` prefix + composite math correct; created-date OK; price/modality/context enrichment dead (latent, 0 stealth models today). |
| **Robustness** | **8.5 / 10** | Offline snapshot handling, staleness (filename-date based), malformed-JSON tolerance (WARN + degrade), error isolation all solid. |
| **Performance** | **9.0 / 10** | Rendering linear in rows; snapshot discovery O(n) on a small dir; no hot loops. |
| **Security** | **8.5 / 10** | `atomic_write_text` (tmp sibling + fsync + `os.replace`) + `html.escape` everywhere; only residual: bash-log injection via `--fetch` output path, plus `.tmp` collisions under parallel `--fetch`. |
| **Test Coverage** | **6.0 / 10** | 15/15 pass, but the OR seam, enrichment, and key-collision paths are untested — the regression and the collision hazard both slipped through. |
| **Maintainability (CC)** | **4.0 / 10** | `main` CC ≈ 75 (fcheck) / 52 (scheck); far above the CC≤10 target; no concrete bug attributable, but genuine P3 debt. |

---

## 3. Top Findings (with exact references)

### P1-1 — CRITICAL: OR-catalog seam — `is_free_model` vacuously true, enrichment dead (fcheck + scheck)
**Files:** `checkers/free_model_ranker.py:493-503, 540-548, 578-591` · `checkers/stealth_model_detector.py:429-461, 318-360` · seam origin `checkers/benchmark_common.py:724-763` (regression introduced by commit `4c23c01`, 2026-08-30).

`bc.parse_openrouter` (benchmark_common.py:724) returns records with `context`, `prompt_price_1m`, `completion_price_1m`, `is_free`, `is_stealth`, `created` — **but not** `pricing`, `context_length`, or `architecture`. Both checkers were written against ocheck's *rich* parser (pre-refactor `opencode_cost_benefit_analyzer.parse_openrouter` returned `out[mid] = m`, the raw record) and read back the dropped keys:

- `is_free_model` reads `rec["pricing"]` (free_model_ranker.py:68-74) → absent ⇒ `.get("prompt", 0)` = 0 ⇒ **True for every record** (verified: 425/425, incl. paid `ibm-granite/granite-4.2-8b`, `anthropic/claude-opus-5`, negative-priced `openrouter/auto`).
- `or_free_by_key` index (free_model_ranker.py:499-503) is therefore built from every key (413/413).
- Enrichment (free_model_ranker.py:540-548, 578-591): `or_rec.get("context_length")` → None, `or_rec.get("pricing")` → None ⇒ every listed row has `openrouter_context=None` ⇒ `Ctx` column is `—` for **all 10 rows** despite the "6 price/ctx via OR" banner (verified live).
- scheck's `price_str` (stealth_model_detector.py:429-433) reads `rec.get("pricing")` → always `0.00/0.00`; `modality` (line 453) reads `architecture` → always `—`; `openrouter_context` (line 460) reads `context_length` → always None.

**Impact:** the *validation* half of the fcheck scope invariant is dead (a paid model in Cline's free list would now be listed with fabricated $0, not dropped), and price/context enrichment — the documented purpose of the OR fetch — silently no-ops. Listed-rows invariant itself still holds because membership is driven by OC/Cline id naming, not by the OR index.

**Fix (P1):** either (a) restore a rich `parse_openrouter` (id→raw record) and have fcheck/scheck use it, or (b) extend the bc subset with `pricing`, `context_length`, `architecture` (and update `is_free_model` to read the subset keys `prompt_price_1m`/`completion_price_1m` — using `== 0.0` only, never `<= 0`, since `openrouter/auto` has negative prices). Add a WARN when the parsed map has zero free keys / zero records with `pricing` so the shape mismatch can never again be silent.

### P1-2 — HIGH: `_free_key` paid/free twin collision makes the OR join order-dependent
**File:** `checkers/free_model_ranker.py:77-81, 499-503, 540, 578`

12 OR keys collide on `_free_key` between a paid model and its `:free` twin (`z-ai/glm-5.2` vs `z-ai/glm-5.2:free`, `poolside/laguna-s-2.1` vs `:free`, `nvidia/nemotron-3.5-lightning` vs `:free`, … — verified live). `or_free_by_key.setdefault` keeps whichever record is iterated first, so the free model picked for enrichment can be the **paid** twin — which, once the P1-1 shape fix lands, would copy paid pricing/context onto a free row (or the free twin could be dropped entirely). The design comment says "OpenCode lists bare `x-free` while OpenRouter/Cline list `prov/x[:free]`" — the key intentionally strips the suffix, but the index must **prefer the free variant** when a collision exists (e.g. build the index over `is_free_model`-filtered records and order `:free`-suffixed ids first, or key on `base_id` including the `:free` marker and resolve via exact suffix on the OR side).

### P1-3 — HIGH: `is_free_model` numeric semantics — `or 0` + missing-key default misclassify negative/absent pricing
**File:** `checkers/free_model_ranker.py:63-74`

`p.get("prompt", 0) or 0` treats *missing* pricing as $0 (fine for the :free suffix path, wrong for validation) and would treat a **negative** price (OR uses `-1000000` as a sentinel for `openrouter/auto`) as `True` after `float()` — a negative price is not "free". The blanket `except (ValueError, TypeError): return False` is the prior-audit-flagged clause; it is narrow and not the primary bug, but the whole function should be rewritten to (a) only `:free`-suffix → free, (b) parse real numbers with `_safe_float` and require `prompt == 0.0 and completion == 0.0`, (c) missing pricing → not free (unless suffix). This is the gate that protects the Cline validation (S3-F3-1), so it must be strict, not permissive.

### P2-1 — MEDIUM: Cline validation gate can no-op when OR has no free twin — `is_free_model(check_rec)` fallback uses Cline's record or a bare `{"id": cid}`
**File:** `checkers/free_model_ranker.py:582-585`

When no OR record exists for a Cline id, `check_rec` falls back to `crec` (Cline's raw record, which has no `pricing` key in the 20260901 snapshot) or `{"id": cid}` — `is_free_model` then returns True **because pricing is absent** (`or 0`), so the S3-F3-1 validation never rejects anything. A paid Cline-listed model with no OR twin would be listed with fabricated $0. Should require explicit evidence of $0 (suffix or pricing) rather than defaulting to free.

### P2-2 — MEDIUM: `Ctx`/price columns misleadingly render `—`/`0.00/0.00` instead of "unknown" — enrichment is advertised but dead
**Files:** `checkers/free_model_ranker.py:160-161, 352-353` · `checkers/stealth_model_detector.py:88, 209-210`

Because the enrichment is dead (P1-1), the CLI/HTML `Ctx` column is `—` for every row and scheck's price column shows `0.00/0.00` — which is *misinformation* ("$0" on a model whose price is unknown), not just missing data. scheck even appends "($0)" when the string is `0.00/0.00` (stealth_model_detector.py:454), which will mark every future stealth model as $0. After fixing P1-1, re-verify these render paths; in the meantime the `0.00/0.00 ($0)` marker should require an actual free record.

### P3-1 — LOW: bash-log injection via `--fetch` success path
**Files:** `checkers/free_model_ranker.py:109` · `checkers/stealth_model_detector.py:340`

`print(f"  saved {snapshot_prefix} -> ...")` interpolates a URL-derived snapshot prefix. Prefixes are constants today (`openrouter_models`, etc.), so this is latent — but the safe habit is to print only the resolved `target` path (which is filesystem-derived and safe), not the raw prefix.

### P3-2 — LOW: `atomic_write_text` tmp-name collision under parallel `--fetch`
**File:** `checkers/benchmark_common.py:147-163`

The tmp name embeds pid + `time_ns`, which is collision-safe in practice; the residual risk is two *processes on the same host sharing a pid namespace* — theoretical. No change required, noting only for completeness.

### P3-3 — LOW: CC debt — `main()` fcheck ≈ 75, scheck ≈ 52 (prior audit claimed 102 / 65)
**Files:** `checkers/free_model_ranker.py:462` · `checkers/stealth_model_detector.py:288`

Recomputed with an AST decision-point counter (If/For/While/Except/With/BoolOp/comprehension). The gap vs. the prior claim comes from `render_cli_table` (≈38 / ≈22) and `render_html` (≈13 / ≈5) being counted separately. No concrete bug attributable to CC; flagging as maintainability debt — recommend extracting the per-section OR/OC/CLN ingestion into named helpers (which also makes the P1-1 shape bug unit-testable in isolation).

### P3-4 — LOW: `removed_models` CLI renderer Q-suppression asymmetry
**File:** `checkers/benchmark_common.py:1842-1844`

The Q detail is only shown when `fgi is None` — a removed model with both FGI and Q shows FGI but never Q, and one with neither shows neither. Cosmetic; consistent with sibling checkers, flagged for awareness.

---

## 4. Remediations

### P1 (Critical / High — do first)
1. **Fix the OR seam (P1-1):** extend `benchmark_common.parse_openrouter` to carry `pricing`, `context_length`, `architecture` (or restore a rich parser used by fcheck/scheck), and add a WARN when the parsed map contains no records with real pricing — making a shape regression loud instead of silent.
2. **Strict `is_free_model` (P1-3):** `:free` suffix → free; otherwise parse real numbers and require both `== 0.0`; missing or negative pricing → not free. Add unit tests: paid model, `openrouter/auto` (negative sentinel), missing pricing, malformed pricing.
3. **Collision-safe free index (P1-2):** build `or_free_by_key` only from `is_free_model`-filtered records and prefer the `:free`-suffixed variant on collision (or resolve the OR side by exact `base_id` + `:free` suffix match). Add a unit test asserting `z-ai/glm-5.2:free` wins over `z-ai/glm-5.2`.

### P2 (Medium)
4. **Cline validation gate (P2-1):** require explicit free evidence (suffix or $0 pricing) — never default "absent pricing ⇒ free". Add a test with a paid Cline-listed model and no OR twin.
5. **Truthful rendering (P2-2):** until enrichment is restored, render `Ctx`/price as `—`/`unknown` rather than `0.00/0.00 ($0)`; re-verify after P1-1.

### P3 (Low)
6. Split `main()` ingestion into per-source helpers (CC + testability).
7. `--fetch` banner: print only resolved `target` paths (bash-log hygiene).
8. Optional: cover the OR index + enrichment + key-collision in `test_free_model_ranker.py` (currently zero coverage of the OR path — this is why the regression shipped).

---

## 5. Method & Verification Notes

- Ran `test_free_model_ranker.py` + `test_stealth_model_detector.py` (15 tests) via stdlib unittest: **all pass** (0.665s).
- Ran both checkers offline `--check --plain` against the 20260901 snapshot set: fcheck lists 10 rows (8 OC + 2 CLN, no `[OR]`), scheck 0 rows (no stealth models in the current OR snapshot).
- Verified seam behavior with live-data scripts: `is_free_model` True for 425/425 parsed OR records; `or_free_by_key` 413/413 keys; all 8 OC ids resolve in the index but with `context_length=None`/`pricing=None`; 12 paid/free key collisions; raw OR snapshot contains `pricing`/`context_length`/`architecture` on 425/425 records (so the data is there — the parser drops it).
- CC measured with an AST decision-point counter (If/For/While/Except/With/BoolOp/comprehensions; `and`/`or` counted via BoolOp `n_values-1`).
- Scope invariant verified both statically (membership driven only by OC id naming + Cline `free` list, lines 509-601) and dynamically (run output shows no OR rows/badges).
- Read-only audit; no files modified besides this report.

**Files reviewed:** `checkers/free_model_ranker.py`, `checkers/stealth_model_detector.py`, `checkers/test_free_model_ranker.py`, `checkers/test_stealth_model_detector.py`, `checkers/benchmark_common.py` (relevant sections: 62-181, 200-266, 417-481, 544-560, 644-851, 890-1165, 1639-1877).
