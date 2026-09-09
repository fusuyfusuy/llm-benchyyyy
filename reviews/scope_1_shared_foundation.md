# Scope 1 Audit — Shared Foundation & Math

**Scope:** `checkers/benchmark_common.py` (2052 lines) + `checkers/test_benchmark_common.py` (637 lines). Non-goals: aggregator, cost analyzers, rankers, daemon (referenced only as consumers).
**Auditor:** ScopeSharedFoundation · **Commit:** `b27355d` · **Date:** 2026-09-09
**Method:** targeted range reads + adversarial runtime probes (every crash/value below was executed, not inferred).
**Tests:** suite passes (29+ tests); probes below cover what the suite does not.

---

## 1. Executive verdict

**Health score: 8.2 / 10** — *Moderate band (7.0–8.4). Strong core, defensive gaps at the edges.*

The mathematical core, normalization layer, staleness layer (filename-date authority), `diff_model_catalog` two-set semantics, `load_previous_snapshot` loud-corrupt handling, and `atomic_write_text` are **correct and probe-verified**. The old std-dev drift (`stdev` vs `pstdev`) is **fixed** — all three z-primitives now use population `pstdev`. No RCE, no data-loss, no crash-loop, nothing in the <7.0 Critical band.

The residual risk concentrates in four moderate defects: a **10.7-second ReDoS** in `strip_tier_tokens`, a **NaN crash path** into `get_z_scores` reachable through `parse_lmarena`'s unguarded `float(rating)`, **single-bad-record kills whole-source** parsing in `parse_lmarena`, and **NaN→Q=99.9 fabrication** in `compute_capability_q`. Plus invariant drift (zero-fill vs None-passthrough z-scores), tier-strip bypass of the variant guard, silent `fetch_url`, and raising staleness helpers. The 2026-08-27 incident class (silent whole-source parse loss → stale cache marked fresh) is **narrowed but not closed**.

**Invariant status:**

| Invariant | Status |
|---|---|
| Pure stdlib, zero deps | ✅ Compliant (imports are stdlib-only, lines 8–24) |
| Offline by default; staleness from filename `_YYYYMMDD`, not mtime | ✅ Compliant — `snapshot_date_str` / `pick_latest_raw` / `snapshot_age_hours` key on filename date; midnight-UTC anchoring overcounts ≤24h (P3) |
| Never mix AA live vs static scales in one z-distribution | ✅ Held (aggregator cohort split); shared primitive no longer drifts on std (all `pstdev`) |
| Missing signals NEVER banked at cohort mean | ⚠️ **Breached (latent):** `get_z_scores` zero-fills missing at z=0.0→Q=78; `compute_meanfill_composite` correctly skips; aggregator reimplements `_z_scores` with None-passthrough. Two divergent primitives = drift |
| Fail-fast, no swallowed errors | ⚠️ **Breach-leaning:** `parse_lmarena`/`parse_aa`/`fetch_url` swallow failures to `{}`/`None` silently at default verbosity; no post-parse sanity gate, so "broken parse" ≡ "source has no data" |
| Corrupt baseline is loud, cold-starts either way | ✅ Compliant — `load_previous_snapshot` WARNs on stderr and returns None (verified) |
| Atomic crash-safe writes, inputs never mutated | ✅ Compliant — tmp+fsync+`os.replace`+cleanup verified, no tmp leftovers; `diff_model_catalog` copies rows (test-pinned). Missing only parent-dir fsync (P3) |

---

## 2. Findings

### P1 — fix next cycle (High)

**F1. Catastrophic ReDoS in `strip_tier_tokens` — 10.7 s on a 30 KB model id.**
`checkers/benchmark_common.py:118` — `re.sub(r"(\d+)(xhigh|high|medium|low|minimal|max)$", …)`.
`(\d+)` + 6-way alternation + `$` anchor backtracks O(n·m) when the suffix never matches. Probe: `"1"*30000` → **10.737 s**. Model ids flow from upstream payloads (AA/LMArena/OpenRouter) into `strip_tier_tokens` on every `find_*` call, so one poisoned upstream string stalls every checker run. All other regexes in the file probed linear (≤0.001 s at 50 KB).
*Fix:* replace the regex with a suffix loop, e.g. split trailing digit-run once (`re.match(r"^(.*?\d)[-_]?(xhigh|high|…)$", …)` with the digit part made possessive via a single `rstrip`-style scan) or plain `str.endswith` checks over the 6 suffixes. Add a 5 KB-input perf test.

