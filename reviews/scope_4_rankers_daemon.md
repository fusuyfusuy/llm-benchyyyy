# Scope 4 — Free-Model Ranker (fcheck), Stealth Detector (scheck), Benchmark Sync Daemon

Commit `b27355d` · reviewer: ScopeRankersDaemon · date: 2026-09-09
Targets: `checkers/free_model_ranker.py`, `checkers/stealth_model_detector.py`,
`checkers/benchmark_sync_daemon.py` + their three test files.
Non-goals (not audited): aggregator, cost analyzers, shared-math internals.

## Health score: 7.5 / 10 (Moderate)

One P1 (daemon fetch abort on truncated reads), three P2s (fcheck missing
empty-catalog refuse, JSON feeds persisted without validity check, unit tests
polluting the production log), plus P3 polish notes. Scope invariants hold;
KEEP/MISSING and 0-model-refuse paths are tested and correct. No RCE, no data
loss, no auth surface (public feeds by design).

---

## 1. Correctness

### 1.1 fcheck scope invariant — HOLDS
Listed rows come exclusively from OpenCode Zen/Go (`-free` naming) plus the
Cline `free` tier. The OR catalog is validation/enrichment only:
`checkers/free_model_ranker.py:495-509` builds `or_free_by_key` and prints
"validation + price/context only — not listed"; the end-to-end test
`checkers/test_free_model_ranker.py:205-216` asserts no `[OR]` badge and
`[OC]`/`[CLN]` presence. Cross-platform dedup via provider-stripped
`_free_key` (`:79-83`) is covered by `test_free_key_dedups_provider_prefix`.
Live run confirms: `OR catalog: 431 models loaded, 21 free keys … not listed`,
`free total: 8 (OC 8 + CLN 0)`.

### 1.2 `is_free_model` price==0 "dead clause" — RESOLVED, correctly
The old OC price==0 clause was deleted because Zen `/v1/models` entries carry
no `pricing` field (0/64 in the 20260828+20260830 snapshots) — documented in
the ponytail comment at `:519-523`, with reinstatement instructions if
upstream ever ships pricing. `is_free_model` (`:63-76`) itself is still live
and correct for its two remaining call sites: OR-catalog key building
(`:503-508`, string prices `"0"`/`"0.0001"` → float compare) and Cline-claim
validation (`:584-591`). Negative-price guard verified: `"-1"` parses to
`-1.0 ≠ 0.0` → not free (`test_free_model_ranker.py:23`). No dead code
remains; the `:free`-suffix short-circuit (`:66-67`) is a deliberate
trust decision (suffix authoritative), not a bug.

### 1.3 Asymmetric trust: OC authoritative, Cline validated (design note, P3)
Cline candidates are validated with this script's own free check before
appending (S3-F3-1, `:585-591`) — live run correctly drops
`cline-free/longcat-2.0` and `z-ai/glm-5.3-flash` (both paid per OR
`20260909` catalog, verified independently). OC ids are authoritative and
never validated (`:543-551`). Consequence measured today: 5 of 8 OC ids
(`big-pickle`, `deepseek-v4-flash-free`, `muse-spark-1.2-contributor-free`,
`mimo-v2.5-free`, `nemotron-3-ultra-free`) have **no** OR-free match, so they
get fabricated `{"prompt": "0", "completion": "0"}` pricing plus `None`
context (`:551`). Inert today (fcheck renders no price column; composite
ignores price), but any future cost consumer of `free_models.json` would
read invented $0. Recommend tagging unenriched rows (`"price_verified":
false`) or reusing the Cline drop/flag path. Also note `_free_key`
collisions are benign: 11 keys map to paid+`:free` pairs and the builder
prefers the `:free` variant (`:507`).

### 1.4 `compute_meanfill_composite` vs weighted-sum — NO BREACH (documented)
fcheck/scheck call `compute_meanfill_composite` (fcheck `:723`, scheck
`:469`), the mean of available z-scores; bcheck uses a 6-signal renormalized
weighted sum (`llm_benchmark_aggregator.py:1293-1318`). For the 2-signal
fcheck/scheck case the mean *is* the equally-weighted renormalized sum, and
both paths exclude (never mean-fill) missing signals and emit `None`
composites for zero-coverage rows. The shared helper's docstring
(`benchmark_common.py:466-477`) explicitly scopes it to sparse catalogs.
Residual, inherent to the design: Q is cohort-relative over a tiny cohort
(today 8 free rows, 3 with AA, 2 with LMArena), so fcheck Q values are not
comparable to bcheck Q. Already disclosed in payload `sources.note`
(fcheck `:783`). No action.

