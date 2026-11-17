#!/usr/bin/env python3
"""
benchmark_sync_daemon.py — 08:00 Daily Benchmark Sync Daemon & Local Cache Engine

Automatically pulls all upstream benchmark & catalog feeds into docs/data/raw/,
refreshes master/downstream JSON & HTML reports, and syncs the Akatsuki radar note.
All suite tools (bcheck, ccheck, fcheck, scheck, ocheck, fntcheck) read offline by default.
"""
import argparse
import contextlib
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
import urllib.error
import urllib.request
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

ROOT = HERE.parent
for _p in (HERE.parent, HERE.parent.parent, HERE.parent.parent.parent):
    if (_p / "setup.sh").exists() or (_p / ".git").exists():
        ROOT = _p
        break

import benchmark_common as bc  # noqa: E402

DATA = ROOT / "docs" / "data"
RAW = DATA / "raw"
LOGS = DATA / "sync_daemon.log"
LOCK_PATH = DATA / "sync_daemon.lock"

# Upstream Source Endpoints
LIVEBENCH_CSV = "https://livebench.ai/v1/table_2026_06_25.csv"
LIVEBENCH_CAT = "https://livebench.ai/v1/categories_2026_06_25.json"
AA_URL = bc.AA_URL
OPENROUTER_API = bc.OPENROUTER_API
CC_GOAT_DOCS = "https://commandcode.ai/docs/plans/goat"
CLINE_MODELS_URL = bc.CLINE_RECOMMENDED_MODELS_API
OCGO_DOCS = bc.OCGO_DOCS
OCGO_API = bc.OPENCODE_GO_API
OPENCODE_ZEN_API = bc.OPENCODE_ZEN_API
VALS_INDEX_URL = bc.VALS_INDEX_URL
FRONTIERCODE_URL = bc.FRONTIERCODE_URL
FRONTIERSWE_URL = bc.FRONTIERSWE_URL
UA = bc.UA

MIN_SNAPSHOT_BYTES = {
    "livebench_csv": 2000,
    "livebench_categories": 200,
    "artificial_analysis": 500_000,
    "openrouter": 100_000,
    "commandcode_goat": 50_000,
    "cline_models": 1000,
    "opencode_go_docs": 30_000,
    "opencode_go_models": 1000,
    "opencode_zen_models": 2000,
    "vals_index": 100_000,
    "frontiercode": 10_000,
    "frontierswe": 20_000,
}

_MIN_PARSED_ROWS = {
    "artificial_analysis": (bc.parse_aa, 50),
    "vals_index": (bc.parse_vals_index, 20),
    "frontiercode": (bc.parse_frontiercode, 20),
    "frontierswe": (bc.parse_frontierswe, 15),
}

_FEED_SPECS = (
    ("livebench_csv", "LiveBench CSV", LIVEBENCH_CSV, "livebench_{today}.csv"),
    ("livebench_categories", "LiveBench Categories", LIVEBENCH_CAT, "livebench_categories_{today}.json"),
    ("artificial_analysis", "Artificial Analysis HTML", AA_URL, "artificial_analysis_{today}.html"),
    ("openrouter", "OpenRouter JSON", OPENROUTER_API, "openrouter_models_{today}.json"),
    ("commandcode_goat", "CommandCode GOAT HTML", CC_GOAT_DOCS, "cc_goat_docs_{today}.html"),
    ("cline_models", "Cline Models JSON", CLINE_MODELS_URL, "cline_models_{today}.json"),
    ("opencode_go_docs", "OpenCode Go Docs HTML", OCGO_DOCS, "opencode_go_docs_{today}.html"),
    ("opencode_go_models", "OpenCode Go Models JSON", OCGO_API, "opencode_go_models_{today}.json"),
    ("opencode_zen_models", "OpenCode Zen Models JSON", OPENCODE_ZEN_API, "opencode_zen_models_{today}.json"),
    ("vals_index", "Vals Index HTML", VALS_INDEX_URL, "vals_index_{today}.html"),
    ("frontiercode", "FrontierCode 2.0 JSON", FRONTIERCODE_URL, "frontiercode_{today}.json"),
    ("frontierswe", "FrontierSWE HTML", FRONTIERSWE_URL, "frontierswe_{today}.html"),
)

_DATED_SNAP_RE = re.compile(r"^(.+)_(\d{8})\.[^.]+$")
_PROTECTED_RAW = frozenset({"livebench_20260625.csv", "livebench_categories_20260625.json"})
_RADAR_TARGET_LINK = "[[30-Agents/Model-Benchmarks-Live|Live Model Benchmarks & Pricing Radar]]"
_MEDAL_BADGES = {1: "🥇#1", 2: "🥈#2", 3: "🥉#3"}
_FETCH_ERRORS = (
    urllib.error.URLError,
    urllib.error.HTTPError,
    TimeoutError,
    OSError,
    ValueError,
    http.client.HTTPException,
)


