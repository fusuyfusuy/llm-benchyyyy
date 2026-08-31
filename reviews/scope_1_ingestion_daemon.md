# Scope 1: Upstream Ingestion & Daemon Audit

## Executive Summary
**Health Score:** 7.5 / 10.0 (Moderate)

The ingestion layer and sync daemon provide a decent baseline for daily automated cache updates with zero dependencies. However, several critical robustness and correctness flaws exist, particularly around daemon timing, atomic write concurrency, network failure handling, and time zone mismatching on cache age.

### Invariant Breaches & Top Findings
1. **Concurrency Race in Atomic Writes (`benchmark_common.py#L146-L155`)**:
   - The `atomic_write_text` function hardcodes the temp file as `p.name + ".tmp"`. If two processes (e.g., daemon and a manual `bcheck --fetch`) attempt to write the same file concurrently, they will corrupt each other's temporary files before the atomic rename.
2. **System Suspension / Time Drift Vulnerability in Daemon (`benchmark_sync_daemon.py#L223-L228`)**:
   - The daemon computes `seconds_until_next_target_time` and executes a single `time.sleep(sec)`. If the system sleeps/suspends, or if daylight savings / NTP drift occurs, `time.sleep` will drift significantly.
3. **No Retries on Network Failure (`benchmark_sync_daemon.py#L97-L101`)**:
   - If `fetch_url_content` fails (returns `None`), the daemon silently skips the update. It will not attempt another fetch until the *next day's* scheduled run 24 hours later, leaving the local cache stale.
4. **Timezone Mismatch in Cache Staleness (`benchmark_common.py#L224-L233`)**:
   - `snapshot_date_str` parses dates from the file string (generated via local time `dt.date.today()` in the daemon), but `snapshot_age_hours` compares this against `dt.datetime.now(dt.timezone.utc)`. This causes cache staleness math to be offset by the local machine's UTC offset.
5. **Unsafe Path Escaping in Systemd/Cron Generators (`benchmark_sync_daemon.py#L327` & `#L361`)**:
   - `ExecStart` and the cron line interpolate unquoted `{py_bin}` and `{daemon_script}` variables. If the repository or python path contains spaces, the daemon will fail to start via systemd/cron.
6. **Pure-Python String Parsing Block (`benchmark_common.py#L664-L681`)**:
   - `parse_aa` iterates character-by-character in pure Python over the Artificial Analysis HTML payload to match bracket depth. If the JSON payload is multiple megabytes, this blocks the event loop / CPU unnecessarily.

## Actionable Remediations

### 1. Correctness
- **Fix Timezone Mismatch**: Standardize on UTC dates for cache snapshots (`dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")`), or compare the parsed date against a local timezone-aware datetime rather than UTC.
- **Robust Bracket Parsing**: Replace the manual pure-Python while loop in `parse_aa` with a more efficient stack-based search or a safer regex boundary extraction.

### 2. Robustness
- **Fix Atomic Writes**: Use a randomized or PID-suffixed temp file name (e.g., `f"{p.name}.{os.getpid()}.tmp"`) in `atomic_write_text` to prevent race conditions.
- **Resilient Daemon Sleep**: Replace the long `time.sleep(sec)` with a short polling loop (e.g., checking the clock every 30-60 seconds) to tolerate system suspends and time adjustments.
- **Implement Exponential Backoff**: Wrap `fetch_url_content` with a simple 3-attempt exponential backoff retry loop to handle transient network blips.

### 3. Performance
- **Streaming over Buffering**: For large payloads (like HTML/CSV), use chunked reading (`shutil.copyfileobj`) into the temp file instead of buffering megabytes of data into RAM with `.read().decode()`.
- **Cache Age Caching**: If `glob` performance degrades over years of daily files, store the "latest" filename in a lightweight symlink or manifest file to bypass directory sweeping.

### 4. Security
- **Quote Generated Paths**: In `install_systemd` and `install_cron`, wrap `{py_bin}`, `{daemon_script}`, and `{LOGS}` in double quotes (`"{py_bin}"`) to prevent shell injection or tokenization errors from spaces in paths.