### 1.5 scheck empty-catalog `--json` refuse — PRESENT; fcheck lacks it (P2)
scheck refuses `--json`/`--html` when the OR catalog yields 0 records
(`stealth_model_detector.py:485-488`, exit 1, S3-F3-6). fcheck has **no**
equivalent guard (`free_model_ranker.py:770-798` writes unconditionally):
total feed+cache loss yields `free_recs == []` → `--json` would overwrite
last-good `docs/data/free_models.json` with an `n_free: 0` payload. Mirror
the scheck guard in fcheck.

### 1.6 Daemon `_fetch_and_save` size gates — adequate for truncation, not for error pages (P2)
Gates (`benchmark_sync_daemon.py:95-103`) vs measured real sizes: livebench
CSV 2000 vs 9410 ✓; categories 200 vs 725 (3.6× — thinnest); lmarena 100k
vs 1.39MB ✓; AA 500k vs 4.63MB ✓; OR 100k vs 709KB ✓; GOAT 50k vs 660KB ✓;
cline 1000 vs 4445 (4.4×). Two holes: (a) the daemon's `fetch_url_content`
(`:74-92`) rejects `<100`-byte/404-prefix bodies, but a 1–5 KB Cloudflare
challenge or JSON error body passes both that check *and* the cline (1000)
and categories (200) gates, and `_fetch_and_save` (`:106-128`) persists raw
text **without JSON/CSV validity parsing** — a poisoned snapshot then sits
as cache until displaced by date. Recommend validating JSON feeds with
`json.loads` (and requiring a `data` key / non-empty list) before save.
(b) Gates can't catch in-range truncations — today's AA snapshot dropped
5.29MB → 4.63MB (−12%) with no alarm. Acceptable; flag only.

### 1.7 `_baseline_collapsed` threshold — CORRECT, conservative by design
`max(50, 50% of prev)` (`:131-144`) only refuses *shrinks*; legitimate
catalog growth can never trip it. 0-model runs are refused earlier
(`:191-192`), both paths covered by hermetic tests
(`test_benchmark_sync_daemon.py:85-105`, `:107-133`). Only residual risk is
a legitimate >50% shrink (mass feed rename/dedup) being held — a safe
failure mode (logs, keeps file). No change.

### 1.8 Lock-file crash behavior — CORRECT
`sync_lock` (`:147-157`) truncates+`flock(NB)`; the kernel releases the lock
on fd close even on crash, so no stale-lock deadlock. The leftover file
holds a stale PID but nothing reads it (no PID check). Lock + log are both
git-ignored (`.gitignore:27-28`, verified via `git check-ignore`; neither is
tracked) — the "lockfile in tracked docs/data" concern is resolved. Minor:
a second process opening with `"w"` truncates the holder's PID cosmetically;
harmless.

### 1.9 Log-file growth + test pollution (P2 test hygiene, P3 ops)
`docs/data/sync_daemon.log` is append-only with no rotation (1375 lines /
~125 KB today) and `log()` writes to the module-global `LOGS`
(`:61-71`). Daemon tests patch `RAW`/`DATA`/fetch but **not** `LOGS`, so
unit runs append mocked lines to the production log — confirmed in situ:
`Saved … (600,000 bytes)` and `MISSING … got 4 bytes` rows (the latter is
literally the `"oops"` failure fixture, 4 bytes) timestamped from the test
run sit in the shipped log. Recommend patching `bsd.LOGS` in tests and
adding log rotation (or a `--max-log-lines` trim).

---

## 2. Robustness

- **KEEP vs MISSING** (`:122-128`): failure with existing *dated* cache →
  KEEP and reuse; without → MISSING/`None`, and callers treat `None` as
  missing, never empty. Tested (`:85-105`). One wording wrinkle: on a fresh
  day with a failed fetch the log says MISSING even though yesterday's
  snapshot remains fully usable by rankers (`pick_latest_raw` is
  date-agnostic) — misleading but harmless.
