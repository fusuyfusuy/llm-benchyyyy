#!/usr/bin/env python3
"""
benchmark_sync_daemon.py — 08:00 Daily Benchmark Sync Daemon & Local Cache Engine

Automatically pulls all upstream benchmark data:
  1. LiveBench (table CSV + categories JSON)
  2. LMArena / Arena.ai (leaderboard HTML)
  3. Artificial Analysis (models leaderboard HTML)
  4. OpenRouter API (models catalog JSON)
  5. CommandCode GOAT Docs (https://commandcode.ai/docs/plans/goat HTML)
  6. Cline Models Feed (models catalog JSON)

Caches dated snapshots in docs/data/raw/ (e.g. livebench_YYYYMMDD.csv, cc_goat_docs_YYYYMMDD.html).
Runs automatically every day at 08:00 local time.
All tools in the suite (bcheck, ccheck, fcheck, scheck, ocheck) read 100% offline from this local cache.
Supports manual sync via --sync-now / --fetch at any time.
"""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import glob
import json
import os
import pathlib
import signal
import sys
import time
import urllib.request
import urllib.error

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

ROOT = HERE.parent
for _p in (HERE.parent, HERE.parent.parent, HERE.parent.parent.parent):
    if (_p / "setup.sh").exists() or (_p / ".git").exists():
        ROOT = _p
        break

DATA = ROOT / "docs" / "data"
RAW = DATA / "raw"
LOGS = DATA / "sync_daemon.log"
LOCK_PATH = DATA / "sync_daemon.lock"

import benchmark_common as bc

# Upstream Source Endpoints
LIVEBENCH_CSV = "https://livebench.ai/table_2026_06_25.csv"
LIVEBENCH_CAT = "https://livebench.ai/categories_2026_06_25.json"
LMARENA_URL = "https://arena.ai/leaderboard/code/webdev"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"
CC_GOAT_DOCS = "https://commandcode.ai/docs/plans/goat"
CLINE_MODELS_URL = "https://api.cline.bot/v1/models"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"