**F2. `get_z_scores` hard-crashes on NaN/Inf; counts booleans as numbers.**
`checkers/benchmark_common.py:291–306`. `isinstance(v, (int,float))` admits `bool`, `nan`, `inf`; `statistics.pstdev` then raises `ValueError: inf or nan encountered in data` (probe-confirmed for both `nan` and `inf` cohorts) — a whole-run crash from one poisoned value. Separately, `get_z_scores([True, False, 1.0])` → `[0.7, -1.4, 0.7]`: booleans skew the cohort mean/std.
*Fix:* filter with `isinstance(v, bool)` exclusion and `math.isfinite(v)` in both the `valid` list and the output guard; all-NaN cohort → all-`0.0`.

**F3. `parse_lmarena`: one bad record (or one `}]` in a string) silently drops the entire LMArena source.**
`checkers/benchmark_common.py:601–638`. Three stacked defects: (a) block end found with escape-unaware `unescaped.find("}]", idx)` (line 607) — any `}]` inside a name/notes/description truncates the JSON → `json.loads` fails → `except: pass` → falls to the legacy table path → `{}`; (b) the `try` at line 611 wraps the **whole entries loop**, so one record with non-numeric `rating` (`round(float(rating),0)`, line 620 — note: `float("nan")` *succeeds*, storing `nan`, which then triggers F2 downstream), a dict `rating` (`float({})` raises), or a string `contextLength` (`ctx//1000`, line 626 raises) discards every good record in the block; (c) failure is silent at default verbosity. Probe: garbage/empty inputs return `{}` (good), but `parse_lmarena(None)` raises `AttributeError` (P3).
*Fix:* per-record `try` inside the `for e` loop; guard `rating` with `_safe_float` (never bare `float()`); guard `contextLength` with `_safe_int`; replace `find("}]")` with a quote-aware scan (same disciplined pattern `parse_aa` already uses at lines 720–738); `if not html_text: return {}` entry guard.

**F4. `compute_capability_q(nan)` fabricates top-of-scale Q=99.9 (with P_succ=0.0).**
`checkers/benchmark_common.py:316` — `max(40.0, min(99.9, 78.0 + nan))` → `min(99.9, nan)` returns `99.9` in CPython. Probe: `nan→99.9`, `inf→99.9`; `compute_p_success(nan)→0.0`, so one NaN yields the incoherent pair **Q=99.9 with P=0.0**; `compute_avi(80, nan)→873.1`, `compute_bfi(80,100,nan)→800.0` (garbage in, ranked out). Reachability is real: F3's `float(rating)` path stores `nan` without `_safe_float` filtering, and `compute_meanfill_composite`'s `fmean` propagates any `nan` that reaches it straight into `compute_capability_q` (line 500). `_safe_float` itself correctly rejects NaN/Inf in both numeric and string paths — the hole is that `compute_*` re-admits them.
*Fix:* `if cz is None or not isinstance(cz,(int,float)) or isinstance(cz,bool) or not math.isfinite(cz): return 78.0` (and analogous `math.isfinite` guards in `compute_p_success`→0.0, `compute_avi`/`compute_fgi`/`compute_bfi`→0.0, `compute_token_multiplier`→100.0).

### P2 — fix eventually (Moderate)

**F5. `get_z_scores` zero-fills missing entries at the cohort mean — the behavior the suite's own invariant forbids.**
`checkers/benchmark_common.py:306` vs `checkers/llm_benchmark_aggregator.py:1215–1229`. Probe: `get_z_scores([None,70,80,90])` → `[0.0,…]` — the missing entry banks z=0.0→Q=78. Currently masked (ocheck/ccheck index `z[i]` only when the source value is non-None; `compute_meanfill_composite` skips missing), but it is why the aggregator maintains a second, correct `_z_scores` (None-passthrough + weight renormalization). Two divergent z-primitives is textbook invariant drift and a loaded footgun for the next consumer.
*Fix:* adopt None-passthrough in `get_z_scores` (major-version flag if any blind indexer exists — audit shows none: all readers guard) or, at minimum, document the footgun on the docstring and add a test pinning the divergence as intentional.

