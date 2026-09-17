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
import http.client
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
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
OCGO_DOCS = "https://opencode.ai/docs/go/"
OCGO_API = "https://opencode.ai/zen/go/v1/models"
OPENCODE_ZEN_API = "https://opencode.ai/zen/v1/models"

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
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, http.client.HTTPException) as e:
            if attempt < max_retries:
                backoff = 1.5 ** attempt
                time.sleep(backoff)
            else:
                log(f"  WARN: Failed to fetch {url} after {max_retries} attempts: {e}")
                return None
    return None


MIN_SNAPSHOT_BYTES = {
    "livebench_csv": 2000,
    "livebench_categories": 200,
    "lmarena": 100_000,
    "artificial_analysis": 500_000,
    "openrouter": 100_000,
    "commandcode_goat": 50_000,
    "cline_models": 1000,
    "opencode_go_docs": 30_000,
    "opencode_go_models": 1000,
    "opencode_zen_models": 2000,
}


def _fetch_and_save(name: str, url: str, path: pathlib.Path, min_bytes: int, force: bool, verbose: bool = True) -> pathlib.Path | None:
    """Fetch url and save dated snapshot. Never overwrites good cache with failure bodies.

    Returns path on fresh save or KEEP-existing cache, None when no usable cache exists.
    Failure (None/tiny body) with existing cache logs KEEP and reuses it; without
    cache logs MISSING. Callers must treat None as missing, never as empty data.
    """
    if path.exists() and not force:
        if verbose:
            log(f"  {name} cached -> {path.name}")
        return path
    txt = fetch_url_content(url)
    if txt and len(txt) >= min_bytes:
        bc.atomic_write_text(path, txt)
        log(f"  Saved {name} -> {path.name} ({len(txt):,} bytes)")
        return path
    if path.exists():
        have = path.stat().st_size
        log(f"  KEEP {name} -> {path.name} ({have:,} bytes, fetch failed — keeping cache)")
        return path
    got = 0 if not txt else len(txt)
    log(f"  MISSING {name} (no cache, fetch failed — got {got} bytes, need {min_bytes:,})")
    return None


def _baseline_collapsed(models: list, prev_snapshot) -> tuple[bool, int]:
    """True when saving would wipe real history: new count < max(50, 50% of prev)."""
    n = len(models)
    if isinstance(prev_snapshot, dict):
        prev_n = len(prev_snapshot.get("models", []) or [])
    elif isinstance(prev_snapshot, list):
        prev_n = len(prev_snapshot)
    else:
        prev_n = 0
    if prev_n <= 0:
        return False, 0
    if n < max(50, int(prev_n * 0.5)):
        return True, prev_n
    return False, prev_n


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


def find_akatsuki_vault() -> pathlib.Path | None:
    """Resolve the Akatsuki vault path from env or canonical location."""
    env_vault = os.getenv("AKATSUKI_VAULT")
    if env_vault:
        p = pathlib.Path(env_vault).expanduser().resolve()
        if p.is_dir():
            return p
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return None
    default_p = pathlib.Path.home() / "configs" / "knowledge-base" / "akatsuki"
    if default_p.is_dir():
        return default_p
    return None


def run_checker_script(script_name: str, args: list[str] | None = None) -> bool:
    """Execute an analysis checker script in a subprocess to refresh its data/reports."""
    script_path = HERE / script_name
    if not script_path.exists():
        log(f"  WARN: checker script {script_name} not found")
        return False
    cmd = [sys.executable, str(script_path)] + (args or [])
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=90)
        if proc.returncode == 0:
            return True
        log(f"  WARN: {script_name} returned exit {proc.returncode}: {proc.stderr.strip()[:200]}")
        return False
    except Exception as e:
        log(f"  WARN: Failed to execute {script_name}: {e}")
        return False


