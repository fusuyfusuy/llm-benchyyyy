# Scope 1 Audit — Shared Foundation & Math
**Scope:** `checkers/benchmark_common.py` + `checkers/test_benchmark_common.py`
**Auditor:** Scope 1 (Shared Foundation) — method: `mimori slice` + targeted reads + adversarial runtime probes
**Date:** 2026-02 (session) · **Tests:** 29/29 pass (`pytest checkers/test_benchmark_common.py`)

---

## 1. Executive Summary

**Health score: 8.6 / 10** — *Moderate-to-Minor band; strong core, defensive gaps at the edges.*

This module is the best-tested and most carefully-invariant'd file in the checkers suite. The core mathematical layer (z-scores, capability-Q clamping, sigmoid P_succ, value indices), the normalization layer (`norm_id`/`norm_model_slug`/`strip_tier_tokens`/`variant_conflict`), the staleness layer (filename-date authority, S2-M2), and `atomic_write_text` are all **correct and faithful to the documented invariants** — verified by probe, not just by reading. 29/29 tests pass, including the subtle ones (filename-date-beats-fresh-mtime, variant/digit surplus rejection, two-set docs-tag diffing, 0.0-cost Pareto frontier).

The weaknesses concentrate in **parser robustness** (silent whole-source failure on adversarial-but-plausible upstream payloads), **NaN/`nan` string handling** (silent fabrication of Q=99.9, or a hard crash in `get_z_scores`), and **defensive type-guarding** in two display/compute helpers. None of these are data-loss/RCE/crash-loop grade (no deserialization of untrusted code, no path traversal possible through `atomic_write_text`), so nothing lands in the <7.0 Critical band. But the parse-failure class is the *same class of bug that already bit production once* (2026-08-27 parse_aa silently broken, per `.mimori/memory.md`) — the residual escape-ordering fragility means the blast radius (all four checkers silently lose an entire benchmark source) is unchanged.

**Invariant status:**

| Invariant | Status |
|---|---|
| Pure Python 3.11+ stdlib, zero deps | ✅ Compliant (imports: stdlib only) |
| Offline by default; staleness from filename `_YYYYMMDD`, not mtime | ✅ Compliant (S2-M2) — `snapshot_date_str`/`pick_latest_raw`/`snapshot_age_hours` all key on filename date; tests pin it |
| Never mix AA live intelligenceIndex (~62–78) with static seeds (~93–96) in one z-distribution | ✅ **Held in the aggregator's `calculate_composite_scores` (cohort split, `llm_benchmark_aggregator.py:1425-1434`)**. ⚠️ **Latent drift in the shared primitive**: `get_z_scores` banks missing entries at cohort mean (z=0.0 → Q=78) — a footgun that contradicts the invariant's letter; currently masked because every consumer guards with `is not None` before reading the z array |
| Missing signals NEVER banked at cohort mean | ⚠️ Partially: `compute_meanfill_composite` skips missing (✅); `get_z_scores` zero-fills (⚠️ latent) |
| CC ≤ 10, depth ≤ 3, fail-fast, no swallowed errors | ⚠️ **Breach-leaning**: `parse_aa`/`parse_lmarena`/`fetch_url` swallow exceptions and return `{}`/`None` *silently* (no warning at default verbosity); parsers return empty dicts with no post-parse validation, so a broken parse looks identical to "source has no data" |

---

## 2. Top Findings (with line references)

### P1 — Critical-severity findings (silent corruption / whole-source data loss)