def log(msg: str):
    """Write timestamped log to stderr and LOGS file."""
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, file=sys.stderr)
    with contextlib.suppress(OSError):
        LOGS.parent.mkdir(parents=True, exist_ok=True)
        with open(LOGS, "a", encoding="utf-8") as f:
            f.write(line + "\n")


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
        except _FETCH_ERRORS as e:
            if attempt < max_retries:
                time.sleep(1.5 ** attempt)
                continue
            log(f"  WARN: Failed to fetch {url} after {max_retries} attempts: {e}")
            return None
    return None


def _payload_valid(feed_key: str, txt: str, min_bytes: int) -> bool:
    if len(txt) < min_bytes:
        return False
    check = _MIN_PARSED_ROWS.get(feed_key)
    if check is None:
        return True
    parser, min_rows = check
    try:
        return len(parser(txt)) >= min_rows
    except Exception:
        return False


def _fetch_and_save(
    name: str,
    url: str,
    path: pathlib.Path,
    min_bytes: int,
    force: bool,
    verbose: bool = True,
    feed_key: str = "",
) -> pathlib.Path | None:
    """Fetch url and save dated snapshot without overwriting valid cache on failure."""
    if path.exists() and not force:
        if verbose:
            log(f"  {name} cached -> {path.name}")
        return path
    txt = fetch_url_content(url)
    if txt and _payload_valid(feed_key, txt, min_bytes):
        bc.atomic_write_text(path, txt)
        log(f"  Saved {name} -> {path.name} ({len(txt):,} bytes)")
        return path
    if path.exists():
        have = path.stat().st_size
        log(f"  KEEP {name} -> {path.name} ({have:,} bytes, fetch failed — keeping cache)")
        return path
    got = len(txt) if txt else 0
    log(f"  MISSING {name} (no cache, fetch/parse failed — got {got} bytes, need {min_bytes:,})")
    return None


def _unlink_old_snapshot(old: pathlib.Path, verbose: bool) -> int:
    try:
        old.unlink()
        if verbose:
            log(f"  pruned old snapshot: {old.name}")
        return 1
    except OSError as e:
        if verbose:
            log(f"  WARN prune {old.name}: {e}")
        return 0


def prune_raw_snapshots(raw_dir: pathlib.Path = RAW, keep_days: int = 3, verbose: bool = True) -> int:
    """Retain the latest keep_days dated snapshots per feed family plus protected baselines."""
    if not raw_dir.exists():
        return 0
    groups: dict[str, list[pathlib.Path]] = defaultdict(list)
    for f in raw_dir.iterdir():
        if not f.is_file() or f.name in _PROTECTED_RAW:
            continue
        m = _DATED_SNAP_RE.match(f.name)
        if m:
            groups[m.group(1)].append(f)

    pruned = 0
    for flist in groups.values():
        flist.sort(key=lambda p: p.name)
        for old in flist[:-keep_days]:
            pruned += _unlink_old_snapshot(old, verbose)
    return pruned


def _baseline_collapsed(models: list, prev_snapshot) -> tuple[bool, int]:
    """True when saving would wipe history (>50% drop from previous non-empty snapshot)."""
    prev_models = prev_snapshot.get("models") if hasattr(prev_snapshot, "get") else prev_snapshot
    prev_n = len(prev_models) if isinstance(prev_models, list) else 0
    if prev_n <= 0:
        return False, 0
    threshold = max(1, int(prev_n * 0.5))
    return len(models) < threshold, prev_n


@contextlib.contextmanager
def sync_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise RuntimeError("benchmark sync is already running") from e
        lock_file.seek(0)
        lock_file.truncate()
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
    return default_p if default_p.is_dir() else None


def run_checker_script(script_name: str, args: list[str] | None = None) -> bool:
    """Execute an analysis checker script in a subprocess to refresh its data/reports."""
    script_path = HERE / script_name
    if not script_path.exists():
        log(f"  WARN: checker script {script_name} not found")
        return False
    cmd = [sys.executable, str(script_path), *(args or [])]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=90)
        if proc.returncode == 0:
            return True
        log(f"  WARN: {script_name} returned exit {proc.returncode}: {proc.stderr.strip()[:200]}")
        return False
    except (OSError, subprocess.SubprocessError) as e:
        log(f"  WARN: Failed to execute {script_name}: {e}")
        return False


