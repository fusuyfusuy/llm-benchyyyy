# Seams & Interfaces Audit Report

## 1. Shared Utilities & Math Seam
**Violation:** Redefined Utilities (Violation of Ponytail - reuse repo code)
Functions implemented in `checkers/benchmark_common.py` are duplicated across the checker scripts despite being imported as `bc`.
- `_safe_float`: Duplicated in `opencode_cost_benefit_analyzer.py:448`, `commandcode_cost_benefit_analyzer.py:338`.
- `_safe_int`: Duplicated in `opencode_cost_benefit_analyzer.py`, `commandcode_cost_benefit_analyzer.py`.
- `_safe_int_round`: Duplicated in `opencode_cost_benefit_analyzer.py`, `commandcode_cost_benefit_analyzer.py`.
- `pick_latest_raw`: Duplicated in `free_model_ranker.py:84`, `commandcode_cost_benefit_analyzer.py:140`, `opencode_cost_benefit_analyzer.py:64`, `stealth_model_detector.py:59`.
- `display_len`: Duplicated in `opencode_cost_benefit_analyzer.py`, `commandcode_cost_benefit_analyzer.py`.

## 2. CLI Entrypoint Seam
**Violation:** Tight Coupling / Module Loading
While `pyproject.toml` correctly maps entrypoints like `bsync = "checkers.benchmark_sync_daemon:main"`, the files rely on a `sys.path.insert(0, str(HERE))` hack to resolve relative imports (`import benchmark_common as bc`).

## 3. Daemon & System Integration Seam
**Violation:** Bypassing CLI Entrypoint
In `checkers/benchmark_sync_daemon.py`, the `install_systemd()` and `install_cron()` methods generate configurations that bypass the `bsync` CLI entrypoint defined in `pyproject.toml`.
- Systemd ExecStart: `ExecStart={py_bin} {daemon_script} --sync-now` (approx line 324)
- Cron entry: `0 8 * * * {py_bin} {daemon_script} --sync-now >> {LOGS} 2>&1` (approx line 360)
These should invoke `bsync --sync-now`.

**Violation:** Snapshot Contract Drift
All checkers are supposed to be offline by default with `docs/data/raw/` caching. However, `fcheck` and `scheck` violate this by defaulting to network fetch and mutating `docs/data/raw/` files unconditionally on dry runs.

## 4. Invariant Contracts (AGENTS.md)
**Violation:** Cyclomatic Complexity (CC <= 10)
The rule `CC <= 10, depth <= 3` is ignored universally.
- `opencode_cost_benefit_analyzer.py:1301 main` (CC=205)
- `commandcode_cost_benefit_analyzer.py:633 main` (CC=139)
- `free_model_ranker.py:462 main` (CC=102)
- `stealth_model_detector.py:288 main` (CC=65)
- `benchmark_sync_daemon.py:82 sync_all_sources` (CC=34)

**Violation:** No Swallowed Exceptions
Exceptions are swallowed explicitly, violating fail-fast principles:
- `opencode_cost_benefit_analyzer.py:1612` (`except Exception: pass`)
- `opencode_cost_benefit_analyzer.py:1663` (`except Exception: pass`)
- `opencode_cost_benefit_analyzer.py:1686, 1690, 1695` (`except Exception: continue`)
- `benchmark_sync_daemon.py:67` (`except Exception: pass`)

## Scoring
**Critical <7.0:** The failure to adhere to system boundaries (Daemon bypasses entrypoint), severe data tracking inconsistencies (unconditional writing to raw snapshots during dry-runs), massively bloated cyclomatic complexity, and explicit violation of fail-fast guarantees (swallowed exceptions) warrant a severe penalty.
**Score: 6.5 (Critical)**