def log(msg: str):
    """Write timestamped log to stderr and LOGS file."""
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, file=sys.stderr)
    try:
        LOGS.parent.mkdir(parents=True, exist_ok=True)
        with open(LOGS, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def fetch_url_content(url: str, timeout: int = 20, max_retries: int = 3) -> str | None:
    """Download text content from URL with realistic User-Agent and exponential backoff retries."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            normalized = text.strip().lower()
            if len(text) < 100 or normalized.startswith(("404", "not found", "<h1>404")):
                raise ValueError(f"invalid response body ({len(text)} bytes)")
            return text
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
            if attempt < max_retries:
                backoff = 1.5 ** attempt
                time.sleep(backoff)
            else:
                log(f"  WARN: Failed to fetch {url} after {max_retries} attempts: {e}")
                return None
    return None


@contextmanager
def sync_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise RuntimeError("benchmark sync is already running") from e
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        yield


def sync_all_sources(verbose: bool = True, force: bool = False) -> dict[str, pathlib.Path | None]:
    """Fetch all upstream benchmark feeds and save dated snapshots to docs/data/raw/."""
    RAW.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    results = {}

    log("=== Starting Upstream Benchmark Synchronization ===")

    # 1. LiveBench CSV
    lb_csv_path = RAW / f"livebench_{today}.csv"
    if lb_csv_path.exists() and not force:
        results["livebench_csv"] = lb_csv_path
        if verbose:
            log(f"  LiveBench CSV cached -> {lb_csv_path.name}")
    else:
        txt = fetch_url_content(LIVEBENCH_CSV)
        if txt:
            bc.atomic_write_text(lb_csv_path, txt)
            results["livebench_csv"] = lb_csv_path
            log(f"  Saved LiveBench CSV -> {lb_csv_path.name} ({len(txt):,} bytes)")

    # 2. LiveBench Categories JSON
    lb_cat_path = RAW / f"livebench_categories_{today}.json"
    if lb_cat_path.exists() and not force:
        results["livebench_categories"] = lb_cat_path
        if verbose:
            log(f"  LiveBench Categories cached -> {lb_cat_path.name}")
    else:
        txt = fetch_url_content(LIVEBENCH_CAT)
        if txt:
            bc.atomic_write_text(lb_cat_path, txt)
            results["livebench_categories"] = lb_cat_path
            log(f"  Saved LiveBench Categories -> {lb_cat_path.name} ({len(txt):,} bytes)")

    # 3. LMArena HTML
    lm_path = RAW / f"lmarena_{today}.html"
    if lm_path.exists() and not force:
        results["lmarena"] = lm_path
        if verbose:
            log(f"  LMArena HTML cached -> {lm_path.name}")
    else:
        txt = fetch_url_content(LMARENA_URL)
        if txt:
            bc.atomic_write_text(lm_path, txt)
            results["lmarena"] = lm_path
            log(f"  Saved LMArena HTML -> {lm_path.name} ({len(txt):,} bytes)")

    # 4. Artificial Analysis HTML
    aa_path = RAW / f"artificial_analysis_{today}.html"
    if aa_path.exists() and not force:
        results["artificial_analysis"] = aa_path
        if verbose:
            log(f"  Artificial Analysis HTML cached -> {aa_path.name}")
    else:
        txt = fetch_url_content(AA_URL)
        if txt:
            bc.atomic_write_text(aa_path, txt)
            results["artificial_analysis"] = aa_path
            log(f"  Saved Artificial Analysis HTML -> {aa_path.name} ({len(txt):,} bytes)")

    # 5. OpenRouter API JSON
    or_path = RAW / f"openrouter_models_{today}.json"
    if or_path.exists() and not force:
        results["openrouter"] = or_path
        if verbose:
            log(f"  OpenRouter JSON cached -> {or_path.name}")
    else:
        txt = fetch_url_content(OPENROUTER_API)
        if txt:
            bc.atomic_write_text(or_path, txt)
            results["openrouter"] = or_path
            log(f"  Saved OpenRouter JSON -> {or_path.name} ({len(txt):,} bytes)")

    # 6. CommandCode GOAT Docs HTML
    cc_path = RAW / f"cc_goat_docs_{today}.html"
    if cc_path.exists() and not force:
        results["commandcode_goat"] = cc_path
        if verbose:
            log(f"  CommandCode GOAT HTML cached -> {cc_path.name}")
    else:
        txt = fetch_url_content(CC_GOAT_DOCS)
        if txt:
            bc.atomic_write_text(cc_path, txt)
            results["commandcode_goat"] = cc_path
            log(f"  Saved CommandCode GOAT HTML -> {cc_path.name} ({len(txt):,} bytes)")

    # 7. Cline Models JSON
    cln_path = RAW / f"cline_models_{today}.json"
    if cln_path.exists() and not force:
        results["cline_models"] = cln_path
        if verbose:
            log(f"  Cline Models JSON cached -> {cln_path.name}")
    else:
        txt = fetch_url_content(CLINE_MODELS_URL)
        if txt:
            bc.atomic_write_text(cln_path, txt)
            results["cline_models"] = cln_path
            log(f"  Saved Cline Models JSON -> {cln_path.name} ({len(txt):,} bytes)")

    # 8. Trigger Suite Baseline Refresh
    try:
        import llm_benchmark_aggregator as lba
        live_map = lba.load_livebench_data(fetch=False)
        lm_map = lba.load_lmarena_data(fetch=False)
        aa_map = lba.load_aa_data(fetch=False)
        cat = lba.build_universal_catalog(live_map=live_map, lm_map=lm_map, aa_map=aa_map)
        lba.calculate_composite_scores(cat)
        models = [m for m in cat.values() if m.get("livebench") or m.get("aa_live_quality") or m.get("base_metrics", {}).get("lm_elo") or m.get("base_metrics", {}).get("aa_quality")]
        prev_snap = lba.load_previous_snapshot(DATA / "benchmarks.json")
        diff = lba.diff_model_catalog(models, prev_snap, id_key="display")
        base_p = lba.save_baseline(models, diff)
        results["baseline_json"] = base_p
        log(f"  Refreshed Master Baseline -> {base_p.name} ({len(models)} evaluated models)")
    except Exception as e:
        log(f"  WARN: Failed to refresh master baseline: {e}")

    log(f"=== Sync Completed: {len(results)} items updated/verified ===")
    return results


def seconds_until_next_target_time(target_hour: int = 8, target_minute: int = 0) -> float:
    """Calculate the number of seconds from now until the next occurrence of target_hour:target_minute in local time."""
    now = dt.datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


def run_daemon_loop(target_hour: int = 8, target_minute: int = 0):
    """Run continuous daily sync loop scheduled at target_hour:target_minute local time."""
    log(f"Starting 08:00 Benchmark Sync Daemon (PID {os.getpid()}). Press Ctrl+C to terminate.")

    # Graceful shutdown handler
    def _term_handler(signum, frame):
        log(f"Received signal {signum}. Terminating daemon gracefully.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term_handler)
    signal.signal(signal.SIGINT, _term_handler)

    while True:
        sec = seconds_until_next_target_time(target_hour, target_minute)
        next_dt = dt.datetime.now() + dt.timedelta(seconds=sec)
        log(f"Next scheduled sync: {next_dt.strftime('%Y-%m-%d %H:%M:%S')} (in {sec/3600:.2f} hours)")

        # Poll in short intervals (up to 30s) to tolerate OS suspend, NTP adjustments, and clock changes
        while True:
            remaining = seconds_until_next_target_time(target_hour, target_minute)
            if remaining <= 5 or remaining > 86350:
                break
            time.sleep(min(30.0, max(1.0, remaining - 2)))

        log("Awakened for scheduled 08:00 sync.")
        try:
            sync_all_sources(verbose=True, force=True)
        except Exception as e:
            log(f"ERROR during scheduled sync: {e}")

        # Sleep past the current target minute to avoid immediate re-trigger
        time.sleep(65)


def get_cache_status() -> dict:
    """Inspect all cached snapshot files and report their status."""
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    feeds = [
        ("LiveBench CSV", f"livebench_{today}.csv", "livebench_[0-9]*.csv"),
        ("LiveBench Categories", f"livebench_categories_{today}.json", "livebench_categories_*.json"),
        ("LMArena HTML", f"lmarena_{today}.html", "lmarena_*.html"),
        ("Artificial Analysis HTML", f"artificial_analysis_{today}.html", "artificial_analysis_*.html"),
        ("OpenRouter Models", f"openrouter_models_{today}.json", "openrouter_models_*.json"),
        ("CommandCode GOAT Docs", f"cc_goat_docs_{today}.html", "cc_goat_docs_*.html"),
        ("Cline Models", f"cline_models_{today}.json", "cline_models_*.json"),
        ("Master Baseline", "benchmarks.json", "benchmarks.json"),
    ]

    status_report = []
    for name, today_name, glob_pat in feeds:
        if name == "Master Baseline":
            p = DATA / today_name
            matches = [p] if p.exists() else []
        else:
            matches = sorted(glob.glob(str(RAW / glob_pat)))

        if matches:
            latest = pathlib.Path(matches[-1])
            mtime = dt.datetime.fromtimestamp(latest.stat().st_mtime)
            size_kb = latest.stat().st_size / 1024
            is_today = latest.name == today_name
            status_report.append({
                "feed": name,
                "latest_file": latest.name,
                "size_kb": size_kb,
                "mtime": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                "is_today": is_today,
            })
        else:
            status_report.append({
                "feed": name,
                "latest_file": "— (missing)",
                "size_kb": 0,
                "mtime": "—",
                "is_today": False,
            })

    sec_next = seconds_until_next_target_time(8, 0)
    next_dt = dt.datetime.now() + dt.timedelta(seconds=sec_next)

    return {
        "status_report": status_report,
        "next_sync": next_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "hours_until_next": sec_next / 3600,
    }


def print_status():
    """Render formatted CLI cache status."""
    st = get_cache_status()
    print("=" * 80)
    print(" BENCHMARK LOCAL CACHE & SYNC DAEMON STATUS")
    print("=" * 80)
    print(f" Next 08:00 Sync: {st['next_sync']} (in {st['hours_until_next']:.2f} hours)")
    print(f" Cache Directory: {RAW.relative_to(ROOT) if RAW.is_relative_to(ROOT) else RAW}")
    print("-" * 80)
    print(f" {'Feed / Dataset':<25} {'Latest Snapshot':<32} {'Size':<10} {'Status':<10}")
    print("-" * 80)
    for r in st["status_report"]:
        stat = "✅ Fresh" if r["is_today"] else "⚠️ Cached" if r["size_kb"] > 0 else "❌ Missing"
        sz_str = f"{r['size_kb']:.1f} KB" if r["size_kb"] > 0 else "—"
        print(f" {r['feed']:<25} {r['latest_file']:<32} {sz_str:<10} {stat:<10}")
    print("-" * 80)


def install_systemd():
    """Generate and configure systemd user service & timer."""
    user_systemd = pathlib.Path.home() / ".config" / "systemd" / "user"
    user_systemd.mkdir(parents=True, exist_ok=True)

    py_bin = sys.executable
    daemon_script = pathlib.Path(__file__).resolve()

    service_content = f"""[Unit]
Description=LLM Benchmark Daily Sync Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory="{ROOT}"
ExecStart="{py_bin}" "{daemon_script}" --sync-now
"""

    timer_content = f"""[Unit]
Description=Run LLM Benchmark Daily Sync at 08:00
Requires=llm-bench-sync.service

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
"""

    service_file = user_systemd / "llm-bench-sync.service"
    timer_file = user_systemd / "llm-bench-sync.timer"

    bc.atomic_write_text(service_file, service_content)
    bc.atomic_write_text(timer_file, timer_content)

    print("Installed systemd user unit files:")
    print(f"  Service: {service_file}")
    print(f"  Timer:   {timer_file}")
    print("\nTo activate and enable the timer:")
    print("  systemctl --user daemon-reload")
    print("  systemctl --user enable --now llm-bench-sync.timer")
    print("  systemctl --user list-timers llm-bench-sync.timer")


def install_cron():
    """Output or append crontab configuration for daily 08:00 sync."""
    py_bin = sys.executable
    daemon_script = pathlib.Path(__file__).resolve()
    cron_line = f'0 8 * * * "{py_bin}" "{daemon_script}" --sync-now >> "{LOGS}" 2>&1'

    print("Crontab entry for daily 08:00 sync:")
    print("-" * 60)
    print(cron_line)
    print("-" * 60)
    print(f'To install, run: (crontab -l 2>/dev/null; echo \'{cron_line}\') | crontab -')


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Sync Daemon & Local Cache Engine (Pulls LiveBench, LMArena, AA, OpenRouter, CommandCode, Cline at 08:00 daily)."
    )
    parser.add_argument("--sync-now", "--fetch", "--once", action="store_true", help="Perform immediate upstream synchronization and exit")
    parser.add_argument("--force", action="store_true", help="Force re-fetch even if today's snapshot already exists")
    parser.add_argument("--daemon", action="store_true", help="Run continuous background daemon sleeping until 08:00 daily")
    parser.add_argument("--status", action="store_true", help="Display local cache snapshot status and next sync time")
    parser.add_argument("--install-systemd", action="store_true", help="Generate systemd user service & timer files (~/.config/systemd/user/)")
    parser.add_argument("--install-cron", action="store_true", help="Display or install crontab line for 08:00 daily sync")
    parser.add_argument("--target-hour", type=int, default=8, help="Target hour for daily sync (default: 8)")
    parser.add_argument("--target-minute", type=int, default=0, help="Target minute for daily sync (default: 0)")

    args = parser.parse_args()

    if args.status:
        print_status()
        return

    if args.install_systemd:
        install_systemd()
        return

    if args.install_cron:
        install_cron()
        return

    try:
        with sync_lock():
            if args.daemon:
                run_daemon_loop(target_hour=args.target_hour, target_minute=args.target_minute)
                return

            sync_all_sources(verbose=True, force=args.force)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
