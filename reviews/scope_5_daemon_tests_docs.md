# Scope 5 Audit — Sync Daemon, Tests, Docs & Data Contracts

**Auditor:** Scope 5 (Sync Daemon, Tests, Docs & Data Contracts)
**Date:** 2026-09-01
**Scope:** `checkers/benchmark_sync_daemon.py`, `checkers/test_*.py` (all), `docs/data/*.json`, `docs/data/raw/*`, `pyproject.toml`, `README.md`, `docs/models.md`, `.gitignore`/`.env`
**Method:** `mimori slice` on `benchmark_sync_daemon.py` symbols + targeted `read_file`/`grep`/`shell` verification, full unittest suite execution. No subagents.

---

## Executive Summary

**Health Score: 7.1 / 10 — Moderate (low end).**

The daemon's core scheduling math, signal handling, atomic writes, installer path-quoting (previously flagged as a shell-injection risk), and the "offline by default / filename-staleness" invariants are all **correct and verified**. The test suite is substantial (102 tests, all green, hermetic w.r.t. real network — no `urlopen`/`requests`/`socket` in any test).

However, the audit surfaced **one Critical invariant breach with live, dated evidence** and several Moderate robustness gaps:

1. **CRITICAL — The daemon's own mocked test (`test_sync_all_sources_mocked`) overwrites the real, git-tracked `docs/data/benchmarks.json`** (verified by md5 before/after test execution; the tree was restored post-audit). The test patches `bsd.RAW`/`bsd.DATA` but the baseline-refresh step calls `llm_benchmark_aggregator.save_baseline(models, diff)` with a **default `path`** that resolves to the **real** `lba.DATA` — silently writing a 35-row synthetic catalog over the 35-row real baseline. This violates the invariant "**Keys/data never touch tracked files**" and the general hermeticity contract for the suite's own data.
2. **CRITICAL — `sync_daemon.log` shows 119 "14 bytes" snapshot-write events.** "404 Not Found\n" is exactly 14 bytes: `fetch_url_content` treats any 2xx/3xx HTTP status (including `404 Not Found`) as success and `atomic_write_text` then **atomically replaces a good multi-MB snapshot with a 404 body** — no size floor, no content sniff, no `HTTPError` for >=400. Evidence: log lines 12–18 (`livebench_20260901.csv (14 bytes)`), plus baseline collapse 1146 → 30 → 35 "evaluated models". This is the single most dangerous production path in the daemon.
3. **HIGH — No pid/lock file.** Two concurrent `--daemon`/`--sync-now`/cron-timer invocations run in parallel; nothing prevents a second process from racing `--force` re-fetches against the first (the log shows 4–8 overlapping sync runs within minutes). Combined with (2), a concurrent 404 can destroy a snapshot that a parallel run had just refreshed.
4. **MODERATE — `seconds_until_next_target_time` uses naive local `datetime`.** DST shifts make the returned seconds wrong by ±1h on transition days (verified: Europe/Berlin spring-forward returns 6.5h when real elapsed time is 6h). Tests only cover the non-DST happy path. Severity is mitigated because the poll loop re-computes every ≤30s.
5. **MODERATE — `run_daemon_loop` has no `--sync-now` equivalent, no failure counter, and does not regenerate baseline freshness on transient upstream failure** (baseline silently reflects whatever partial data survived). Signal handling is correct (SIGTERM/SIGINT → `sys.exit(0)`), and the polling design is suspend-tolerant, but there is no crash-restart story other than the systemd timer `Persistent=true`.

**Docs/data contract:** 7/8 daemon feeds' `_YYYYMMDD` filename convention matches `snapshot_date_str`/`pick_latest_raw` expectations and `docs/data/*.json` schemas match the producers. Minor drift: `README.md`/`docs/models.md` do not document `bsync` at all (only `pyproject.toml` registers the `bsync` entrypoint), the daemon's module docstring claims "6 feeds" while it actually manages 8, and 18 raw snapshot families (opencode zen/go, ocgo_usage, swe_rebench) are maintained by the individual checkers, not the daemon — a maintenance seam, not a breach.