def refresh_suite_results(results: dict, verbose: bool = True) -> dict[str, bool]:
    """Run all downstream analysis checkers to refresh prices, limits, and ranking databases."""
    status = {}
    if verbose:
        log("  Refreshing OpenCode Go pricing & cost/benefit (ocgo_live.json)...")
    status["ocgo"] = run_checker_script("opencode_cost_benefit_analyzer.py")
    if status["ocgo"]:
        results["ocgo_live_json"] = DATA / "ocgo_live.json"
        if verbose:
            log("  Refreshed OpenCode Go pricing & cost/benefit -> ocgo_live.json")

    if verbose:
        log("  Refreshing CommandCode GOAT pricing & credits (cc_live.json)...")
    status["cc"] = run_checker_script("commandcode_cost_benefit_analyzer.py")
    if status["cc"]:
        results["cc_live_json"] = DATA / "cc_live.json"
        if verbose:
            log("  Refreshed CommandCode GOAT pricing & credits -> cc_live.json")

    if verbose:
        log("  Refreshing Free Model rankings (free_models.json)...")
    status["free"] = run_checker_script("free_model_ranker.py", ["--json", "--html"])
    if status["free"]:
        results["free_models_json"] = DATA / "free_models.json"
        if verbose:
            log("  Refreshed Free Model rankings -> free_models.json")

    if verbose:
        log("  Refreshing Stealth Model rankings (stealth_models.json)...")
    status["stealth"] = run_checker_script("stealth_model_detector.py", ["--json", "--html"])
    if status["stealth"]:
        results["stealth_models_json"] = DATA / "stealth_models.json"
        if verbose:
            log("  Refreshed Stealth Model rankings -> stealth_models.json")

    if verbose:
        log("  Refreshing Frontier Models tracking (frontier_models.json)...")
    status["frontier"] = run_checker_script("frontier_model_tracker.py", ["--json"])
    if status["frontier"]:
        results["frontier_models_json"] = DATA / "frontier_models.json"
        if verbose:
            log("  Refreshed Frontier Models tracking -> frontier_models.json")

    return status