**F6. Stage-1 tier-stripping bypasses `variant_conflict`: `non`/`reasoning` treated as tiers.**
`checkers/benchmark_common.py:100–104` (`TIER_TOKENS` contains `non`, `reasoning`, `base`, `preview`, `auto`), `:115–122`, `:840–853` (+ LM/LiveBench twins at 867–881, 916–930). `strip_tier_tokens("glm-5-2-non-reasoning")` → `"glm-5-2"`, so stage 1 links a **non-reasoning record to a base query** although `variant_conflict` correctly returns `True` for the pair — stage 1 never consults it. Same for `-base` (real base-checkpoint vs instruct-tuned conflation) and `-preview`/`-auto`. Over-strip extremes: `strip_tier_tokens("claude-high")` → `""`, `"gpt-next"` → `"gpt"`.
*Fix:* remove capability-distinctive tokens (`non`, `reasoning`, `base`, `preview`) from `TIER_TOKENS` (keep pure effort/tier: `high/medium/low/minimal/xhigh/max/effort/thinking`); AND-gate stage 1 with `not variant_conflict(sn, norm_model_slug(slug))`; never return on an empty stripped key.

**F7. Size/context suffixes false-link: `llama-3` resolves to `llama-3-70b`.**
`checkers/benchmark_common.py:132–149`, `:884–903`. Surplus token `70b` is neither in `VARIANT_TOKENS` nor pure-digit, so `variant_conflict("llama-3","llama-3-70b")` → `False` (probe-confirmed both 70b and 8b; `find_aa_for_model("llama-3",…)` returns the 70b record by dict order; OpenRouter twin resolves `llama-3` → first size variant). Same class: `model`↔`model-200k/128k` (context), `model`↔`model-v2` (version), `model-2024` date suffixes link only when pure-digit (correct) but `70b`-style alphanumeric sizes slip through. A bare family query silently inherits one member's benchmarks.
*Fix:* treat trailing size tokens (`\d+[bmkt]` + optional `b`, e.g. `8b/70b/200k/1m`) and version tokens (`v\d+`, 4-digit dates) as conflicts in `variant_conflict`; make `find_or_for_model` deterministic on ambiguity (prefer exact, else `None` instead of first-dict-order).