**Invariant breaches:**
- ❌ "Never commit/keys/data touch tracked files" — test clobbers `benchmarks.json` (P1); 14-byte 404 writes overwrite tracked snapshots (P1).
- ✅ "Pure stdlib, no 3rd-party deps" — held (`dependencies = []`; stdlib only).
- ✅ "Offline by default; network only via --fetch/--sync-now" — held in production code (all tests mock network).
- ✅ "Staleness from FILENAME _YYYYMMDD" — held; daemon writes UTC-dated names; `snapshot_date_str` parses them.
- ✅ "UTC dates for snapshots" — held (`dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")`).
- ✅ "Fail-fast; no swallowed errors" — **mostly held**; `sync_all_sources`' baseline step catches `Exception` broadly and only logs (by design), and `fetch_url_content` returns `None` on network errors (by design), but neither is a silent swallow of *data corruption*.

---

## Audit Dimensions

### 1. Correctness

| Symbol | Verdict | Notes |
| :-- | :-- | :-- |
| `sync_all_sources` (L88–205) | **Correct structure; P1 data-guard missing** | 8 feeds (LiveBench CSV/Categories, LMArena, AA, OpenRouter, CC GOAT, Cline + baseline refresh). UTC `today` stamp. `force`/cache short-circuit works. Each feed's write is gated only on `if txt:` — no size/content validation (see finding 2). Baseline step calls `lba.*` with `fetch=False` (offline, correct) but with `save_baseline`'s default path (finding 1). |
| `seconds_until_next_target_time` (L208–214) | **Correct in the common case; DST-naive** | Naive local `datetime.now()`, `replace()`, `+1 day` if `<= now`. Correct for 07:00→08:00 (3600s) and 09:00→next 08:00 (82800s), as the tests assert. Wrong by ±3600s across DST transitions; also breaks if the local timezone has no `08:00` wall time on a transition day. The original "local-time vs UTC mismatch" concern is **resolved**: snapshots use UTC; scheduling uses local time, which is a deliberate and reasonable split (08:00 local trigger, UTC file dates). |
| `run_daemon_loop` (L217–248) | **Correct signal/poll design; gaps** | SIGTERM/SIGINT handlers → `sys.exit(0)` (graceful). Poll loop re-computes target every ≤30s (`remaining <= 5 or remaining > 86350` break; `sleep(min(30, max(1, remaining-2)))`) — genuinely suspend/NTP-drift tolerant. Gaps: no pid lock (finding 3), no retry/backoff on sync failure beyond the next-day cycle, no `--once` in the loop, hard `time.sleep(65)` after sync to avoid re-trigger (fine). |
| `fetch_url_content` (L71–85) | **Retry logic correct; HTTP-status bug** | Exponential backoff `1.5**attempt` (1.5s/2.25s), retries on `URLError/HTTPError/TimeoutError/OSError`, returns `None` on final failure with a log line — good. **But** `HTTPError` is only raised for 4xx/5xx *by urllib when you read the response*; for some servers a `404 Not Found` body is returned with status 200, or (as evidenced) `urlopen` succeeds and the body is the 14-byte "404 Not Found" — the function returns it as valid content. No status-code check, no minimum-size check. |
| Baseline refresh (L187–202) | **Correct pipeline, fragile output** | Loads cached maps offline, builds catalog, computes composite, diffs against `benchmarks.json`, `save_baseline` (atomic). But the whole step is wrapped in a bare `except Exception: log(WARN)` — if parsing collapses (e.g. 14-byte AA/LiveBench snapshots), the baseline is silently rewritten with a tiny catalog (1146 → 30/35 in the log). |

### 2. Robustness