def generate_akatsuki_radar_content(today_str: str) -> str:
    """Generate machine-structured Akatsuki note for Model-Benchmarks-Live.md."""
    bench_p = DATA / "benchmarks.json"
    bench_data = {}
    if bench_p.exists():
        try:
            bench_data = json.loads(bench_p.read_text(encoding="utf-8"))
        except Exception:
            pass
    models = bench_data.get("models", []) if isinstance(bench_data, dict) else []

    oc_p = DATA / "ocgo_live.json"
    oc_data = {}
    if oc_p.exists():
        try:
            oc_data = json.loads(oc_p.read_text(encoding="utf-8"))
        except Exception:
            pass
    oc_models = oc_data.get("models", []) if isinstance(oc_data, dict) else []

    cc_p = DATA / "cc_live.json"
    cc_data = {}
    if cc_p.exists():
        try:
            cc_data = json.loads(cc_p.read_text(encoding="utf-8"))
        except Exception:
            pass
    cc_models = cc_data.get("models", []) if isinstance(cc_data, dict) else []

    free_p = DATA / "free_models.json"
    free_data = {}
    if free_p.exists():
        try:
            free_data = json.loads(free_p.read_text(encoding="utf-8"))
        except Exception:
            pass
    free_models = free_data.get("models", []) if isinstance(free_data, dict) else []

    frontier_p = DATA / "frontier_models.json"
    frontier_data = {}
    if frontier_p.exists():
        try:
            frontier_data = json.loads(frontier_p.read_text(encoding="utf-8"))
        except Exception:
            pass
    frontier_provs = frontier_data.get("providers", {}) if isinstance(frontier_data, dict) else {}

    iso_now = dt.datetime.now(dt.timezone.utc).isoformat()
    lines = [
        "---",
        'title: "Live Model Benchmarks & Pricing Radar"',
        f'date: {today_str[:4]}-{today_str[4:6]}-{today_str[6:]}',
        "type: note",
        "tags:",
        "  - agents",
        "  - llm",
        "  - benchmarks",
        "  - pricing",
        "  - telemetry",
        'summary: "Automated live sync of LLM benchmark evaluations, OpenCode/CommandCode pricing limits, and free-tier rankings."',
        f'updated: {iso_now}',
        "updated_by: bsync-daemon",
        "---",
        "",
        "# ⚡ Live Model Benchmarks & Pricing Radar",
        "",
        "## 📌 Overview & Sync Telemetry",
        f"- **Last Updated**: `{iso_now}`",
        f"- **Evaluated Models Tracked**: {len(models)} models in universal catalog",
        "- **Standard Pricing Unit**: USD per 1M tokens ($/1M in / out / cache) by default",
        "- **Frontier Providers Tracked**: OpenAI, Anthropic (Claude), Google (Gemini) with per-token pricing ($/1M tokens)",
        "- **Upstream Feeds**: LiveBench, LMArena, Artificial Analysis, OpenRouter, OpenCode Go, CommandCode GOAT, Cline",
        "- **Local Engine**: `checkers/benchmark_sync_daemon.py` (`bsync --sync-now`)",
        "",
        "## 🏆 Top Frontier Models (Master Baseline)",
        "| Rank | Model | Pool | In / 1M | Out / 1M | Overall / LiveBench | AA Quality | Arena ELO |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    valid_models = [m for m in models if isinstance(m, dict) and (m.get("livebench", {}).get("overall") or m.get("aa_live_quality") or m.get("base_metrics", {}).get("lm_elo"))]
    valid_models.sort(
        key=lambda m: (
            m.get("composite_score", {}).get("score", 0) if isinstance(m.get("composite_score"), dict) else 0,
            m.get("livebench", {}).get("overall", 0) if isinstance(m.get("livebench"), dict) else 0,
            m.get("aa_live_quality", 0) or 0,
        ),
        reverse=True,
    )
    for i, m in enumerate(valid_models[:8], start=1):
        disp = m.get("display") or m.get("name") or "—"
        pool = m.get("pool") or "—"
        pin_val = m.get("price_in")
        pout_val = m.get("price_out")
        pin = f"${pin_val:.2f}" if isinstance(pin_val, (int, float)) else "—"
        pout = f"${pout_val:.2f}" if isinstance(pout_val, (int, float)) else "—"
        lb = f"{m.get('livebench', {}).get('overall'):.1f}" if isinstance(m.get("livebench"), dict) and m.get("livebench", {}).get("overall") else "—"
        aa = f"{m.get('aa_live_quality'):.1f}" if m.get("aa_live_quality") else "—"
        elo = f"{m.get('base_metrics', {}).get('lm_elo'):.0f}" if isinstance(m.get("base_metrics"), dict) and m.get("base_metrics", {}).get("lm_elo") else "—"
        badge = "🥇#1" if i == 1 else "🥈#2" if i == 2 else "🥉#3" if i == 3 else f"#{i}"
        lines.append(f"| {badge} | {disp} | {pool} | {pin} | {pout} | {lb} | {aa} | {elo} |")

    # Render dedicated sections for tracked frontier providers (Claude, OpenAI, Gemini)
    provider_sections = [
        ("claude", "🧠 Anthropic Claude Models (Benchmarks & Pricing)"),
        ("openai", "⚡ OpenAI Models (Benchmarks & Pricing)"),
        ("gemini", "💎 Google Gemini Models (Benchmarks & Pricing)"),
    ]
    for pkey, ptitle in provider_sections:
        pinfo = frontier_provs.get(pkey, {})
        pmodels = pinfo.get("models", [])
        if pmodels:
            lines.extend([
                "",
                f"## {ptitle}",
                "| Model | Input / 1M | Output / 1M | Cache / 1M | Context | LiveBench | AA Quality | Arena ELO |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for m in pmodels[:8]:
                name = m.get("display") or m.get("model_id") or "—"
                pr = m.get("pricing", {})
                bm = m.get("benchmarks", {})
                pin = f"${pr.get('price_in_1m'):.2f}" if pr.get("price_in_1m") is not None else "—"
                pout = f"${pr.get('price_out_1m'):.2f}" if pr.get("price_out_1m") is not None else "—"
                pcache = f"${pr.get('price_cache_1m'):.2f}" if pr.get("price_cache_1m") is not None else "—"
                ctx_val = pr.get("context_length")
                ctx = f"{ctx_val//1000}k" if ctx_val else "—"
                lb = f"{bm.get('livebench_overall'):.1f}" if bm.get('livebench_overall') is not None else "—"
                aa = f"{bm.get('aa_quality'):.1f}" if bm.get('aa_quality') is not None else "—"
                elo = f"{bm.get('arena_elo'):.0f}" if bm.get('arena_elo') is not None else "—"
                lines.append(f"| {name} | {pin} | {pout} | {pcache} | {ctx} | {lb} | {aa} | {elo} |")

    lines.extend([
        "",
        "## 💰 OpenCode Go Pricing & Value Radar",
        "- **Standard Unit**: `$/1M tokens` · **Account Caps**: `$12/5h` · `$30/wk` · `$60/mo` pooled",
        "",
        "| Rank | Model | In / 1M | Out / 1M | Limit | Req/Mo | Q(Cap) | Eff c/r | Value Score |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for i, m in enumerate(oc_models[:6], start=1):
        badge = "🥇#1" if i == 1 else "🥈#2" if i == 2 else "🥉#3" if i == 3 else f"#{i}"
        name = m.get("display") or m.get("name") or m.get("model_id") or "—"
        pr = m.get("pricing") if isinstance(m.get("pricing"), dict) else {}
        pin_val = pr.get("input_per_1m")
        pout_val = pr.get("output_per_1m")
        pin = f"${pin_val:.2f}" if isinstance(pin_val, (int, float)) else "—"
        pout = f"${pout_val:.2f}" if isinstance(pout_val, (int, float)) else "—"

        cap_val = None
        if isinstance(m.get("caps"), dict):
            cap_val = m.get("caps", {}).get("cap_mo_usd")
        if cap_val is None and isinstance(m.get("pricing"), dict):
            cap_val = m.get("pricing", {}).get("monthly_usage_limit_usd")
        if cap_val is None:
            cap_val = m.get("limit")
        limit = f"${cap_val:.0f}/m" if isinstance(cap_val, (int, float)) else (f"${cap_val}/m" if cap_val is not None else "—")

        req_val = None
        if isinstance(m.get("value"), dict):
            req_val = m.get("value", {}).get("effective_requests_per_month")
        if req_val is None and isinstance(m.get("requests"), dict):
            req_val = m.get("requests", {}).get("requests_per_month")
        if req_val is None:
            req_val = m.get("req_mo_eff") or m.get("req_mo")
        reqs = f"{req_val:,.0f}" if req_val is not None else "—"

        bm = m.get("benchmarks") if isinstance(m.get("benchmarks"), dict) else {}
        qcap_val = bm.get("capability_q") if bm.get("capability_q") is not None else (bm.get("q_capability") or m.get("q_cap"))
        qcap = f"{qcap_val:.1f}" if qcap_val is not None else "—"

        eff_c_val = None
        if isinstance(m.get("value"), dict):
            eff_c_val = m.get("value", {}).get("effective_cost_per_request")
        if eff_c_val is None:
            eff_c_val = m.get("cost_per_request_usd") or m.get("cost_per_req")
        eff_c = f"${eff_c_val:.4f}" if eff_c_val is not None else "—"

        val_score = None
        if isinstance(m.get("value"), dict):
            val_score = m.get("value", {}).get("value_score") or m.get("value", {}).get("qvi_score")
        elif isinstance(m.get("value"), (int, float)):
            val_score = m.get("value")
        elif m.get("value_score") is not None:
            val_score = m.get("value_score")
        val = f"{val_score:.1f}" if val_score is not None else "—"
        lines.append(f"| {badge} | {name} | {pin} | {pout} | {limit} | {reqs} | {qcap} | {eff_c} | {val} |")

    lines.extend([
        "",
        "## ⚡ CommandCode GOAT Quota & Value Radar",
        "- **Standard Unit**: `$/1M tokens` · **Account Caps**: `$14/5h` · `$35/wk` · `$70/mo` · Credits `$20`–`$70`",
        "",
        "| Rank | Model | In / 1M | Out / 1M | Credits | Req/Mo | Q(Cap) | Eff c/r | Value Score |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for i, m in enumerate(cc_models[:6], start=1):
        badge = "🥇#1" if i == 1 else "🥈#2" if i == 2 else "🥉#3" if i == 3 else f"#{i}"
        name = m.get("display") or m.get("name") or m.get("model_id") or "—"
        pr = m.get("pricing") if isinstance(m.get("pricing"), dict) else {}
        pin_val = pr.get("input_per_1m")
        pout_val = pr.get("output_per_1m")
        pin = f"${pin_val:.2f}" if isinstance(pin_val, (int, float)) else "—"
        pout = f"${pout_val:.2f}" if isinstance(pout_val, (int, float)) else "—"

        cred_val = None
        if isinstance(m.get("pricing"), dict):
            cred_val = m.get("pricing", {}).get("monthly_credits")
        if cred_val is None and isinstance(m.get("caps"), dict):
            cred_val = m.get("caps", {}).get("cap_mo_usd")
        if cred_val is None:
            cred_val = m.get("credits")
        credits = f"${cred_val:.0f}" if isinstance(cred_val, (int, float)) else (f"${cred_val}" if cred_val is not None else ("Free" if m.get("is_free") else "—"))

        req_val = None
        if isinstance(m.get("value"), dict):
            req_val = m.get("value", {}).get("effective_requests_per_month")
        if req_val is None and isinstance(m.get("requests"), dict):
            req_val = m.get("requests", {}).get("requests_per_month")
        if req_val is None:
            req_val = m.get("req_mo_eff") or m.get("req_mo")
        reqs = f"{req_val:,.0f}" if req_val is not None else "—"

        bm = m.get("benchmarks") if isinstance(m.get("benchmarks"), dict) else {}
        qcap_val = bm.get("capability_q") if bm.get("capability_q") is not None else (bm.get("q_capability") or m.get("q_cap"))
        qcap = f"{qcap_val:.1f}" if qcap_val is not None else "—"

        eff_c_val = None
        if isinstance(m.get("value"), dict):
            eff_c_val = m.get("value", {}).get("effective_cost_per_request")
        if eff_c_val is None:
            eff_c_val = m.get("cost_per_request_usd") or m.get("cost_per_req")
        eff_c = f"${eff_c_val:.4f}" if eff_c_val is not None else "—"

        val_score = None
        if isinstance(m.get("value"), dict):
            val_score = m.get("value", {}).get("value_score") or m.get("value", {}).get("qvi_score")
        elif isinstance(m.get("value"), (int, float)):
            val_score = m.get("value")
        elif m.get("value_score") is not None:
            val_score = m.get("value_score")
        val = f"{val_score:.1f}" if val_score is not None else "—"
        lines.append(f"| {badge} | {name} | {pin} | {pout} | {credits} | {reqs} | {qcap} | {eff_c} | {val} |")

    lines.extend([
        "",
        "## 🎁 Free Tier Champions",
        "| Rank | Model | Provider | Q(Cap) | P(Succ) | FGI | Context |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for i, m in enumerate(free_models[:6], start=1):
        badge = "🥇#1" if i == 1 else "🥈#2" if i == 2 else "🥉#3" if i == 3 else f"#{i}"
        name = m.get("display") or m.get("model_id") or m.get("name") or "—"
        prov = m.get("provider") or "opencode"
        bm = m.get("benchmarks") if isinstance(m.get("benchmarks"), dict) else {}
        qcap_val = bm.get("capability_q") if bm.get("capability_q") is not None else m.get("q_cap")
        qcap = f"{qcap_val:.1f}" if qcap_val is not None else "—"
        psucc_val = bm.get("p_success") if bm.get("p_success") is not None else m.get("p_success")
        if psucc_val is not None:
            psucc = f"{psucc_val:.1f}%" if psucc_val > 1 else f"{psucc_val*100:.1f}%"
        else:
            psucc = "—"
        fgi_val = bm.get("fgi_score") if bm.get("fgi_score") is not None else m.get("fgi")
        fgi = f"{fgi_val:.1f}" if fgi_val is not None else "—"
        ctx_val = bm.get("openrouter_context") or m.get("context_length")
        ctx = f"{ctx_val//1000}k" if ctx_val else "—"
        lines.append(f"| {badge} | {name} | {prov} | {qcap} | {psucc} | {fgi} | {ctx} |")

    lines.extend([
        "",
        "## 🔗 Related",
        "- [[30-Agents/Agents-MOC|Agents MOC]]",
        "- [[20-Projects/llm-benchyyyy|llm-benchyyyy]]",
        "- [[30-Agents/Model-Benchmarks-2026|Model Benchmarks 2026]]",
        "- [[30-Agents/Provider-Quota-Telemetry-Spec|Provider Quota Telemetry Spec]]",
        "",
    ])
    return "\n".join(lines)


def _normalize_radar_content_for_diff(text: str) -> str:
    """Extract and normalize markdown body (ignoring frontmatter and Last Updated) to detect real table changes."""
    body_idx = text.find("# ⚡ Live Model Benchmarks")
    if body_idx != -1:
        text = text[body_idx:]
    lines = []
    for line in text.splitlines():
        line_s = line.strip()
        if line_s.startswith("- **Last Updated**:") or not line_s:
            continue
        lines.append(line_s)
    return "\n".join(lines)


def save_results_to_akatsuki(verbose: bool = True) -> bool:
    """Save synthesized benchmark and pricing radar to Akatsuki vault and log telemetry."""
    vault = find_akatsuki_vault()
    if not vault:
        if verbose:
            log("  Akatsuki vault not found — skipping Akatsuki persistence")
        return False

    today_str = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    content = generate_akatsuki_radar_content(today_str)
    note_rel = "30-Agents/Model-Benchmarks-Live.md"
    note_file = vault / note_rel

    # Deduplication & Anti-Bloat: skip write and telemetry if underlying data is unchanged
    if note_file.exists():
        try:
            existing_text = note_file.read_text(encoding="utf-8")
            if _normalize_radar_content_for_diff(existing_text) == _normalize_radar_content_for_diff(content):
                if verbose:
                    log("  Akatsuki note content unchanged — skipping rewrite and telemetry to prevent bloat")
                return True
        except Exception:
            pass

    is_custom_vault = os.getenv("AKATSUKI_VAULT") is not None
    akatsuki_bin = None if is_custom_vault else (shutil.which("akatsuki") or (pathlib.Path.home() / ".local" / "bin" / "akatsuki"))
    saved = False

    if akatsuki_bin and pathlib.Path(akatsuki_bin).exists():
        try:
            proc = subprocess.run(
                [str(akatsuki_bin), "write", note_rel, "--overwrite"],
                input=content,
                text=True,
                capture_output=True,
                timeout=15,
            )
            if proc.returncode == 0:
                saved = True
                if verbose:
                    log(f"  Saved Akatsuki note via CLI -> {note_rel}")
            else:
                log(f"  WARN: akatsuki write returned {proc.returncode}: {proc.stderr.strip()[:100]}")
        except Exception as e:
            log(f"  WARN: Failed to execute akatsuki write: {e}")

    if not saved:
        try:
            note_file.parent.mkdir(parents=True, exist_ok=True)
            bc.atomic_write_text(note_file, content)
            saved = True
            if verbose:
                log(f"  Saved Akatsuki note directly -> {note_file}")
        except Exception as e:
            log(f"  WARN: Failed to write note directly: {e}")
            return False

    # Ensure link exists in 30-Agents/Agents-MOC.md
    moc_file = vault / "30-Agents" / "Agents-MOC.md"
    if moc_file.exists():
        try:
            moc_text = moc_file.read_text(encoding="utf-8")
            target_link = "[[30-Agents/Model-Benchmarks-Live|Live Model Benchmarks & Pricing Radar]]"
            if target_link not in moc_text:
                heading = "## 🔬 Model Benchmarking & Empirical Evaluations"
                if heading in moc_text:
                    replacement = f"{heading}\n\n- {target_link}: Automated daily sync of benchmark evaluations, OpenCode/CommandCode pricing, and free-tier rankings."
                    moc_text = moc_text.replace(heading, replacement, 1)
                    bc.atomic_write_text(moc_file, moc_text)
                    if verbose:
                        log("  Linked note in Agents-MOC.md")
        except Exception as e:
            log(f"  WARN: Failed to link in Agents-MOC: {e}")

    # Ensure link exists in 20-Projects/llm-benchyyyy.md
    proj_file = vault / "20-Projects" / "llm-benchyyyy.md"
    if proj_file.exists():
        try:
            proj_text = proj_file.read_text(encoding="utf-8")
            target_link = "[[30-Agents/Model-Benchmarks-Live|Live Model Benchmarks & Pricing Radar]]"
            if target_link not in proj_text:
                heading = "## 🔗 Related"
                if heading in proj_text:
                    replacement = f"{heading}\n- {target_link}"
                    proj_text = proj_text.replace(heading, replacement, 1)
                    bc.atomic_write_text(proj_file, proj_text)
                    if verbose:
                        log("  Linked note in 20-Projects/llm-benchyyyy.md")
        except Exception as e:
            log(f"  WARN: Failed to link in llm-benchyyyy: {e}")

    # Ensure link exists in 30-Agents/Model-Benchmarks-2026.md
    bm_2026_file = vault / "30-Agents" / "Model-Benchmarks-2026.md"
    if bm_2026_file.exists():
        try:
            bm_text = bm_2026_file.read_text(encoding="utf-8")
            target_link = "[[30-Agents/Model-Benchmarks-Live|Live Model Benchmarks & Pricing Radar]]"
            if target_link not in bm_text:
                heading = "## 🔗 Related"
                if heading in bm_text:
                    replacement = f"{heading}\n- {target_link}"
                    bm_text = bm_text.replace(heading, replacement, 1)
                    bc.atomic_write_text(bm_2026_file, bm_text)
                    if verbose:
                        log("  Linked note in 30-Agents/Model-Benchmarks-2026.md")
        except Exception as e:
            log(f"  WARN: Failed to link in Model-Benchmarks-2026: {e}")

    # Deposit work log telemetry
    if akatsuki_bin and pathlib.Path(akatsuki_bin).exists():
        try:
            summary = "sync upstream -> refreshed benchmarks, frontier (openai/claude/gemini) & ocgo/ccgo prices; saved to akatsuki"
            proc = subprocess.run(
                [str(akatsuki_bin), "log", "--project", "llm-benchyyyy", "--summary", summary],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                if verbose:
                    log("  Deposited Akatsuki work log telemetry")
            else:
                log(f"  WARN: akatsuki log exit {proc.returncode}: {proc.stderr.strip()[:100]}")
        except Exception as e:
            log(f"  WARN: Failed to deposit akatsuki log: {e}")

    return saved


def sync_all_sources(verbose: bool = True, force: bool = False) -> dict[str, pathlib.Path | None]:
    """Fetch all upstream benchmark feeds, refresh all result/pricing databases, and save to Akatsuki."""
    RAW.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    results = {}

    log("=== Starting Upstream Benchmark Synchronization ===")

    # 1. Fetch each feed via the guarded helper: failure KEEPs cache, never writes it.
    results["livebench_csv"] = _fetch_and_save("LiveBench CSV", LIVEBENCH_CSV, RAW / f"livebench_{today}.csv", MIN_SNAPSHOT_BYTES["livebench_csv"], force, verbose)
    results["livebench_categories"] = _fetch_and_save("LiveBench Categories", LIVEBENCH_CAT, RAW / f"livebench_categories_{today}.json", MIN_SNAPSHOT_BYTES["livebench_categories"], force, verbose)
    results["lmarena"] = _fetch_and_save("LMArena HTML", LMARENA_URL, RAW / f"lmarena_{today}.html", MIN_SNAPSHOT_BYTES["lmarena"], force, verbose)
    results["artificial_analysis"] = _fetch_and_save("Artificial Analysis HTML", AA_URL, RAW / f"artificial_analysis_{today}.html", MIN_SNAPSHOT_BYTES["artificial_analysis"], force, verbose)
    results["openrouter"] = _fetch_and_save("OpenRouter JSON", OPENROUTER_API, RAW / f"openrouter_models_{today}.json", MIN_SNAPSHOT_BYTES["openrouter"], force, verbose)
    results["commandcode_goat"] = _fetch_and_save("CommandCode GOAT HTML", CC_GOAT_DOCS, RAW / f"cc_goat_docs_{today}.html", MIN_SNAPSHOT_BYTES["commandcode_goat"], force, verbose)
    results["cline_models"] = _fetch_and_save("Cline Models JSON", CLINE_MODELS_URL, RAW / f"cline_models_{today}.json", MIN_SNAPSHOT_BYTES["cline_models"], force, verbose)
    results["opencode_go_docs"] = _fetch_and_save("OpenCode Go Docs HTML", OCGO_DOCS, RAW / f"opencode_go_docs_{today}.html", MIN_SNAPSHOT_BYTES["opencode_go_docs"], force, verbose)
    results["opencode_go_models"] = _fetch_and_save("OpenCode Go Models JSON", OCGO_API, RAW / f"opencode_go_models_{today}.json", MIN_SNAPSHOT_BYTES["opencode_go_models"], force, verbose)
    results["opencode_zen_models"] = _fetch_and_save("OpenCode Zen Models JSON", OPENCODE_ZEN_API, RAW / f"opencode_zen_models_{today}.json", MIN_SNAPSHOT_BYTES["opencode_zen_models"], force, verbose)
    missing = sorted(k for k, v in results.items() if v is None)
    if missing:
        log(f"  WARN {len(missing)} feed(s) missing with no usable cache: {', '.join(missing)}")

    # 2. Trigger Suite Baseline Refresh (refuse to persist a collapsed catalog).
    baseline_ok = False
    try:
        import llm_benchmark_aggregator as lba
        live_map = lba.load_livebench_data(fetch=False)
        lm_map = lba.load_lmarena_data(fetch=False)
        aa_map = lba.load_aa_data(fetch=False)
        cat = lba.build_universal_catalog(live_map=live_map, lm_map=lm_map, aa_map=aa_map)
        lba.calculate_composite_scores(cat)
        models = [m for m in cat.values() if m.get("livebench") or m.get("aa_live_quality") or m.get("base_metrics", {}).get("lm_elo")]
        prev_snap = lba.load_previous_snapshot(DATA / "benchmarks.json")
        if not models:
            log("  REFUSE baseline rewrite: 0 evaluated models — keeping benchmarks.json")
        else:
            collapsed, prev_n = _baseline_collapsed(models, prev_snap)
            if collapsed:
                log(f"  REFUSE baseline rewrite: {len(models)} evaluated vs {prev_n} prev — keeping benchmarks.json")
            else:
                diff = lba.diff_model_catalog(models, prev_snap, id_key="display")
                models = diff["rows"]
                base_p = lba.save_baseline(models, diff)
                results["baseline_json"] = base_p
                baseline_ok = True
                log(f"  Refreshed Master Baseline -> {base_p.name} ({len(models)} evaluated models)")
    except Exception as e:
        log(f"  WARN: Failed to refresh master baseline: {e}")

    # 3. Refresh downstream cost-benefit, pricing, and free/stealth model checkers.
    refresh_suite_results(results, verbose=verbose)

    # 4. Save synthesized benchmarks & prices to Akatsuki.
    akatsuki_saved = save_results_to_akatsuki(verbose=verbose)
    results["akatsuki_saved"] = akatsuki_saved

    kept = sum(1 for v in results.values() if v is not None and v is not False)
    log(f"=== Sync Completed: {kept} items updated/verified (baseline: {'ok' if baseline_ok else 'kept'}, akatsuki: {'saved' if akatsuki_saved else 'skipped'}) ===")
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
        ("OpenCode Go Docs", f"opencode_go_docs_{today}.html", "opencode_go_docs_*.html"),
        ("OpenCode Go Models", f"opencode_go_models_{today}.json", "opencode_go_models_*.json"),
        ("OpenCode Zen Models", f"opencode_zen_models_{today}.json", "opencode_zen_models_*.json"),
        ("Master Baseline", "benchmarks.json", "benchmarks.json"),
        ("OpenCode Go Live", "ocgo_live.json", "ocgo_live.json"),
        ("CommandCode Live", "cc_live.json", "cc_live.json"),
        ("Free Models", "free_models.json", "free_models.json"),
        ("Stealth Models", "stealth_models.json", "stealth_models.json"),
        ("Frontier Models (OpenAI/Claude/Gemini)", "frontier_models.json", "frontier_models.json"),
    ]

    status_report = []
    for name, today_name, glob_pat in feeds:
        if name in ("Master Baseline", "OpenCode Go Live", "CommandCode Live", "Free Models", "Stealth Models", "Frontier Models (OpenAI/Claude/Gemini)"):
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

    vault = find_akatsuki_vault()
    akatsuki_status = "Vault not found"
    if vault:
        ak_file = vault / "30-Agents" / "Model-Benchmarks-Live.md"
        if ak_file.exists():
            ak_mtime = dt.datetime.fromtimestamp(ak_file.stat().st_mtime)
            akatsuki_status = f"Saved (30-Agents/Model-Benchmarks-Live.md, {ak_mtime.strftime('%Y-%m-%d %H:%M:%S')})"
        else:
            akatsuki_status = "Vault located (note not yet created)"

    sec_next = seconds_until_next_target_time(8, 0)
    next_dt = dt.datetime.now() + dt.timedelta(seconds=sec_next)

    return {
        "status_report": status_report,
        "akatsuki_status": akatsuki_status,
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
    print(f" Akatsuki Note:   {st['akatsuki_status']}")
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