_CHECKER_STEPS = (
    ("ocgo", "opencode_cost_benefit_analyzer.py", [], [("ocgo_live_json", DATA / "ocgo_live.json")], "OpenCode Go pricing & cost/benefit"),
    ("cc", "commandcode_cost_benefit_analyzer.py", [], [("cc_live_json", DATA / "cc_live.json")], "CommandCode GOAT pricing & credits"),
    ("free", "free_model_ranker.py", ["--json", "--html"], [("free_models_json", DATA / "free_models.json")], "Free Model rankings"),
    ("stealth", "stealth_model_detector.py", ["--json", "--html"], [("stealth_models_json", DATA / "stealth_models.json")], "Stealth Model rankings"),
    ("frontier", "frontier_model_tracker.py", ["--json"], [("frontier_models_json", DATA / "frontier_models.json")], "Frontier Models tracking"),
    (
        "reports",
        "llm_benchmark_aggregator.py",
        ["--md", "docs/reports/benchmarks.md", "--html", "docs/reports/benchmarks.html"],
        [
            ("benchmarks_md", ROOT / "docs" / "reports" / "benchmarks.md"),
            ("benchmarks_html", ROOT / "docs" / "reports" / "benchmarks.html"),
        ],
        "published benchmark tables",
    ),
)


def refresh_suite_results(results: dict, verbose: bool = True) -> dict[str, bool]:
    """Run all downstream analysis checkers to refresh prices, limits, and ranking databases."""
    status: dict[str, bool] = {}
    for key, script, args, outputs, label in _CHECKER_STEPS:
        if verbose:
            log(f"  Refreshing {label}...")
        ok = run_checker_script(script, args)
        status[key] = ok
        if not ok:
            continue
        for res_key, path in outputs:
            results[res_key] = path
        if verbose:
            log(f"  Refreshed {label} -> {outputs[0][1].name}")
    return status