**F1. `parse_lmarena` RSC block extraction truncates on `}]` inside string values — silently drops the entire LMArena source**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L554` and `#L558`
The block finder is `unescaped.find('"entries":[{', pos)` then the **escape-unaware** `unescaped.find("}]", idx)` (#L558-561). Any `}]` sequence inside a string field (a model name, notes, or description containing `x}] y`) terminates the JSON early → `json.loads` fails → `except Exception: pass` (#L587) → falls through to the legacy table path → ultimately `{}`. Compounding: `elo = round(float(rating), 0)` (#L571) crashes the whole block on non-numeric ratings, and the naive pre-unescape `html_text.replace('\\"', '"')` (#L552) corrupts any value that legitimately contained an escaped quote/backslash, again producing `{}`.
*Probe results:* payload with `"notes":"x}] y"` → `{}`; payload with escaped quote in a name → `{}`; payload with `"rating":{}` → `{}`. Real RSC payload parses correctly today, but the class of failure is one upstream name/description tweak away, and the failure is **silent at default verbosity**.

**F2. `parse_aa` unescapes the whole HTML *before* bracket-scanning — escaped quotes in values break quote tracking and kill the entire AA source**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L651` (unescape), `#L672-L689` (scan), `#L715-L718` (silent `{}` on failure)
The scan relies on real quotes, but the text has already been through `replace('\\"', '"')`. A model name that originally contained an escaped quote (e.g. `GPT-5.6 \"Luna\"`) becomes a bare `"` inside the string, the depth-tracker closes the string early, the bracket scan ends at the wrong `]`, and `json.loads` throws — swallowed by `except Exception` (#L715) → returns `{}` → every downstream checker (bcheck/ocheck/fcheck/scheck all import this, in-degree 8 per `mimori slice`) silently loses the AA column for the run. There is **no post-parse sanity gate** (no "≥N models or warn loudly" check), so a broken parse is indistinguishable from "AA has no data".
*Probe results:* `"name":"GPT \\"5\\" Live"` → `{}` (0 models); real escaped RSC payload → parses correctly (6-line fix recipe below removes the fragility without touching the happy path).

**F3. NaN/`nan`/`inf` values are accepted and either silently fabricate top-of-scale Q or hard-crash the run**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L166-L175` (`_safe_float`), `#L200-L210` (`parse_price`), `#L284-L291` (`compute_capability_q`), `#L294-L303` (`compute_p_success`), `#L272-L281` (`get_z_scores`)
`_safe_float("nan")` returns `nan` (float("nan") succeeds; only ValueError/TypeError are caught). Consequences, all probe-confirmed:
- `compute_capability_q(nan)` → **99.9** (Python `min(99.9, nan)` returns 99.9) — a single `"nan"` token in an AA payload silently promotes that model to the top of the Q scale, distorting every derived metric (P_succ, AVI, FGI, BFI, QVI, Pareto frontier).
- `compute_p_success(nan)` → 0.0 (max/min clamping semantics), so the same model shows Q=99.9 *and* P=0.0 simultaneously.
- `get_z_scores([nan, 70, 80, 90])` → `ValueError: inf or nan encountered in data` — a hard crash of the whole run instead of row-level isolation.

---

### P2 — Moderate findings (invariant drift, missing fallbacks, validation gaps)

**F4. `get_z_scores` zero-fills missing/non-numeric entries at the cohort mean — the exact behavior the bcheck Q-scoring invariant forbids**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L272-L281` (zero-fill at #L276/#L281)
Probe: `get_z_scores([None, 70, 80, 90])` → `[0.0, -1.0, 0.0, 1.0]` — the missing entry is banked at z=0.0 → Q=78.0 (cohort mean). Currently *masked* because ocheck/ccheck only read `z_int[i]` when the source value is non-None (`opencode_cost_benefit_analyzer.py:1788-1797`), and `compute_meanfill_composite` skips missing correctly (`benchmark_common.py:440-448`). But it is a loaded footgun for any future consumer that indexes the z array blindly, and it is why the aggregator had to reimplement a *correct* `_z_scores` returning `None` for missing (`llm_benchmark_aggregator.py:1385-1399`). **Two divergent z-primitives in one suite is invariant drift.** Bonus inconsistency: `get_z_scores` uses `statistics.stdev` (sample, n−1) while `compute_meanfill_composite` uses `pstdev` (population) for the identical concept (#L278 vs #L432-434).

**F5. Staleness helpers crash on missing/None paths instead of reporting "missing"**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L232-L241` (`snapshot_age_hours` → `FileNotFoundError` at #L241), `#L244-L250` (`staleness_tag(None)` → `TypeError` at #L247)
Probe-confirmed: `snapshot_age_hours("/nonexistent/x.json")` crashes; `staleness_tag(None)` crashes. Consumers like `opencode_cost_benefit_analyzer.py:78-86` guard `pick_latest_raw` → None *before* calling staleness, but `llm_benchmark_aggregator.py:1361-1364` and `stealth_model_detector.py:329` do not always — a missing/deleted snapshot turns an offline run into a traceback instead of a "source missing" banner. Also: `snapshot_age_hours` anchors the filename date at **midnight UTC** (#L239), so age overcounts by up to ~24h and the `>24h` WARN (#L249) fires up to a day early for a same-day snapshot fetched in the afternoon (tests only pin midnight-to-midnight, so this is invisible to the suite).

**F6. `parse_openrouter` crashes on non-dict records or non-dict `pricing` — a schema tweak takes down the whole checker**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L740-L748`
Probe-confirmed: `{"data": [{"id": "a/b", "pricing": "0.000003"}]}` → `AttributeError: 'str' object has no attribute 'get'` (#L746); a non-dict item in `data` → same crash (#L742). If OpenRouter ever emits `pricing` as a string, or a list entry that isn't a dict, every checker crashes. Needs `isinstance` guards and per-record isolation (skip the bad record, keep the rest).

**F7. `find_aa_for_model`/`find_lm_for_model`/`find_livebench_for_model` stage-1 tier-stripping can link a *non-reasoning* variant — contradicting the memory contract ("non/reasoning are VARIANT tokens, never tier")**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L97-L101` (`TIER_TOKENS` contains `non`, `reasoning`), `#L112-L117` (`strip_tier_tokens`), `#L787-L801` (stage 1 links on `strip_tier_tokens(slug) == sn`)
Probe-confirmed: with only `glm-5-2-non-reasoning` (intelligenceIndex 34.2) in the AA map, `find_aa_for_model("glm-5.2", aa_map)` **returns the non-reasoning record** because stage 1 strips `non-reasoning` as a tier and links on the base. `variant_conflict("glm-5.2","glm-5-2-non-reasoning")` correctly returns `True` — but stage 1 never consults `variant_conflict`, so the guard is bypassed whenever the AA map is sparse (exactly the "static seed" degradation scenario the invariant warns about). `strip_tier_tokens("glm-5.2-non-reasoning")` → `"glm-5-2"` — the token is being treated as a tier, in direct conflict with the memory.md contract that classifies `non`/`reasoning` as variant tokens.

**F8. Defensive type gaps crash two compute/render helpers**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L405` + `#L410-L413` (`compute_pareto_frontier`: `a.get("display")` → `None` → `None[:22]` → `TypeError`), `#L1819-L1823` (`render_removed_models_cli`: `f"{pr_lim:.0f}/m"` on a string limit → `ValueError: Unknown format code 'f'`)
Probe-confirmed both. A catalog row missing `display`, or a snapshot whose `monthly_usage_limit_usd` is a string, crashes the report render instead of degrading gracefully.

---

### P3 — Minor findings (polish, test gaps, hardening)

**F9. `fetch_url` swallows every exception silently; the sync daemon writes whatever bytes come back with no sanity gate**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L62-L69`; `benchmark_sync_daemon.py:103-107`, `:142-146`
A 200-with-error-page (or truncated body) is saved as today's `artificial_analysis_YYYYMMDD.html` with no size/parse validation → the filename date marks it *fresh* for 24h while parsers silently return `{}` (F1/F2). The memory.md 2026-08-27 incident is exactly this chain. Recommend: minimum-byte threshold + parse-validate-before-persist, and a loud stderr WARN (not just `verbose`-gated) when a fetch/parse yields empty.

**F10. `parse_livebench` `or`-chains treat legitimate 0.0 scores as missing; `overall` double-counts summary columns**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L530-L536` (e.g. `cat_scores.get("Coding") or ... or _safe_float(row.get("coding"))` falls through on 0.0), `#L518` (mean of *all* numeric non-`model`/`nq_`/`out_` columns — an "Overall" column in the CSV would be double-counted).

**F11. `diff_model_catalog` stamps future-dated `created` values as `first_seen` and marks them brand-new**
`file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/checkers/benchmark_common.py#L1769-L1779`, `#L1788-L1792`
Probe: a row with `created: "2026-09-01"` at `now=2026-08-30` is stamped `first_seen` in the future and flagged green. The freshness guard clamps negative age (`0 <= age_days`) so it self-corrects next run, but the persisted future timestamp leaks into reports/sorts.

**F12. Test-coverage gaps in `test_benchmark_common.py`** — no malformed-input tests for any parser (F1/F2/F6), no NaN/`nan`-string tests (F3), no missing-path staleness tests (F5), no non-dict record tests (F6), no `compute_pareto_frontier`-without-`display` / string-limit render tests (F8), and `compute_role_recommendations` is only exercised with a 4-model happy path. The suite is excellent at pinning the *happy-path contracts* (staleness filename authority, variant conflicts, docs-tag diffing) but leaves the entire failure-class surface untested.

**Performance verdict (P3, no action needed):** `parse_aa`'s bracket scan is O(k·n) with k = number of `"models":` occurrences (2–4 in practice) over a 1–3 MB HTML — fine. `parse_lmarena` is O(k·n) similarly. Whole-response buffering in `fetch_url` and `atomic_write_text` is acceptable at leaderboard scale; no streaming needed. No perf bloat found.

**Security verdict (P3, no action needed):** `atomic_write_text` is clean — tmp name is `.{name}.{pid}.{time_ns()}.tmp`, and `Path.with_name` rejects `/` (probe-confirmed `ValueError`), so no traversal through the tmp path; `os.replace` + fsync is atomic; stale tmp cleanup in `finally`. Deserialization is `json.loads` only (no pickle/eval); parsers run `json.loads` on remote content but JSON is not executable. No credentials handled in this module.

---

## 3. Actionable Remediations (prioritized)

### P1 (do first — silent corruption / whole-source loss)
1. **Fix the RSC extraction order in `parse_aa` and `parse_lmarena`: scan the *raw* text, unescape only the extracted segment.**
   - `parse_lmarena` (#L554-561): replace the blind `find("}]")` with an escape-aware bracket scan over the raw HTML (track `in_str`/`esc`, count `[`/`]`), starting at `"entries":[{`. Then unescape the segment (`\"`→`"`, `\/`→`/`) and `json.loads` it. This single change fixes F1's truncation *and* escaped-quote corruption, because the scan's escape flag already handles `\"` correctly on raw text.
   - `parse_aa` (#L651, #L672-689): move the `replace('\\"', '"').replace("\\/", "/")` to *after* the segment is located (scan raw text; the bracket-depth state machine already tracks escapes). Unescape `unescaped[best_idx:best_end]` before `json.loads` (#L699-700).
   - Add a **post-parse validation gate** to both parsers: if the source marker was found but `len(out) == 0` (or `< 50` for AA), emit a loud `WARN` to stderr *unconditionally*, not just under `verbose` — a broken parse must never look identical to "no data".
2. **Reject non-finite floats at the conversion boundary.** In `_safe_float` (#L166-175) and `parse_price` (#L200-210): after `float(val)`, `if not math.isfinite(f) : return default`. This neutralizes F3 end-to-end (AA "nan" → `None` → consumer skips the signal), and makes `compute_capability_q`/`compute_p_success`/`get_z_scores` NaN-proof without touching their math. Add a defensive `math.isfinite` guard in `get_z_scores`'s valid-list filter (#L274) so a stray NaN degrades to a skipped row instead of a run-wide `ValueError`.

### P2 (next — invariant drift, crash surfaces, missing fallbacks)
3. **Align the shared z-primitive with the invariant:** change `get_z_scores` (#L272-281) to return `None` for missing/non-numeric entries (mirroring `llm_benchmark_aggregator.py:1385-1399`), and fix the docstring that currently advertises zero-fill. Verify all consumers (ocheck/ccheck z-array indexing at `opencode_cost_benefit_analyzer.py:1788-1797`, `commandcode_cost_benefit_analyzer.py:864-876`) skip `None` entries — they already key off `is not None` on the source signal, so this is a mechanical change. Reconcile `stdev` vs `pstdev` (#L278 vs #L432-434) with a comment or a single helper.
4. **Make staleness helpers total:** `snapshot_age_hours` (#L232-241) → return `math.inf` (or raise a documented `FileNotFoundError` caught by callers) when the path is missing; `staleness_tag` (#L244-250) → `""` on `None`. And anchor the age to the snapshot's actual fetch window — either store a fetch timestamp alongside the date or accept the midnight anchor but document the ≤24h overcount in the WARN text.
5. **Harden `parse_openrouter` (#L740-748):** `isinstance(rec, dict)` filter, `isinstance(pricing, dict)` guard, and per-record `try/except` so one malformed record is skipped rather than crashing the checker. Add a "parsed 0 of N" warning when the payload had entries but none parsed.
6. **Move `non`/`reasoning` handling in the finders to match the memory contract:** in `find_aa_for_model`/`find_lm_for_model`/`find_livebench_for_model` stage 1 (#L787-801, #L814-820, #L864-869), either remove `non`/`reasoning` from `TIER_TOKENS` (they belong in `VARIANT_TOKENS` only — `#L97-101`) or run the stage-1 candidate list through `variant_conflict` before linking. Keep exact-canonical matches untouched (they're correct today).
7. **Defensive isinstance guards:** `compute_pareto_frontier` (#L410-413) — `d = a.get("display"); if d and d[:22]`; `render_removed_models_cli` (#L1823) — `isinstance(pr_lim, (int, float))` before `:.0f`.

### P3 (polish / hardening)
8. **Gate the sync daemon's snapshot persistence:** minimum-byte threshold + parse-validate-before-write for AA/LMArena/OpenRouter (`benchmark_sync_daemon.py:129-159`), so a 200-error-page can never become today's fresh snapshot (feeds F9).
9. **`parse_livebench` (#L518, #L530-536):** exclude any column literally named `overall`/`Overall` from the mean; use explicit `is not None` checks instead of `or`-chains so 0.0 scores survive.
10. **`diff_model_catalog` (#L1769-1779):** clamp `first_seen` to `now` when `created` parses to a future date (clock-skew tolerance), and add a unit test with a future `created` + a negative-age run.
11. **Extend `test_benchmark_common.py` with a failure-class suite:** one test per F1/F2/F3/F5/F6/F8 trigger (escaped quotes in values, `}]` in strings, `"nan"` price, missing path, string pricing, missing `display`, string limit). These are one-liners that lock the P1/P2 fixes in place — the current suite's only real gap.

---

## 4. Verified-Correct Highlights (for the record)

- `variant_conflict` (#L127-144): token-prefix-run + variant/digit-surplus rejection is correct; `qwen3-5` vs `qwen-3-5` and `mimo-v2-pro` vs `mimo-v2-5` both correctly conflict (probe-verified); equal ids non-conflict; empty → conflict. Matches memory.md S2-C2 exactly.
- `norm_id` preserves dots/underscores, `norm_model_slug` strips vendor prefixes and folds `qwen-3` → `qwen3` — matches the documented divergence contract (memory.md dedup note).
- Staleness-from-filename (S2-M2): `snapshot_date_str` validates via `strptime` (rejects `20261399`), `pick_latest_raw` orders by filename date before mtime, tests pin "name wins over fresh mtime".
- `atomic_write_text`: genuinely atomic (tmp sibling + `fsync` + `os.replace`, cleanup in `finally`, pid+ns collision-proof name, `with_name` blocks traversal).
- `load_previous_snapshot`: absent = silent, corrupt = loud `WARN` (S1-M2) — tested.
- `compute_meanfill_composite`: missing signals properly skipped, weights renormed over present signals; single-row cohort pins to Q=78 (the model *is* the cohort — no banking violation).
- `diff_model_catalog`: two-set docs-tag diff (S1-M1/S3-F3-2), catalog-wide `first_seen` carry-over, negative-age guard — all tested and correct.
- Pareto cost handling (S2-M1): 0.0 is a real cost, `None` → price sum, unknown → 999 sentinel — tested.
- Z-score std=0 → all-zeros contract pinned (S2-M3).