- **0-model baseline refuse** (`:191-192`): tested, correct.
- **[P1] Narrow except in `fetch_url_content` aborts whole sync on
  truncated reads** (`:85` catches `URLError, HTTPError, TimeoutError,
  OSError, ValueError`). Verified empirically: `http.client.IncompleteRead`
  MRO is `(IncompleteRead, HTTPException, Exception, …)` — neither
  `OSError` nor `URLError` — and `BadStatusLine` likewise escapes. A single
  truncated chunk on the 4.6 MB AA / 1.4 MB LMArena transfer propagates out
  of `_fetch_and_save` (no per-feed try in `sync_all_sources`, `:169-175`),
  skipping all remaining feeds and the baseline refresh in `--sync-now`
  mode (the persistent `--daemon` loop survives via its own `try`, `:246`).
  The rankers' shared `bc.fetch_url` already catches bare `Exception`
  (`benchmark_common.py:65-72`). Fix: widen the daemon handler to
  `Exception` (or add `http.client.HTTPException`), matching `bc.fetch_url`.
- `HTTPError` in the tuple is redundant (subclass of `URLError`) — harmless.

## 3. Performance

- Measured parse cost: OR 709 KB `json.loads` 13 ms + parse 2 ms; AA
  4.6 MB parse 357 ms; LMArena 1.4 MB parse 8 ms. Per-tool cost is fine, but
  fcheck/scheck/bcheck each re-parse the same AA HTML from disk on every
  invocation (~0.4 s × N tools per suite run). P3: consider a parsed-cache
  helper or documenting the redundancy as accepted. No action required.
- Daemon schedule (`:233-252`): absolute-target recompute each cycle, 30 s
  poll slices, 65 s post-sync guard — no cumulative drift; `remaining >
  86350` handles backward clock jumps; suspend/NTP tolerated. Correct.

## 4. Security

All seven feeds are unauthenticated public GETs by design (no keys to leak;
stdlib `urllib` keeps default TLS verification). Integrity rests solely on
TLS + size gates — see 1.6 for the error-page persistence hole (P2). Parsers
are regex/json over untrusted HTML with no `eval`/shell — low RCE risk.
`install_systemd`/`install_cron` write user-local files only. No findings
above P3; note as accepted posture for a public-data benchmark tool.

---

## Remediation list

1. **[P1]** Widen `fetch_url_content` except to include
   `http.client.HTTPException` (or bare `Exception` like `bc.fetch_url`);
   add a truncated-read regression test. (`benchmark_sync_daemon.py:85`)
2. **[P2]** Mirror scheck's S3-F3-6 empty-catalog refuse in fcheck's
   `--json`/`--html` path. (`free_model_ranker.py:770-798` vs
   `stealth_model_detector.py:485-488`)
3. **[P2]** Validate JSON feeds (`json.loads` + expected top-level shape)
   inside `_fetch_and_save` before persisting; consider raising the
   `livebench_categories` (200) and `cline_models` (1000) gates.
   (`benchmark_sync_daemon.py:95-103`, `:106-128`)
4. **[P2]** Patch `bsd.LOGS` to tmp in daemon tests; add log rotation/trim.
   (`benchmark_sync_daemon.py:61-71`,
   `checkers/test_benchmark_sync_daemon.py:60-133`)
5. **[P3]** Tag OC rows lacking OR confirmation (`price_verified: false`)
   instead of silent fabricated `$0`. (`free_model_ranker.py:546-551`)
6. **[P3]** Fix MISSING-vs-yesterday wording; note AA-drop observability.
   (`benchmark_sync_daemon.py:122-128`)

## Verification performed

- Ran `free_model_ranker.py --check --plain` (8 rows, correct OC/CLN
  split, 2 Cline drops with reasons) and `stealth_model_detector.py
  --check --plain` (0 stealth, clean empty-table path).
- Independently recomputed all four Cline drop/merge decisions and all 8
  OC enrichment hits/misses against `openrouter_models_20260909.json`.
- Empirically confirmed `IncompleteRead` escapes the daemon's except tuple.
- Measured real snapshot sizes vs every size gate; timed OR/AA/LMArena
  parses; confirmed lock/log git-ignore status and test-line pollution in
  the production log.