def _load_json_dict(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _dict_or_empty(val) -> dict:
    return val if isinstance(val, dict) else {}


def _first_num(*candidates) -> float | None:
    for val in candidates:
        num = bc._safe_float(val)
        if num is not None:
            return num
    return None


def _fmt_num(val, fmt: str, prefix: str = "", suffix: str = "") -> str:
    num = bc._safe_float(val)
    return f"{prefix}{num:{fmt}}{suffix}" if num is not None else "—"


def _model_comp_score(m: dict) -> float:
    raw = m.get("composite_score")
    if isinstance(raw, dict):
        raw = raw.get("score")
    return _first_num(raw, m.get("capability_q")) or 0.0


def _badge(rank: int) -> str:
    return _MEDAL_BADGES.get(rank, f"#{rank}")


def _frontier_master_row(rank: int, m: dict) -> str:
    roles = _dict_or_empty(m.get("roles"))
    bm = _dict_or_empty(m.get("base_metrics"))
    disp = m.get("display") or m.get("name") or "—"
    pool = m.get("pool") or "—"
    q_s = _fmt_num(_model_comp_score(m), ".1f")
    arch_s = _fmt_num(roles.get("architecture"), ".1f")
    dev_s = _fmt_num(roles.get("software_dev"), ".1f")
    cur_s = _fmt_num(_first_num(bm.get("cursor_score"), _dict_or_empty(m.get("cursor_evals")).get("score")), ".1f", suffix="%")
    fc2_s = _fmt_num(_first_num(bm.get("fc2_score"), _dict_or_empty(m.get("frontiercode")).get("score")), ".1f", suffix="%")
    cost_s = _fmt_num(_first_num(m.get("empirical_cost"), m.get("effective_cost")), ".2f", "$")
    return f"| {_badge(rank)} | {disp} | {pool} | {q_s} | {arch_s} | {dev_s} | {cur_s} | {fc2_s} | {cost_s} |"


def _frontier_master_sort_key(m: dict) -> tuple[float, float, float, float]:
    roles = _dict_or_empty(m.get("roles"))
    bm = _dict_or_empty(m.get("base_metrics"))
    cur_val = _first_num(bm.get("cursor_score"), _dict_or_empty(m.get("cursor_evals")).get("score"))
    fc2_val = _first_num(bm.get("fc2_score"), _dict_or_empty(m.get("frontiercode")).get("score"))
    return (_model_comp_score(m), _first_num(roles.get("architecture")) or 0.0, cur_val or 0.0, fc2_val or 0.0)


def _is_valid_master_model(m) -> bool:
    if not isinstance(m, dict) or m.get("unmatched"):
        return False
    lb = _dict_or_empty(m.get("livebench"))
    bm = _dict_or_empty(m.get("base_metrics"))
    vm = _dict_or_empty(m.get("vals_metrics"))
    return _first_num(
        m.get("composite_score"), lb.get("overall"), m.get("aa_live_quality"), bm.get("lm_elo"),
        vm.get("vals_overall"), bm.get("fc2_score"), bm.get("fswe_overall"), bm.get("cursor_score"),
    ) is not None


def _frontier_master_lines(models: list[dict]) -> list[str]:
    valid = sorted((m for m in models if _is_valid_master_model(m)), key=_frontier_master_sort_key, reverse=True)
    out = [
        "## 🏆 Top Frontier Models (Master Baseline)",
        "| Rank | Model | Pool | Q | Arch | Dev | Cursor% | FC2% | $/Task |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    out.extend(_frontier_master_row(i, m) for i, m in enumerate(valid[:8], start=1))
    return out


_FRONTIER_PROVIDERS = (
    ("claude", "🧠 Anthropic Claude Models (Benchmarks & Pricing)"),
    ("openai", "⚡ OpenAI Models (Benchmarks & Pricing)"),
    ("gemini", "💎 Google Gemini Models (Benchmarks & Pricing)"),
)


def _provider_section_lines(frontier_provs: dict) -> list[str]:
    out: list[str] = []
    for pkey, ptitle in _FRONTIER_PROVIDERS:
        pmodels = _dict_or_empty(frontier_provs.get(pkey)).get("models") or []
        if not pmodels:
            continue
        out.extend([
            "",
            f"## {ptitle}",
            "| Model | Input / 1M | Output / 1M | Cache / 1M | Context | LiveBench | AA Quality | Arena ELO |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])
        for m in pmodels[:8]:
            pr = _dict_or_empty(m.get("pricing"))
            bm = _dict_or_empty(m.get("benchmarks"))
            ctx_val = bc._safe_int(pr.get("context_length"))
            ctx = f"{ctx_val // 1000}k" if ctx_val else "—"
            out.append(
                f"| {m.get('display') or m.get('model_id') or '—'} "
                f"| {_fmt_num(pr.get('price_in_1m'), '.2f', '$')} "
                f"| {_fmt_num(pr.get('price_out_1m'), '.2f', '$')} "
                f"| {_fmt_num(pr.get('price_cache_1m'), '.2f', '$')} "
                f"| {ctx} "
                f"| {_fmt_num(bm.get('livebench_overall'), '.1f')} "
                f"| {_fmt_num(bm.get('aa_quality'), '.1f')} "
                f"| {_fmt_num(bm.get('arena_elo'), '.0f')} |"
            )
    return out


def _cost_radar_row(rank: int, m: dict, is_cc: bool) -> str:
    name = m.get("display") or m.get("name") or m.get("model_id") or "—"
    pr = _dict_or_empty(m.get("pricing"))
    caps = _dict_or_empty(m.get("caps"))
    val = _dict_or_empty(m.get("value"))
    req_d = _dict_or_empty(m.get("requests"))
    bm = _dict_or_empty(m.get("benchmarks"))

    if is_cc:
        cap_raw = _first_num(pr.get("monthly_credits"), caps.get("cap_mo_usd"), m.get("credits"))
        cap_s = _fmt_num(cap_raw, ".0f", "$") if cap_raw is not None else ("Free" if m.get("is_free") else "—")
    else:
        cap_raw = _first_num(caps.get("cap_mo_usd"), pr.get("monthly_usage_limit_usd"), m.get("limit"))
        cap_s = _fmt_num(cap_raw, ".0f", "$", "/m")

    req_raw = _first_num(val.get("effective_requests_per_month"), req_d.get("requests_per_month"), m.get("req_mo_eff"), m.get("req_mo"))
    qcap_raw = _first_num(bm.get("capability_q"), bm.get("q_capability"), m.get("q_cap"))
    eff_c_raw = _first_num(val.get("effective_cost_per_request"), m.get("cost_per_request_usd"), m.get("cost_per_req"))
    val_raw = _first_num(val.get("value_score"), val.get("qvi_score"), None if isinstance(m.get("value"), dict) else m.get("value"), m.get("value_score"))

    return (
        f"| {_badge(rank)} | {name} | {_fmt_num(pr.get('input_per_1m'), '.2f', '$')} "
        f"| {_fmt_num(pr.get('output_per_1m'), '.2f', '$')} | {cap_s} "
        f"| {_fmt_num(req_raw, ',.0f')} | {_fmt_num(qcap_raw, '.1f')} "
        f"| {_fmt_num(eff_c_raw, '.4f', '$')} | {_fmt_num(val_raw, '.1f')} |"
    )


def _cost_radar_section(heading: str, subtitle: str, col4: str, models: list[dict], is_cc: bool) -> list[str]:
    out = [
        "",
        f"## {heading}",
        subtitle,
        "",
        f"| Rank | Model | In / 1M | Out / 1M | {col4} | Req/Mo | Q(Cap) | Eff c/r | Value Score |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for i, m in enumerate(models[:6], start=1):
        out.append(_cost_radar_row(i, m, is_cc))
    return out


def _free_tier_lines(free_models: list[dict]) -> list[str]:
    out = [
        "",
        "## 🎁 Free Tier Champions",
        "| Rank | Model | Provider | Q(Cap) | P(Succ) | FGI | Context |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for i, m in enumerate(free_models[:6], start=1):
        bm = _dict_or_empty(m.get("benchmarks"))
        qcap_raw = _first_num(bm.get("capability_q"), m.get("q_cap"))
        psucc_raw = _first_num(bm.get("p_success"), m.get("p_success"))
        psucc_pct = psucc_raw * 100 if psucc_raw is not None and psucc_raw <= 1 else psucc_raw
        fgi_raw = _first_num(bm.get("fgi_score"), m.get("fgi"))
        ctx_val = bc._safe_int(_first_num(bm.get("openrouter_context"), m.get("context_length")))
        ctx = f"{ctx_val // 1000}k" if ctx_val else "—"
        name = m.get("display") or m.get("model_id") or m.get("name") or "—"
        prov = m.get("provider") or "opencode"
        out.append(
            f"| {_badge(i)} | {name} | {prov} "
            f"| {_fmt_num(qcap_raw, '.1f')} | {_fmt_num(psucc_pct, '.1f', suffix='%')} "
            f"| {_fmt_num(fgi_raw, '.1f')} | {ctx} |"
        )
    return out


def generate_akatsuki_radar_content(today_str: str) -> str:
    """Generate machine-structured Akatsuki note for Model-Benchmarks-Live.md."""
    models = _load_json_dict(DATA / "benchmarks.json").get("models") or []
    oc_models = _load_json_dict(DATA / "ocgo_live.json").get("models") or []
    cc_models = _load_json_dict(DATA / "cc_live.json").get("models") or []
    free_models = _load_json_dict(DATA / "free_models.json").get("models") or []
    frontier_provs = _dict_or_empty(_load_json_dict(DATA / "frontier_models.json").get("providers"))

    iso_now = dt.datetime.now(dt.UTC).isoformat()
    lines = [
        "---",
        'title: "Live Model Benchmarks & Pricing Radar"',
        f"date: {today_str[:4]}-{today_str[4:6]}-{today_str[6:]}",
        "type: note",
        "tags:",
        "  - agents",
        "  - llm",
        "  - benchmarks",
        "  - pricing",
        "  - telemetry",
        'summary: "Automated live sync of LLM benchmark evaluations, OpenCode/CommandCode pricing limits, and free-tier rankings."',
        f"updated: {iso_now}",
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
        "- **Upstream Feeds**: Artificial Analysis, Vals Index, LMArena, LiveBench, FrontierCode 2.0, FrontierSWE, CursorBench 4.0, OpenRouter, OpenCode Go, CommandCode GOAT, Cline",
        "- **Local Engine**: `checkers/benchmark_sync_daemon.py` (`bsync --sync-now`)",
        "",
    ]
    lines.extend(_frontier_master_lines(models))
    lines.extend(_provider_section_lines(frontier_provs))
    lines.extend(_cost_radar_section(
        "💰 OpenCode Go Pricing & Value Radar",
        "- **Standard Unit**: `$/1M tokens` · **Account Allowance**: shared `5h=20%` · `weekly=50%` · `monthly=100%` of model Monthly limit (`$20/m` Go · `$100/m` Go Plus)",
        "Limit",
        oc_models,
        is_cc=False,
    ))
    lines.extend(_cost_radar_section(
        "⚡ CommandCode GOAT Quota & Value Radar",
        "- **Standard Unit**: `$/1M tokens` · **Account Caps**: `$14/5h` · `$35/wk` · `$70/mo` · Credits `$20`–`$70`",
        "Credits",
        cc_models,
        is_cc=True,
    ))
    lines.extend(_free_tier_lines(free_models))
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
    """Normalize markdown body (ignoring frontmatter and Last Updated) to detect real table changes."""
    body_idx = text.find("# ⚡ Live Model Benchmarks")
    if body_idx != -1:
        text = text[body_idx:]
    return "\n".join(
        s for line in text.splitlines()
        if (s := line.strip()) and not s.startswith("- **Last Updated**:")
    )


def _write_akatsuki_via_cli(akatsuki_bin: pathlib.Path, note_rel: str, content: str, verbose: bool) -> bool:
    try:
        proc = subprocess.run(
            [str(akatsuki_bin), "write", note_rel, "--overwrite"],
            input=content,
            text=True,
            capture_output=True,
            timeout=15,
        )
        if proc.returncode == 0:
            if verbose:
                log(f"  Saved Akatsuki note via CLI -> {note_rel}")
            return True
        log(f"  WARN: akatsuki write returned {proc.returncode}: {proc.stderr.strip()[:100]}")
        return False
    except (OSError, subprocess.SubprocessError) as e:
        log(f"  WARN: Failed to execute akatsuki write: {e}")
        return False


def _ensure_vault_links(vault: pathlib.Path, verbose: bool) -> None:
    link_specs = (
        (
            vault / "30-Agents" / "Agents-MOC.md",
            "## 🔬 Model Benchmarking & Empirical Evaluations",
            f"\n\n- {_RADAR_TARGET_LINK}: Automated daily sync of benchmark evaluations, OpenCode/CommandCode pricing, and free-tier rankings.",
            "Agents-MOC.md",
        ),
        (vault / "20-Projects" / "llm-benchyyyy.md", "## 🔗 Related", f"\n- {_RADAR_TARGET_LINK}", "20-Projects/llm-benchyyyy.md"),
        (vault / "30-Agents" / "Model-Benchmarks-2026.md", "## 🔗 Related", f"\n- {_RADAR_TARGET_LINK}", "30-Agents/Model-Benchmarks-2026.md"),
    )
    for path, heading, addition, label in link_specs:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if _RADAR_TARGET_LINK in text or heading not in text:
                continue
            bc.atomic_write_text(path, text.replace(heading, f"{heading}{addition}", 1))
            if verbose:
                log(f"  Linked note in {label}")
        except OSError as e:
            log(f"  WARN: Failed to link in {label}: {e}")


def _log_akatsuki_work(akatsuki_bin: pathlib.Path, verbose: bool) -> None:
    summary = "sync upstream -> refreshed benchmarks, frontier (openai/claude/gemini) & ocgo/ccgo prices; saved to akatsuki"
    try:
        proc = subprocess.run(
            [str(akatsuki_bin), "log", "--project", "llm-benchyyyy", "--summary", summary],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            if verbose:
                log("  Deposited Akatsuki work log telemetry")
            return
        log(f"  WARN: akatsuki log exit {proc.returncode}: {proc.stderr.strip()[:100]}")
    except (OSError, subprocess.SubprocessError) as e:
        log(f"  WARN: Failed to deposit akatsuki log: {e}")


def _find_akatsuki_bin() -> pathlib.Path | None:
    if os.getenv("AKATSUKI_VAULT") is not None:
        return None
    raw_bin = shutil.which("akatsuki") or (pathlib.Path.home() / ".local" / "bin" / "akatsuki")
    return pathlib.Path(raw_bin) if raw_bin and pathlib.Path(raw_bin).exists() else None


def _persist_akatsuki_note(
    akatsuki_bin: pathlib.Path | None,
    note_file: pathlib.Path,
    note_rel: str,
    content: str,
    verbose: bool,
) -> bool:
    if akatsuki_bin and _write_akatsuki_via_cli(akatsuki_bin, note_rel, content, verbose):
        return True
    try:
        note_file.parent.mkdir(parents=True, exist_ok=True)
        bc.atomic_write_text(note_file, content)
        if verbose:
            log(f"  Saved Akatsuki note directly -> {note_file}")
        return True
    except OSError as e:
        log(f"  WARN: Failed to write note directly: {e}")
        return False


def _is_note_unchanged(note_file: pathlib.Path, content: str) -> bool:
    if not note_file.exists():
        return False
    try:
        return _normalize_radar_content_for_diff(note_file.read_text(encoding="utf-8")) == _normalize_radar_content_for_diff(content)
    except OSError:
        return False


def save_results_to_akatsuki(verbose: bool = True) -> bool:
    """Save synthesized benchmark and pricing radar to Akatsuki vault and log telemetry."""
    vault = find_akatsuki_vault()
    if not vault:
        if verbose:
            log("  Akatsuki vault not found — skipping Akatsuki persistence")
        return False

    today_str = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    content = generate_akatsuki_radar_content(today_str)
    note_rel = "30-Agents/Model-Benchmarks-Live.md"
    note_file = vault / note_rel

    if _is_note_unchanged(note_file, content):
        if verbose:
            log("  Akatsuki note content unchanged — skipping rewrite and telemetry to prevent bloat")
        return True

    akatsuki_bin = _find_akatsuki_bin()
    if not _persist_akatsuki_note(akatsuki_bin, note_file, note_rel, content, verbose):
        return False

    _ensure_vault_links(vault, verbose)
    if akatsuki_bin:
        _log_akatsuki_work(akatsuki_bin, verbose)
    return True


def _refresh_master_baseline() -> tuple[pathlib.Path | None, bool]:
    try:
        import llm_benchmark_aggregator as lba

        cat = lba.build_universal_catalog(
            live_map=lba.load_livebench_data(fetch=False),
            lm_map=lba.load_lmarena_data(fetch=False),
            aa_map=lba.load_aa_data(fetch=False),
            vals_map=lba.load_vals_data(fetch=False),
            fc2_map=lba.load_frontiercode_data(fetch=False),
            fswe_map=lba.load_frontierswe_data(fetch=False),
            cursor_map=lba.load_cursor_data(fetch=False),
        )
        lba.calculate_composite_scores(cat)
        models = [m for m in cat.values() if not m.get("unmatched")]
        models.sort(key=lambda m: m.get("composite_score") or 0.0, reverse=True)
        prev_snap = lba.load_previous_snapshot(DATA / "benchmarks.json")
        if not models:
            log("  REFUSE baseline rewrite: 0 evaluated models — keeping benchmarks.json")
            return None, False
        collapsed, prev_n = _baseline_collapsed(models, prev_snap)
        if collapsed:
            log(f"  REFUSE baseline rewrite: {len(models)} evaluated vs {prev_n} prev — keeping benchmarks.json")
            return None, False
        diff = lba.diff_model_catalog(models, prev_snap, id_key="display")
        base_p = lba.save_baseline(diff["rows"], diff)
        log(f"  Refreshed Master Baseline -> {base_p.name} ({len(diff['rows'])} evaluated models)")
        return base_p, True
    except Exception as e:
        log(f"  WARN: Failed to refresh master baseline: {e}")
        return None, False


def _sync_lmarena_snapshot(today: str, force: bool, verbose: bool) -> pathlib.Path | None:
    try:
        payload = bc.fetch_lmarena_hf_snapshot(RAW, verbose=False, force=force)
        if not payload:
            return None
        if verbose:
            date_tag = payload["rows"][0].get("leaderboard_publish_date") if payload.get("rows") else "?"
            log(f"  LMArena HF cached -> lmarena_hf_{today}.json (board {date_tag})")
        return RAW / f"lmarena_hf_{today}.json"
    except Exception as e:
        log(f"  WARN LMArena HF fetch failed: {e}")
        return None


def _sync_cursor_evals_snapshot(today: str, force: bool, verbose: bool) -> pathlib.Path | None:
    target = RAW / f"cursor_evals_{today}.json"
    if target.exists() and not force:
        if verbose:
            log(f"  CursorBench 4.0 cached -> {target.name}")
        return target
    try:
        parsed = bc.load_or_fetch_cursor_evals(RAW, force=force, allow_fetch=True)
        if not parsed:
            return None
        matches = sorted(RAW.glob("cursor_evals_*.json"))
        chosen = matches[-1] if matches else None
        if verbose and chosen:
            log(f"  CursorBench 4.0 synced -> {chosen.name} ({len(parsed)} rows)")
        return chosen
    except Exception as e:
        log(f"  WARN CursorBench 4.0 fetch failed: {e}")
        return None


def sync_all_sources(verbose: bool = True, force: bool = False) -> dict[str, pathlib.Path | bool | None]:
    """Fetch all upstream benchmark feeds, refresh all result/pricing databases, and save to Akatsuki."""
    RAW.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    results: dict[str, pathlib.Path | bool | None] = {}

    log("=== Starting Upstream Benchmark Synchronization ===")
    for key, label, url, tmpl in _FEED_SPECS:
        results[key] = _fetch_and_save(label, url, RAW / tmpl.format(today=today), MIN_SNAPSHOT_BYTES[key], force, verbose, feed_key=key)
    results["lmarena"] = _sync_lmarena_snapshot(today, force, verbose)
    results["cursor_evals"] = _sync_cursor_evals_snapshot(today, force, verbose)

    missing = sorted(k for k, v in results.items() if v is None)
    if missing:
        log(f"  WARN {len(missing)} feed(s) missing with no usable cache: {', '.join(missing)}")

    prune_raw_snapshots(RAW, keep_days=3, verbose=verbose)

    base_p, baseline_ok = _refresh_master_baseline()
    if base_p is not None:
        results["baseline_json"] = base_p

    refresh_suite_results(results, verbose=verbose)
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

    def _term_handler(signum, frame):
        log(f"Received signal {signum}. Terminating daemon gracefully.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _term_handler)
    signal.signal(signal.SIGINT, _term_handler)

    while True:
        sec = seconds_until_next_target_time(target_hour, target_minute)
        next_dt = dt.datetime.now() + dt.timedelta(seconds=sec)
        log(f"Next scheduled sync: {next_dt.strftime('%Y-%m-%d %H:%M:%S')} (in {sec / 3600:.2f} hours)")

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
        time.sleep(65)


_STATUS_DATA_FEEDS = (
    ("Master Baseline", "benchmarks.json"),
    ("OpenCode Go Live", "ocgo_live.json"),
    ("CommandCode Live", "cc_live.json"),
    ("Free Models", "free_models.json"),
    ("Stealth Models", "stealth_models.json"),
    ("Frontier Models (OpenAI/Claude/Gemini)", "frontier_models.json"),
)

_STATUS_RAW_FEEDS = (
    ("LiveBench CSV", "livebench_{today}.csv", "livebench_[0-9]*.csv"),
    ("LiveBench Categories", "livebench_categories_{today}.json", "livebench_categories_*.json"),
    ("LMArena HF Board", "lmarena_hf_{today}.json", "lmarena_hf_*.json"),
    ("Artificial Analysis HTML", "artificial_analysis_{today}.html", "artificial_analysis_*.html"),
    ("Vals Index HTML", "vals_index_{today}.html", "vals_index_*.html"),
    ("FrontierCode 2.0 JSON", "frontiercode_{today}.json", "frontiercode_*.json"),
    ("FrontierSWE HTML", "frontierswe_{today}.html", "frontierswe_*.html"),
    ("CursorBench 4.0 JSON", "cursor_evals_{today}.json", "cursor_evals_*.json"),
    ("OpenRouter Models", "openrouter_models_{today}.json", "openrouter_models_*.json"),
    ("CommandCode GOAT Docs", "cc_goat_docs_{today}.html", "cc_goat_docs_*.html"),
    ("Cline Models", "cline_models_{today}.json", "cline_models_*.json"),
    ("OpenCode Go Docs", "opencode_go_docs_{today}.html", "opencode_go_docs_*.html"),
    ("OpenCode Go Models", "opencode_go_models_{today}.json", "opencode_go_models_*.json"),
    ("OpenCode Zen Models", "opencode_zen_models_{today}.json", "opencode_zen_models_*.json"),
)


def _feed_entry(name: str, matches: list[pathlib.Path], today_name: str) -> dict:
    if not matches:
        return {"feed": name, "latest_file": "— (missing)", "size_kb": 0, "mtime": "—", "is_today": False}
    latest = matches[-1]
    st = latest.stat()
    return {
        "feed": name,
        "latest_file": latest.name,
        "size_kb": st.st_size / 1024,
        "mtime": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "is_today": latest.name == today_name,
    }


def get_cache_status() -> dict:
    """Inspect all cached snapshot files and report their status."""
    today = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    status_report = []
    for name, tmpl, glob_pat in _STATUS_RAW_FEEDS:
        matches = [pathlib.Path(p) for p in sorted(glob.glob(str(RAW / glob_pat)))]
        status_report.append(_feed_entry(name, matches, tmpl.format(today=today)))
    for name, fname in _STATUS_DATA_FEEDS:
        p = DATA / fname
        status_report.append(_feed_entry(name, [p] if p.exists() else [], fname))

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
        stat = "✅ Fresh" if r["is_today"] else ("⚠️ Cached" if r["size_kb"] > 0 else "❌ Missing")
        sz_str = f"{r['size_kb']:.1f} KB" if r["size_kb"] > 0 else "—"
        print(f" {r['feed']:<25} {r['latest_file']:<32} {sz_str:<10} {stat:<10}")
    print("-" * 80)


def install_systemd():
    """Generate and configure systemd user service & timer."""
    user_systemd = pathlib.Path.home() / ".config" / "systemd" / "user"
    user_systemd.mkdir(parents=True, exist_ok=True)
    py_bin = sys.executable
    daemon_script = pathlib.Path(__file__).resolve()

    service_content = (
        "[Unit]\nDescription=LLM Benchmark Daily Sync Service\n"
        "After=network-online.target\nWants=network-online.target\n\n"
        f'[Service]\nType=oneshot\nWorkingDirectory="{ROOT}"\nExecStart="{py_bin}" "{daemon_script}" --sync-now\n'
    )
    timer_content = (
        "[Unit]\nDescription=Run LLM Benchmark Daily Sync at 08:00\n"
        "Requires=llm-bench-sync.service\n\n"
        "[Timer]\nOnCalendar=*-*-* 08:00:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"
    )
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
    """Output crontab configuration for daily 08:00 sync."""
    py_bin = sys.executable
    daemon_script = pathlib.Path(__file__).resolve()
    cron_line = f'0 8 * * * "{py_bin}" "{daemon_script}" --sync-now >> "{LOGS}" 2>&1'
    print("Crontab entry for daily 08:00 sync:")
    print("-" * 60)
    print(cron_line)
    print("-" * 60)
    print(f"To install, run: (crontab -l 2>/dev/null; echo '{cron_line}') | crontab -")


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