**F8. `fetch_url` is silent, single-shot, unbounded.**
`checkers/benchmark_common.py:65–72` (plus a drifted duplicate at `llm_benchmark_aggregator.py:1073`). Swallows every exception to `None` with no log; no retry on transient 5xx/timeout; no status/empty-body distinction (truncated 200 with 0 bytes saves as today's snapshot upstream of the 2026-08-27 incident chain); `resp.read()` unbounded (no size cap); always UTF-8-`replace` (ignores charset); `urllib` follows redirects silently with a frozen 2023 Chrome/120 UA (increasingly bot-walled). Callers treat `None`≡`""` (`if body:`), so failure ≡ empty source.
*Fix:* stderr WARN on failure (not `verbose`-gated); 1 retry with backoff on timeout/5xx; `Content-Length`/byte-cap guard (~50 MB); consolidate the aggregator duplicate onto `bc.fetch_url`.

**F9. Staleness helpers raise on missing paths instead of reporting "missing".**
`checkers/benchmark_common.py:251–260`, `:263–269`. Probe: `snapshot_age_hours("/nonexistent/f.json")` → `FileNotFoundError`; `staleness_tag(None)` → `TypeError`. Most callers guard via `pick_latest_raw`→None first, but any unguarded call turns an offline run into a traceback instead of a "source missing" banner.
*Fix:* `snapshot_age_hours` returns `None` (or `inf`) on missing/unstatable; `staleness_tag` accepts `None` → `" (missing — run with --fetch)"`; type the contract.

**F10. `parse_openrouter` crashes on non-dict records or non-dict `pricing`.**
`checkers/benchmark_common.py:789–797`. No per-record isolation and no `isinstance` guards: a list entry that isn't a dict (`rec.get`, line 791) or `pricing` as a string (`pricing.get`, line 795) raises `AttributeError` out of the whole parse (uncaught inside; callers happen to wrap, but the entire source is lost). `parse_openrouter(None)`→`{}` and string-price coercion both verified tolerant — only the shape guards are missing.
*Fix:* `if not isinstance(rec, dict): continue`; `if not isinstance(pricing, dict): pricing = {}`.

**F11. `parse_aa` tries only the best array; pre-unescape breaks quote tracking.**
`checkers/benchmark_common.py:700`, `:739–767`. The full-text `replace('\\"', '"')` before scanning means a legitimately escaped quote in a model name becomes a bare `"` that closes the depth-tracker's string early → wrong `]` → `json.loads` throws → `return {}` with no fallback to the next candidate array and no loud warning. Per-model loop itself is safe (`_safe_float` never raises; missing slug skipped). 4.6 MB scan measured 0.03 s — no perf issue.
*Fix:* scan the raw text with escape-aware quote tracking (handle `\"` inside the tracker instead of pre-replacing); on `json.loads` failure, continue to the next candidate `idx` before giving up; loud stderr WARN when zero models parse from non-empty input.

### P3 — polish / hardening (Minor)

- **F12. `parse_livebench` `or`-chains + `overall` double-count.** Lines 567, 579–585: `cat_scores.get("Coding") or …` treats a legitimate `0.0` as missing; `overall` averages *every* numeric non-`model`/`nq_`/`out_` column, so a precomputed `overall`/`coding` summary column in the CSV would be double-counted. Duplicate slugs silently last-win; bad `categories_json` silently ignored. *Fix:* `is not None` chains; exclude known summary columns from `overall`; first-win or warn on duplicates.
- **F13. `parse_*` reject `None` with `AttributeError`.** `parse_lmarena(None)` / `parse_aa(None)` raise on `.replace` (probe-confirmed); `parse_livebench(None)` happens to return `{}`. *Fix:* `if not html_text: return {}` guards (then F9-style callers are safe by construction).
- **F14. `compute_*` type gaps.** `compute_avi(-1.2, 5.0)` raises `TypeError` (negative `**2.2` → complex → `round`); `compute_effective_cost("abc", 2.0)` → `ValueError`; `compute_cost("a",…)` → `TypeError`; `compute_token_multiplier(50, alpha=-5.0)` → `-3.0` (negative retry cost); `compute_cost` passes through negative rates (`-0.0002`). Normal pipeline clamps Q first, so reachability is direct-call only. *Fix:* `math.isfinite` + sign guards per F4; `alpha` validated `> 0`; `compute_cost` coerces via `_safe_float` or raises a documented `TypeError`.
- **F15. Strict-shape helpers.** `comp_key` (`:504–512`) and `compute_meanfill_composite` (`:466–501`) raise `KeyError` on rows missing `benchmarks`/`model_id` keys (probe-confirmed); meanfill propagates `fmean(nan)` → `nan` composite → F4. *Fix:* `.get` chains + `math.isfinite` filter on `aa_vals`/`lm_vals`.
- **F16. `atomic_write_text` missing parent-dir fsync.** Lines 152–168 verified correct (tmp+fsync+replace+cleanup, no leftovers, `IsADirectoryError`/`FileNotFoundError` propagate honestly). Only gap: the directory entry itself is never fsynced, so the rename may not survive an OS crash. *Fix:* fsync the parent fd after `os.replace` (best-effort, guarded).
- **F17. Snapshot-date edge polish.** Future-dated files clamp to age 0 (verified, correct); `snapshot_date_str` correctly rejects `20261345`/`20260230`; midnight-UTC anchoring over-ages same-day snapshots by up to ~24 h (WARN fires early); `parse_timestamp(True)` → epoch 1970 (bool is `int` subclass; `created: true` from upstream would stamp 1970). *Fix:* `isinstance(val, bool)` rejection in `parse_timestamp`.
- **F18. Output encoding good; input entities un-decoded; UA stale.** `html_lib.escape` correctly applied at HTML render sites (verified — only-`escape` usage); but parsed names keep entities (`&amp;` survives into slugs). UA frozen at Chrome/120 (2023). *Fix:* `html_lib.unescape` on title/name fields before slugging; refresh UA periodically.
- **F19. Performance (measured, not a problem except F1).** Pareto sweep is O(n²) but 513 rows → 0.015 s, 1000 → 0.056 s — fine at this catalog scale. `parse_aa` bracket scan 4.8 MB → 0.03 s. Residual waste: `find_*` recomputes `norm_model_slug`/`strip_tier_tokens` per candidate per query (O(Q·M) regexes across catalog joins) — memoize normalizations per map if catalogs grow 10×.

---

## 3. Remediation list (ordered)

**P1 (next cycle):**
1. F1: replace suffix regex with `endswith` loop + add adversarial-size perf test.
2. F4: `math.isfinite` + bool guards on all `compute_*` entry points.
3. F2: `math.isfinite` + bool filter in `get_z_scores`.
4. F3: per-record isolation + `_safe_float` rating + `_safe_int` context + quote-aware block end + empty-input guard in `parse_lmarena`.

**P2 (eventually):**
5. F5: unify z-primitives (None-passthrough) or pin the divergence as intentional + tested.
6. F6: prune `TIER_TOKENS` to pure effort/tier; AND-gate stage 1 with `variant_conflict`.
7. F7: size/version/date surplus tokens → conflict; deterministic ambiguity (no dict-order wins).
8. F8: loud WARN + 1 retry + byte cap in `fetch_url`; delete the aggregator duplicate.
9. F11: escape-aware `parse_aa` scan + try-next-array fallback + loud empty-parse WARN.
10. F10: `isinstance` guards + per-record isolation in `parse_openrouter`.
11. F9: `None`-tolerant staleness contract.

**P3 (polish):** F12–F19 as listed; each is a ≤5-line change with a pinned test.

---

## 4. Test-gap notes (`test_benchmark_common.py`)

The suite pins the important contracts (variant/digit rejection, zero-std, two-set docs diff, 0.0-cost Pareto, filename-date authority, input non-mutation). Missing coverage that would have caught the above: NaN/Inf cohorts for `get_z_scores`; `compute_capability_q(nan)`; `parse_lmarena` with a `}]`-in-string and a dict-rating record; `parse_openrouter` with non-dict rec/pricing; `strip_tier_tokens` adversarial-length timing; `0.0`-valued LiveBench categories; `staleness_tag(None)`; `parse_timestamp(True)`. Recommended: one test per P1 fix, none permanent beyond that (per throwaway-script-first policy — each reproduces pre-fix, passes post-fix).

---

## 5. Probe log (all executed 2026-09-09, `checkers/` on `sys.path`)

- `variant_conflict`: `llama-3|70b→False`, `model|200k→False`, `model|v2→False`, `qwen3-5|7→True`, `model|pro→True`, `gpt-4|turbo→True` — size/context/version surplus under-discriminates.
- `strip_tier_tokens`: `llama-3-base→llama-3`, `gpt-next→gpt`, `qwen-non-reasoning→qwen`, `claude-high→""`, regex `(\d+)(…)$` on 30k digits → **10.737 s**.
- `get_z_scores([nan,1,2])` / `[inf,1,2]` → `ValueError`; `[True,False,1.0]` → bool-skewed scores.
- `compute_capability_q(nan/inf)→99.9`, `("bad")→ValueError`; `compute_avi(-1.2,5)→TypeError`; `compute_avi(80,nan)→873.1`; `compute_token_multiplier(50,alpha=-5)→-3.0`; `compute_effective_cost("abc",2)→ValueError`; `compute_cost("a",..)→TypeError`.
- `parse_openrouter(None)→{}`, bad-pricing tolerated; `parse_livebench(None/"" /bad-cats)` tolerant; `parse_lmarena(None)` / `parse_aa(None)` → `AttributeError`.
- `parse_aa` 4.8 MB synthetic → 0.03 s; Pareto 100/513/1000 rows → 0.001/0.015/0.056 s.
- `diff_model_catalog`: future `first_seen`→not-new (correct); dup ids→dup rows; cold start→no green (correct); naive `now` accepted; `parse_timestamp(True)`→1970 epoch.
- `atomic_write_text`: content correct, no tmp leftovers, dir-target→`IsADirectoryError`, `/proc`→`FileNotFoundError`.
- `snapshot_age_hours(missing)`→`FileNotFoundError`; future file age 0; `20261345`/`20260230`→`None`.
- `find_aa("llama-3", {70b:80, 8b:60})`→70b record (dict-order win); `comp_key({model_id})`→`KeyError`; meanfill missing keys→`KeyError`, nan→`nan` mean propagation.