- **Network failure handling:** per-feed `fetch_url_content` returns `None` → feed skipped, snapshot retained, results dict omits the key. Good. But a 404-with-200 status is *not* treated as failure (finding 2).
- **Daemon crash resistance:** a crashed `--sync-now` leaves an atomic tmp cleanup via `atomic_write_text`'s `finally` (no torn files). The systemd timer uses `Persistent=true` (catches up missed runs) — good. No daemon-level watchdog/restart (acceptable; systemd handles it).
- **System suspend/timer drift:** poll loop re-computes after wake; verified logic correct.
- **Pid/lock handling:** **none** (finding 3). `--daemon` twice = two schedulers; cron + timer + manual `--sync-now` can overlap; `--force` concurrent writes race (atomic per-file, but last-writer-wins across a day's snapshots).

### 3. Security

- **`install_systemd` (L322–365) / `install_cron` (L368–378): the previously-flagged path quoting is FIXED and correct.** `ExecStart="{py_bin}" "{daemon_script}" --sync-now` (quoted), `WorkingDirectory="{ROOT}"` (quoted), cron line `0 8 * * * "{py_bin}" "{daemon_script}" --sync-now >> "{LOGS}" 2>&1` (all three quoted). No unquoted interpolation of user-controlled paths. `sys.executable` and `__file__` are not attacker-controlled in the normal install path.
- **Shell injection:** none found; no `os.system`/`subprocess` with string interpolation in the daemon.
- **Credentials:** no hardcoded secrets anywhere in `checkers/` (grep for `sk-*`, `api_key=`, `AIza*` → no matches). `.gitignore` backstops `.env`, `.env.*`, `*.pem`, `*.key`, `credentials*`; no `.env` files exist in the tree; generated systemd/cron configs contain no credentials. Invariant "keys never touch a tracked file" **held**.
- One minor: `install_cron` prints the line but the documented "to install" snippet embeds the line inside single-quoted shell inside an `echo` — safe here (no `'` in paths) but fragile if a future path contains `'`.

### 4. Tests

- **Full suite: 102 tests, all pass** (`python3 -m unittest discover -s checkers`; 3.4s).
- **Hermeticity vs network: held.** No `urlopen`/`requests`/`socket`/`http.client` in any `test_*.py`; all fetch paths are `patch`ed (`fetch_url`, `fetch_url_content`), and the `test_openrouter_models_not_listed` end-to-end test runs `free_model_ranker.py --check` offline (no `--fetch`).
- **Daemon timing logic coverage:** `seconds_until_next_target_time` is directly tested (07:00→3600, 09:00→82800 via `patch("datetime.datetime")`). `get_cache_status` shape tested. `sync_all_sources` mocked-path tested. **Gaps:** no test for `fetch_url_content` retries/backoff/404, no test for `run_daemon_loop` (signal handling, polling, graceful exit), no DST test, no test that `--sync-now`/`--force` flags parse correctly, no test of the baseline-refresh step with a degraded (14-byte) snapshot.
- **Atomic writes:** covered (`TestAtomicWriteAndBaseline` in `test_benchmark_common.py`).
- **Hermeticity vs *data*: BREACHED.** `test_sync_all_sources_mocked` (test_benchmark_sync_daemon.py L58–73) patches `bsd.RAW`/`bsd.DATA` but **not** `lba.DATA`, so the baseline-refresh inside `sync_all_sources` writes the real `docs/data/benchmarks.json` (verified md5 change on test run). `test_free_model_ranker.py::test_cached_json_loader_is_offline_by_default` reads the real cache (read-only — acceptable), and `test_opencode_cost_benefit_analyzer.py::test_offline_parsing` reads real snapshots (read-only — acceptable). Only the daemon test **writes**.

### 5. Docs / Data Contract

- **`docs/data/raw/*` filename convention `_YYYYMMDD`:** all 55 raw files match (`livebench_20260901.csv`, `cc_goat_docs_20260901.html`, …); `snapshot_date_str`/`pick_latest_raw`/`staleness_tag` parse them consistently. ✅
- **`docs/data/*.json` schema vs producers:** `benchmarks.json` = `{generated_at, catalog_diff:{added,removed,total_current}, models[]}` matches `save_baseline` (L2410–2424) exactly. `cc_live.json`/`ocgo_live.json` carry `generated_at`/`sources`/`catalog_diff`/`role_recommendations`/`models` as produced by ccheck/ocheck. `free_models.json`/`stealth_models.json` match fcheck/scheck output shapes. ✅
- **`pyproject.toml`:** registers `bsync = "checkers.benchmark_sync_daemon:main"` alongside the other five entrypoints; `dependencies = []` (pure stdlib). ✅
- **`README.md`:** documents the four "primary" checkers (bcheck/ocheck/ccheck/fcheck/scheck) but **never mentions `bsync`/`--sync-now`/`--status`/the 08:00 scheduler**, and its structure section omits `benchmark_sync_daemon.py`. ❌
- **`docs/models.md`:** harness/model reference; no daemon content (out of scope for it, but confirms the daemon is undocumented project-wide).
- **`.gitignore`:** secrets + Python + editor patterns; raw snapshots and docs JSON are deliberately **tracked** (not ignored) — consistent with "snapshots are the offline cache contract". ✅
- **Daemon docstring drift:** module header says "6 feeds"; actual count is 8. ❌ minor.

---

## Top Findings

### P1-1 — Daemon's mocked test overwrites the real tracked `docs/data/benchmarks.json`
- **Where:** `checkers/test_benchmark_sync_daemon.py:58-73` (`test_sync_all_sources_mocked`), interacting with `checkers/benchmark_sync_daemon.py:187-202` → `checkers/llm_benchmark_aggregator.py:2410-2424` (`save_baseline` default `path = DATA / "benchmarks.json"`).
- **Evidence:** md5 of `docs/data/benchmarks.json` changed `c1e1e792… → 7ad03fef…` across a single run of this test; `generated_at` flipped to the test timestamp; the tree was restored with `git checkout` after the audit.
- **Impact:** running the suite on a clean checkout **rewrites a tracked artifact**, breaking the "data never touches tracked files" invariant and dirtying the tree on every `pytest`/`unittest` run.
- **Fix:** patch `lba.DATA` (or pass an explicit `path=` into the baseline step, or have the test assert the baseline step is *not* invoked with the default path).

### P1-2 — 14-byte "404 Not Found" bodies are saved as authoritative snapshots (119 events in `sync_daemon.log`)
- **Where:** `checkers/benchmark_sync_daemon.py:71-85` (`fetch_url_content`) + L103-185 (each `if txt: atomic_write_text(...)`).
- **Evidence:** `docs/data/sync_daemon.log` lines 12–18, 22–29, 42–49, … (119 "14 bytes" lines); `len("404 Not Found\n") == 14`; baseline refresh collapsed 1146 → 30 → 35 models in the same window; `livebench_20260831.csv` md5 == `livebench_20260901.csv` md5 == `livebench_20260827.csv` md5 (bytes from an older upstream table re-stamped under today's name — `--force` masked it).
- **Impact:** tracked snapshots silently replaced with 14-byte garbage; downstream checkers then read empty/truncated caches and regenerate baselines from near-empty catalogs. The atomic writer makes the corruption *clean* (no torn files) — which is precisely why nothing caught it.
- **Fix:** reject bodies below a per-feed minimum size (e.g. < 100 B for HTML/JSON, < 1 KB for CSV), verify HTTP status (`resp.status < 400`), and refuse to overwrite an existing same-day snapshot unless `--force` AND the new payload passes validation. Consider a schema/content sniff (CSV header contains `model`, JSON starts `{`/`[`, HTML contains `<html`).

### P1-3 — No pid/lock file → concurrent daemon/cron/timer/manual runs race
- **Where:** `checkers/benchmark_sync_daemon.py:217-248` (`run_daemon_loop`) and `main()` (L381-413); no lock anywhere in the module.
- **Evidence:** `sync_daemon.log` shows multiple syncs within the same minute (02:13:51, 02:13:53, 02:18:29, …) — overlapping invocations.
- **Impact:** two `--sync-now` (or timer + manual) runs can interleave `--force` overwrites; combined with P1-2, one process's 404 write can clobber another's fresh snapshot.
- **Fix:** acquire an exclusive lock on `docs/data/.sync.lock` (or `$XDG_RUNTIME_DIR`) via `os.open(..., O_CREAT|O_EXCL)` with PID + stale-lock reclaim, or `fcntl.flock`; release on exit and on signals.

### P2-1 — DST-naive scheduler arithmetic
- **Where:** `checkers/benchmark_sync_daemon.py:208-214`.
- **Evidence:** with `TZ=Europe/Berlin` on 2026-03-29 01:30 local, delta to 08:00 computed as 6.5 h while real elapsed time is 6 h (spring-forward loses an hour).
- **Impact:** on transition days the daemon may fire an hour early/late; the ≤30s poll loop re-computes so it self-corrects within ~1h — Moderate, not Critical. Tests don't cover it.
- **Fix:** compute the target in an explicit zone (e.g. `zoneinfo.ZoneInfo`) or, better, have the scheduler run on UTC with `--target-hour` interpreted in a fixed offset; add a DST test.

### P2-2 — Baseline refresh swallows degradation; no failure accounting in the loop
- **Where:** `checkers/benchmark_sync_daemon.py:187-202` (broad `except Exception` → WARN + continue), `run_daemon_loop` L242-245.
- **Impact:** a sync where 6/8 feeds failed still rewrites `benchmarks.json` from the surviving data (log: 1146 → 30/35 models with zero ERROR lines). No per-feed failure summary in results, no consecutive-failure counter, no alerting.
- **Fix:** track per-feed success/failure in `results`; skip the baseline rewrite if fewer than N feeds succeeded or if the new catalog shrank beyond a threshold vs the previous baseline; log an ERROR (not WARN) with the failure tally.

### P2-3 — `--status`/docs seams and undocumented `bsync`
- **Where:** `README.md` (no `bsync` section), `benchmark_sync_daemon.py:3-17` (docstring says "6 feeds", actual 8), `docs/data/raw/*` (18 files in 4 families managed by ocheck/fcheck/scheck, not the daemon: `opencode_go_*`, `opencode_zen_*`, `ocgo_usage_*`, `swe_rebench_*`).
- **Impact:** operators can't discover the daemon from README; the daemon's `--status`/`get_cache_status` doesn't cover the checker-managed families (its `is_today`/staleness view is incomplete); the docstring misleads.
- **Fix:** document `bsync` (modes: `--sync-now`, `--daemon`, `--status`, `--install-systemd`, `--install-cron`) in README; update the module docstring to 8 feeds; extend `get_cache_status` with the ocheck/fcheck/scheck families or explicitly note they're out of daemon scope.

### P3 — Minor
- `install_cron`'s "to install" echo snippet is single-quote-fragile for paths containing `'` (benchmark_sync_daemon.py:378).
- `get_cache_status` `matches[-1]` relies on sorted lexicographic order == date order (holds for `YYYYMMDD` names, but `pick_latest_raw` is the safer primitive).
- `log()` swallows `OSError` silently when the log file can't be opened (L67-68) — acceptable for a logger, but violates the strict "no swallowed errors" reading.
- `run_daemon_loop`'s inner `while True` can busy-spin if the clock jumps backwards past the target (the `remaining > 86350` guard handles most cases; a `max(1.0, …)` sleep floor already exists).

---

## Remediation Summary

| # | Severity | File:Lines | Fix |
| :-- | :-- | :-- | :-- |
| P1-1 | Critical | `test_benchmark_sync_daemon.py:58-73` | Patch `lba.DATA` in the mocked sync test (or inject `path=`); assert no tracked file is written. |
| P1-2 | Critical | `benchmark_sync_daemon.py:71-85, 103-185` | Enforce per-feed min-size + HTTP status + content-sniff validation before `atomic_write_text`; refuse to overwrite today's snapshot with garbage. |
| P1-3 | Critical | `benchmark_sync_daemon.py:217-248, 381-413` | Add exclusive pid/lock (flock or O_EXCL) with stale-PID reclaim; release on signal. |
| P2-1 | Moderate | `benchmark_sync_daemon.py:208-214` | Zone-aware scheduling (zoneinfo) or UTC target; add DST test. |
| P2-2 | Moderate | `benchmark_sync_daemon.py:187-202, 242-245` | Per-feed failure tally; skip baseline rewrite on degraded sync; ERROR-level logging. |
| P2-3 | Moderate | `README.md`, `benchmark_sync_daemon.py:3-17`, `get_cache_status` | Document `bsync`; fix 8-feed docstring; cover checker-managed raw families in `--status`. |
| P3 | Minor | various | Cron-install quoting; `pick_latest_raw` in status; logger OSError; loop spin guard. |

---

## Verdict

**7.1 / 10 — Moderate.** Architecture and invariants are sound (offline-by-default, UTC filenames, atomic writes, quoted installers, stdlib-only, hermetic-network tests all verified). The score is held down by two Critical, evidenced data-integrity defects — the test that rewrites the tracked baseline, and the 404-as-success snapshot corruption that already fired 119 times in production logs — plus the missing process lock. These three P1s should land before the daemon is trusted as a unattended 08:00 service.
