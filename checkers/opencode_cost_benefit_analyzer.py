#!/usr/bin/env python3
"""
ocgo_check.py — OpenCode Go catalog checker

Checks the OpenCode Go catalog (docs + API) against benchmarks from
Artificial Analysis / LMArena / OpenRouter, and produces a cost/benefit
analysis against the Go usage limits ($12/5h, $30/wk, $60/mo pooled).

Offline by default (rule 7): reads dated snapshots from docs/data/raw/;
--fetch is the only network path. No API keys, stdlib only.
"""
import argparse
import datetime as dt
import glob
import html as html_lib
import json
import math
import os
import pathlib
import re
import shutil
import statistics
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parent
for _p in (HERE.parent, HERE.parent.parent, HERE.parent.parent.parent):
    if (_p / "setup.sh").exists() or (_p / ".git").exists():
        ROOT = _p
        break
DATA = ROOT / "docs" / "data"
RAW = DATA / "raw"
OUT = ROOT / "docs" / "reports"

import benchmark_common as bc
from benchmark_common import (
    C_BOLD, C_DIM,
    BG_EVEN, BG_ODD, BG_HEADER,
    C_GOLD, C_SILVER, C_BRONZE,
    C_GREEN, C_CYAN, C_YELLOW, C_MAGENTA, C_WHITE, C_GRAY, C_RED,
    parse_price,
    get_z_scores, compute_capability_q, compute_p_success, compute_token_multiplier,
    compute_effective_cost, compute_avi, compute_fgi, compute_bfi,
    parse_lmarena,
    compute_role_recommendations, render_role_recommendations_cli,
    render_role_recommendations_html,
    load_previous_snapshot, diff_model_catalog, render_removed_models_cli,
)
# NOTE (memory.md rule 9, S1-m3): norm_id/parse_aa/parse_openrouter/parse_livebench/
# _safe_float/_safe_int/_safe_int_round/display_len/color_cell/C_RESET are deliberately
# NOT imported: this module redefines every one of them below with proven, intentional
# divergences from the benchmark_common originals (e.g. ogc._safe_float REJECTS
# "$"-prefixed values while bc's strips them). The locals are the contract for this
# checker and for ogc.* callers (fcheck/scheck); do not "restore" the imports — editing
# bc's versions does not change this file's behavior, and shadowed imports only invite
# fixes landing in the wrong function.


def pick_latest_raw(name_part):
    """Newest snapshot in data/raw/ whose name contains name_part, or None."""
    return bc.pick_latest_raw(RAW, name_part)


def offline_data_note():
    """S1-M3 banner parity with bcheck: name the raw-snapshot dates an offline
    run reads; sources past CACHE_TTL_H are WARNed and then used (never fetched).
    Returns (banner line, data label reused by the HTML report)."""
    labels = (("docs", "opencode_go_docs"), ("api", "opencode_go_models"),
              ("OpenRouter", "openrouter_models"), ("AA", "artificial_analysis"),
              ("LMArena", "lmarena"), ("LiveBench", "livebench_2"))
    dates, stale = [], []
    for name, part in labels:
        snap = bc.pick_latest_raw(RAW, part)
        if snap is None:
            stale.append(f"{name} missing")
            continue
        ds = bc.snapshot_date_str(snap)
        if ds:
            dates.append(ds)
        if bc.snapshot_age_hours(snap) > bc.CACHE_TTL_H:
            stale.append(f"{name} {bc.snapshot_age_hours(snap) / 24:.0f}d old")
    span = f"{min(dates)}..{max(dates)}" if dates else "none"
    label = f"OFFLINE (data: {span})"
    line = "  " + label
    if stale:
        line += "\n  WARN cached responses >24h — run with --fetch: " + ", ".join(stale)
    return line, label


OCGO_DOCS = "https://opencode.ai/docs/go/"
OCGO_API = "https://opencode.ai/zen/go/v1/models"
OCGO_USAGE_API = "https://opencode.ai/zen/go/v1/usage"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
LMARENA_URL = "https://arena.ai/leaderboard/text"
ARENA_URL = "https://arena.ai/leaderboard/text"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

# ---------- fallback catalog (from docs snapshot 2026-08-21) ----------
# pricing per 1M tokens, usage = monthly_usage_limit_usd
FALLBACK_PRICING = {
    "grok-4.5": {"input": 2.00, "output": 6.00, "cached_read": 0.30, "cached_write": None, "usage": 15},
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cached_read": 0.02, "cached_write": 0.25, "usage": 15},
    "glm-5.3": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 15},
    "glm-5.2": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "glm-5.1": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "glm-5": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "kimi-k3": {"input": 3.00, "output": 15.00, "cached_read": 0.30, "cached_write": None, "usage": 15},
    "kimi-k2.7-code": {"input": 0.95, "output": 4.00, "cached_read": 0.19, "cached_write": None, "usage": 60},
    "kimi-k2.6": {"input": 0.95, "output": 4.00, "cached_read": 0.16, "cached_write": None, "usage": 60},
    "kimi-k2.5": {"input": 0.95, "output": 4.00, "cached_read": 0.16, "cached_write": None, "usage": 60},
    "mimo-v2.5": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "mimo-v2.5-pro": {"input": 0.435, "output": 0.87, "cached_read": 0.003625, "cached_write": None, "usage": 15},
    "mimo-v2-pro": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "mimo-v2-omni": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "minimax-m3": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": None, "usage": 60},
    "minimax-m2.7": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": 0.375, "usage": 60},
    "minimax-m2.5": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": 0.375, "usage": 60},
    "muse-spark-1.2-contributor": {"input": 0.10, "output": 0.20, "cached_read": 0.002, "cached_write": None, "usage": 60},
    "qwen3.8-max": {"input": 2.00, "output": 6.00, "cached_read": 0.25, "cached_write": 2.50, "usage": 15},
    "qwen3.7-max": {"input": 2.50, "output": 7.50, "cached_read": 0.50, "cached_write": 3.125, "usage": 60},
    "qwen3.7-plus": {"input": 0.40, "output": 1.60, "cached_read": 0.04, "cached_write": 0.50, "usage": 60},
    "qwen3.6-plus": {"input": 0.50, "output": 3.00, "cached_read": 0.05, "cached_write": 0.625, "usage": 60},
    "qwen3.5-plus": {"input": 0.40, "output": 1.60, "cached_read": 0.04, "cached_write": 0.50, "usage": 60},
    "deepseek-v4-pro": {"input": 0.66, "output": 1.98, "cached_read": 0.022, "cached_write": None, "usage": 15},
    "deepseek-v4-flash": {"input": 0.22, "output": 0.66, "cached_read": 0.007, "cached_write": None, "usage": 30},
    "deepseek-v4-flash-vision-exp": {"input": 0.22, "output": 0.66, "cached_read": 0.007, "cached_write": None, "usage": 15},
    "hy3": {"input": 0.14, "output": 0.58, "cached_read": 0.035, "cached_write": None, "usage": 60},
    "hy3-preview": {"input": 0.14, "output": 0.58, "cached_read": 0.035, "cached_write": None, "usage": 60},
    "longcat-2.0": {"input": 0.30, "output": 1.20, "cached_read": 0.006, "cached_write": None, "usage": 60},
    "longcat": {"input": 0.30, "output": 1.20, "cached_read": 0.006, "cached_write": None, "usage": 60},
    "ox-alpha-free": {"input": None, "output": None, "cached_read": None, "cached_write": None, "usage": None},
}

# Docs-backed models (exactly those on https://opencode.ai/docs/go/ pricing table)
DOCS_IDS = {
    "grok-4.5", "gpt-5.6-luna", "glm-5.3", "glm-5.2", "glm-5.1",
    "kimi-k3", "kimi-k2.7-code", "kimi-k2.6",
    "mimo-v2.5", "mimo-v2.5-pro",
    "minimax-m3", "minimax-m2.7", "minimax-m2.5",
    "muse-spark-1.2-contributor",
    "qwen3.8-max", "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus",
    "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp",
    "hy3", "longcat-2.0", "longcat", "ox-alpha-free",
}

FALLBACK_TOKENS = {
    "grok-4.5": (1100, 71500, 220),
    "glm-5.3": (700, 52000, 150),
    "glm-5.2": (700, 52000, 150),
    "glm-5.1": (700, 52000, 150),
    "glm-5": (700, 52000, 150),
    "gpt-5.6-luna": (1000, 50000, 220),
    "kimi-k3": (1050, 76500, 300),
    "kimi-k2.7-code": (870, 55000, 200),
    "kimi-k2.6": (870, 55000, 200),
    "kimi-k2.5": (870, 55000, 200),
    "mimo-v2.5": (830, 71500, 295),
    "mimo-v2.5-pro": (790, 86000, 305),
    "mimo-v2-pro": (830, 71500, 295),
    "mimo-v2-omni": (830, 71500, 295),
    "minimax-m3": (510, 56000, 190),
    "minimax-m2.7": (300, 55000, 125),
    "minimax-m2.5": (300, 55000, 125),
    "muse-spark-1.2-contributor": (620, 71400, 300),
    "qwen3.8-max": (420, 66000, 200),
    "qwen3.7-max": (420, 66000, 200),
    "qwen3.7-plus": (500, 57000, 190),
    "qwen3.6-plus": (500, 57000, 190),
    "qwen3.5-plus": (500, 57000, 190),
    "deepseek-v4-pro": (750, 82000, 290),
    "deepseek-v4-flash": (410, 71300, 310),
    "deepseek-v4-flash-vision-exp": (410, 71300, 310),
    "hy3": (830, 71500, 295),
    "hy3-preview": (830, 71500, 295),
    "longcat-2.0": (500, 60000, 200),
    "longcat": (500, 60000, 200),
    "ox-alpha-free": (0, 0, 0),
}

ACC_5H, ACC_WK, ACC_MO = 12.0, 30.0, 60.0


def log(msg, verbose=False):
    if verbose or True:
        print(msg)


def fetch(url, timeout=20, verbose=False):
    """Fetch URL with UA header. Returns bytes or None."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if verbose:
                print(f"  fetched {url} -> {r.status} {len(body)} bytes")
            return body
    except Exception as e:
        print(f"  WARN fetch {url}: {e}", file=sys.stderr)
        return None


def parse_ocgo_docs(html, verbose=False):
    """Parse pricing, requests, and token estimates from Go docs HTML."""
    pricing = {}
    requests = {}
    tokens = {}
    # Tables: first = requests per window, second = pricing
    tables = re.findall(r"<table.*?</table>", html, flags=re.S)
    if verbose:
        print(f"  docs: found {len(tables)} tables")
    # --- pricing table (second) ---
    if len(tables) >= 2:
        # Use second table (index 1)
        # Extract rows
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[1], flags=re.S)
        for tr in rows[1:]:  # skip header
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
            if len(cells) < 6:
                continue
            # Clean cells
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            model_raw = clean[0]
            inp_raw = clean[1]
            out_raw = clean[2]
            cr_raw = clean[3]
            cw_raw = clean[4]
            usage_raw = clean[5]

            # Model name to id: normalize like "GLM-5.3" -> "glm-5.3"
            # Handle variants like "GPT 5.6 Luna (≤ 272K tokens)" -> "gpt-5.6-luna"
            # and "Qwen3.7 Plus (≤ 256K tokens)" -> "qwen3.7-plus"
            # and "DeepSeek V4 Pro (Off-Peak)" -> "deepseek-v4-pro"
            mid = model_to_id(model_raw)
            if not mid:
                continue
            # Skip duplicate tier rows where we already have a cheaper one?
            # For models with two tiers, keep the cheaper (first) entry
            if mid in pricing:
                continue
            usage = parse_price(usage_raw)
            # For pricing, take first occurrence (cheapest tier)
            pricing[mid] = {
                "input": parse_price(inp_raw),
                "output": parse_price(out_raw),
                "cached_read": parse_price(cr_raw),
                "cached_write": parse_price(cw_raw),
                "usage": usage,
            }
            if verbose and mid in ("grok-4.5", "glm-5.3", "hy3"):
                print(f"    pricing {mid}: {pricing[mid]} from '{model_raw}'")

    # --- requests table (first) ---
    if len(tables) >= 1:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], flags=re.S)
        for tr in rows[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
            if len(cells) < 4:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).replace(",", "").strip() for c in cells]
            model_raw = clean[0]
            mid = model_to_id(model_raw)
            if not mid:
                continue
            try:
                r5 = int(clean[1]) if clean[1] not in ("-", "—", "") else None
                rw = int(clean[2]) if clean[2] not in ("-", "—", "") else None
                rm = int(clean[3]) if clean[3] not in ("-", "—", "") else None
            except Exception:
                continue
            requests[mid] = {"per_5h": r5, "per_week": rw, "per_month": rm}

    # --- token estimates (ul after first table) ---
    # Find the <ul> that follows the first table
    ul_match = re.search(r"requests per month.*?</table>(.*?)<h2", html, flags=re.S)
    if ul_match:
        seg = ul_match.group(1)
        lis = re.findall(r"<li[^>]*>(.*?)</li>", seg, flags=re.S)
        for li in lis:
            txt = re.sub(r"<[^>]+>", "", li).strip()
            # e.g. "Grok 4.5 — 1,100 input, 71,500 cached, 220 output tokens per request"
            # or "GLM-5.3/5.2/5.1 — 700 input, 52,000 cached, 150 output..."
            m = re.search(r"([\d,]+)\s+input.*?([\d,]+)\s+cached.*?([\d,]+)\s+output", txt)
            if not m:
                continue
            try:
                inp = int(m.group(1).replace(",", ""))
                cac = int(m.group(2).replace(",", ""))
                out = int(m.group(3).replace(",", ""))
            except Exception:
                continue
            # Model part is before "—" or "-"
            model_part = re.split(r"[—-]", txt)[0].strip()
            # Handle slash-separated like "GLM-5.3/5.2/5.1"
            for part in re.split(r"\s*/\s*", model_part):
                part = part.strip()
                if "/" in part:
                    continue
                # part like "GLM-5.3" or "Kimi K2.7" or "DeepSeek V4 Pro"
                mid = model_to_id(part)
                if not mid:
                    # Try to map verbose names
                    # "Kimi K2.7" without "Code" should map to both k2.6/k2.7 code?
                    # We'll handle special cases
                    if "kimi k2.7" in part.lower() or "kimi k2.6" in part.lower():
                        for k in ("kimi-k2.7-code", "kimi-k2.6", "kimi-k2.5"):
                            tokens[k] = (inp, cac, out)
                        continue
                    if "glm-5.3" in part.lower():
                        for k in ("glm-5.3", "glm-5.2", "glm-5.1", "glm-5"):
                            tokens[k] = (inp, cac, out)
                        continue
                    continue
                # For cases like "mimo-v2.5" the li says "MiMo-V2.5 — 830..."
                # So we get one id per li, but for slash groups we split above
                tokens[mid] = (inp, cac, out)
                # Handle special expanded cases
                if mid == "mimo-v2.5":
                    tokens["mimo-v2-pro"] = (inp, cac, out)
                    tokens["mimo-v2-omni"] = (inp, cac, out)
                if mid == "mimo-v2.5-pro":
                    pass
                if mid == "qwen3.7-plus":
                    # Also covers qwen3.6-plus? No, separate li
                    pass

    # Ensure every pricing entry has token estimate fallback
    for mid in pricing:
        if mid not in tokens and mid in FALLBACK_TOKENS:
            tokens[mid] = FALLBACK_TOKENS[mid]

    return pricing, requests, tokens


def model_to_id(raw):
    """Map docs display name to canonical model_id."""
    raw = raw.strip()
    # Remove parentheticals like "(≤ 272K tokens)" or "(Off-Peak)" or "(≤ 256K tokens)"
    raw = re.sub(r"\([^)]*\)", "", raw).strip()
    # Normalize spaces and dashes
    # Examples:
    # "Grok 4.5" -> "grok-4.5"
    # "GPT 5.6 Luna" -> "gpt-5.6-luna"
    # "GLM-5.3" -> "glm-5.3"
    # "MiMo V2.5 Pro" -> "mimo-v2.5-pro"
    # "MiniMax M3" -> "minimax-m3"
    # "Muse Spark 1.2 Contributor" -> "muse-spark-1.2-contributor"
    # "Qwen3.8 Max" -> "qwen3.8-max"
    # "Qwen3.7 Plus" -> "qwen3.7-plus"
    # "DeepSeek V4 Pro" -> "deepseek-v4-pro"
    # "DeepSeek V4 Flash Vision Exp" -> "deepseek-v4-flash-vision-exp"
    # "Hy3" -> "hy3"
    # "Ox Alpha Free" -> "ox-alpha-free"
    low = raw.lower()
    # Direct mappings for known oddities
    mapping = {
        "grok 4.5": "grok-4.5",
        "gpt 5.6 luna": "gpt-5.6-luna",
        "glm-5.3": "glm-5.3",
        "glm-5.2": "glm-5.2",
        "glm-5.1": "glm-5.1",
        "glm 5": "glm-5",
        "kimi k3": "kimi-k3",
        "kimi k2.7 code": "kimi-k2.7-code",
        "kimi k2.6": "kimi-k2.6",
        "kimi k2.5": "kimi-k2.5",
        "mimo v2.5": "mimo-v2.5",
        "mimo v2.5 pro": "mimo-v2.5-pro",
        "mimo-v2.5": "mimo-v2.5",
        "mimo-v2.5-pro": "mimo-v2.5-pro",
        "mimo v2 pro": "mimo-v2-pro",
        "mimo v2 omni": "mimo-v2-omni",
        "minimax m3": "minimax-m3",
        "minimax m2.7": "minimax-m2.7",
        "minimax m2.5": "minimax-m2.5",
        "muse spark 1.2 contributor": "muse-spark-1.2-contributor",
        "qwen3.8 max": "qwen3.8-max",
        "qwen3.7 max": "qwen3.7-max",
        "qwen3.7 plus": "qwen3.7-plus",
        "qwen3.6 plus": "qwen3.6-plus",
        "qwen3.5 plus": "qwen3.5-plus",
        "deepseek v4 pro": "deepseek-v4-pro",
        "deepseek v4 flash": "deepseek-v4-flash",
        "deepseek v4 flash vision exp": "deepseek-v4-flash-vision-exp",
        "hy3": "hy3",
        "hy3-preview": "hy3-preview",
        "longcat 2.0": "longcat-2.0",
        "longcat-2.0": "longcat-2.0",
        "longcat": "longcat-2.0",
        "ox alpha free": "ox-alpha-free",
    }
    if low in mapping:
        return mapping[low]
    # Try generic normalization: replace spaces with dashes, keep dots
    # e.g. "GLM-5.3" already, "Qwen3.8 Max" -> "qwen3.8-max"
    # Do: lower, replace " " with "-", strip
    generic = low.replace(" ", "-").replace("_", "-")
    generic = re.sub(r"-+", "-", generic).strip("-")
    # Check if generic matches any fallback key when dots/dashes normalized
    for k in FALLBACK_PRICING:
        if k.replace(".", "-") == generic.replace(".", "-"):
            return k
    # Fallback: if generic looks like a model id, return it
    if re.match(r"^[a-z0-9][a-z0-9\.\-]*$", generic) and len(generic) >= 2:
        return generic
    return None


norm_id = bc.norm_id
parse_aa = bc.parse_aa
parse_openrouter = bc.parse_openrouter
find_aa_for_ocgo = bc.find_aa_for_model
find_lm_for_ocgo = bc.find_lm_for_model
find_or_for_ocgo = bc.find_or_for_model
parse_livebench = bc.parse_livebench
find_livebench_for_ocgo = bc.find_livebench_for_model


def compute_cost(input_per_1m, output_per_1m, cached_per_1m, est_input, est_cached, est_output, cached_write_per_1m=0.0, est_cached_write=0):
    if None in (input_per_1m, output_per_1m, cached_per_1m) or None in (est_input, est_cached, est_output):
        return None
    c_write = (cached_write_per_1m or 0.0) * (est_cached_write or 0) / 1_000_000
    if est_input == 0 and est_cached == 0 and est_output == 0 and (est_cached_write or 0) == 0:
        return 0.0
    return (input_per_1m * est_input / 1_000_000) + (cached_per_1m * est_cached / 1_000_000) + (output_per_1m * est_output / 1_000_000) + c_write


def _safe_float(val, default=None):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return default
        return float(val)
    try:
        s = str(val).strip()
        if not s or s.startswith("$") or s.lower() in ("nan", "none", "null", "undefined", "—", "-", "n/a"):
            return default
        f = float(s.replace(",", ""))
        return default if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return default


def _safe_int(val, default=None):
    f = _safe_float(val, default=None)
    if f is None:
        return default
    return int(round(f))


def _safe_int_round(v):
    f = _safe_float(v, default=None)
    if f is None:
        return None
    return int(round(f))


# ---------- usage API ----------
def _lookup_provider_key(d):
    """Targeted opencode-go/opencode provider lookup in an auth.json dict (S1-C4).

    Only the entry for the provider whose endpoint we call is read — a
    multi-provider credential store must never leak another provider's key.
    """
    if not isinstance(d, dict):
        return None
    for name in ("opencode-go", "opencode"):
        entry = d.get(name)
        if isinstance(entry, dict):
            k = entry.get("key") or entry.get("token")
            if k:
                return str(k).strip()
    return None


def get_api_key():
    for env_var in ("OPENCODE_GO_API_KEY", "OPENCODE_API_KEY", "OPENCODE_GO_KEY"):
        val = os.environ.get(env_var)
        if val:
            return val.strip()
    # Check ~/.pi/agent/auth.json
    pi_auth = pathlib.Path.home() / ".pi" / "agent" / "auth.json"
    if pi_auth.exists():
        try:
            k = _lookup_provider_key(json.loads(pi_auth.read_text(encoding="utf-8")))
            if k:
                return k
        except Exception as e:  # noqa: BLE001
            print(f"  WARN {pi_auth}: unreadable auth.json: {e}", file=sys.stderr)
    # opencode's own auth store keeps one entry per provider; targeting only
    # opencode-go/opencode replaces the first-secret-wins recursive harvest (S1-C4).
    for p in [
        pathlib.Path.home() / ".local" / "share" / "opencode" / "auth.json",
        pathlib.Path.home() / ".config" / "opencode" / "auth.json",
    ]:
        if not p.exists():
            continue
        try:
            k = _lookup_provider_key(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            print(f"  WARN {p}: unreadable auth.json: {e}", file=sys.stderr)
            continue
        if k:
            return k
        print(f"  WARN {p}: no opencode-go/opencode provider entry — usage fetch skipped (no other provider's key is sent)", file=sys.stderr)
    return None


def fetch_usage(key, verbose=False):
    if not key:
        return None, "no key"
    req = urllib.request.Request(OCGO_USAGE_API, headers={"User-Agent": UA, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
            data = json.loads(body)
            # usage may be at top level or under "usage"
            usage = data.get("usage", data) if isinstance(data, dict) else data
            if verbose:
                print(f"  usage: HTTP {r.status} keys={list(usage.keys()) if isinstance(usage, dict) else type(usage)}")
            return usage, None
    except urllib.error.HTTPError as e:
        try:
            b = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            b = str(e)
        return None, f"HTTP {e.code}: {b[:200]}"
    except Exception as e:
        return None, str(e)


def _pct_color(pct, for_html=False):
    # pct = remaining percent 0-100
    if pct is None:
        return ("", "") if for_html else ""
    if for_html:
        if pct > 50:
            return "#3fb950", ""  # green
        if pct > 25:
            return "#d29922", ""  # yellow
        if pct > 10:
            return "#f85149", ""  # red
        return "#f85149", "font-weight:700"
    # ANSI
    if pct > 50:
        return "\033[38;5;48m"  # green
    if pct > 25:
        return "\033[38;5;221m"  # yellow
    if pct > 10:
        return "\033[38;5;205m"  # magenta/red
    return "\033[38;5;196;1m"  # bold bright red


# --- ANSI Styling & Theme Constants ---
C_RESET = "\033[0m"
def display_len(s):
    """Calculate terminal display width (accounting for ANSI escapes and wide emoji characters)."""
    clean = re.sub(r"\033\[[0-9;]*m", "", str(s))
    w = 0
    for ch in clean:
        if ord(ch) in (0x1F947, 0x1F948, 0x1F949, 0x1F3C6, 0x26A1) or (0x1F300 <= ord(ch) <= 0x1FAFF):
            w += 2
        else:
            w += 1
    return w


def color_cell(text, color="", width=None, align="<", bg=""):
    """Format and colorize an individual cell with 1-space internal padding and exact width."""
    raw_w = display_len(text)
    pad_needed = max(0, (width if width is not None else 0) - raw_w)

    if align == ">":
        padded = (" " * pad_needed) + str(text)
    elif align == "^":
        left_pad = pad_needed // 2
        right_pad = pad_needed - left_pad
        padded = (" " * left_pad) + str(text) + (" " * right_pad)
    else:
        padded = str(text) + (" " * pad_needed)

    bg_p = bg if bg else ""
    return f"{bg_p}{color} {padded} {C_RESET}"


def format_compact_num(v):
    """Format large counts compactly e.g. 45.3k, 7.6k, 880."""
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        if v >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if v >= 10_000:
            return f"{v / 1_000:.1f}k" if (v % 1000 != 0) else f"{v // 1000:.0f}k"
        if v >= 1_000:
            return f"{v / 1_000:.1f}k"
        return f"{v:.0f}"
    return str(v)


def render_cli_table(models_list, usage_percents=None, usage_err=None, usage_key_present=False, pareto_ids=None, added_ids=None, removed_models=None, color=True, slim=None, wide=False):
    """Render structured TUI table with adaptive terminal width, usage limits, and alternating row zebra striping."""
    if pareto_ids is None:
        pareto_ids = set()
    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []

    # Adaptive width detection (detect split panes or small windows)
    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_slim = slim if slim is not None else (term_cols < 120 and not wide)

    out = []
    if is_slim:
        headers = [
            ("Rank", 4, "^"),
            ("Model", 20, "<"),
            ("Limit", 6, "^"),
            ("Req/5h", 6, ">"),
            ("Q(Cap)", 6, ">"),
            ("P(Succ)", 7, ">"),
            ("Eff c/r", 7, ">"),
            ("AVI", 5, ">"),
            ("FGI", 4, ">"),
            ("Remain", 10, "^"),
        ]
    else:
        headers = [
            ("Rank", 4, "^"),
            ("Model", 22, "<"),
            ("Limit", 6, "^"),
            ("5h Cap", 6, ">"),
            ("Req/5h", 6, ">"),
            ("Q(Cap)", 6, ">"),
            ("P(Succ)", 7, ">"),
            ("Eff c/r", 7, ">"),
            ("AVI", 5, ">"),
            ("FGI", 4, ">"),
            ("Remain", 10, "^"),
            ("Lev", 4, ">"),
        ]

    total_models = len(models_list)
    top_frontier = max(models_list, key=lambda m: m["value"].get("fgi_score", 0)) if models_list else None
    top_avi = max(models_list, key=lambda m: m["value"].get("avi_score", 0)) if models_list else None
    top_req = max(models_list, key=lambda m: (m["requests"].get("per_5h_docs") or m["requests"].get("per_5h_computed") or 0)) if models_list else None

    col_medals = bc.compute_column_medals(
        models_list,
        {
            "q": (lambda r: r["benchmarks"].get("capability_q") or 0, True, None),
            "psucc": (lambda r: r["benchmarks"].get("p_success") or 0, True, None),
            "avi": (lambda r: r["value"].get("avi_score") or 0, True, None),
            "fgi": (lambda r: r["value"].get("fgi_score") or 0, True, None),
        },
        id_key="model_id",
    )

    # Total inner width between outer box borders
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1

    title_str = "⚡ OPENCODE GO USAGE LIMITS & AGENTIC RADAR (https://opencode.ai/docs/go/#usage-limits)"
    f_info = f"Frontier: {top_frontier['model_id'][:14]} (FGI {top_frontier['value'].get('fgi_score', 0):.1f})" if top_frontier else ""
    v_info = f"Top ROI: {top_avi['model_id'][:14]} (AVI {top_avi['value'].get('avi_score', 0):.1f})" if top_avi else ""
    top_req_cnt = top_req["requests"].get("per_5h_docs") or top_req["requests"].get("per_5h_computed") or 0 if top_req else 0
    s_info = f"Max Bulk: {top_req['model_id'][:12]} ({format_compact_num(top_req_cnt)}/5h)" if top_req else ""
    if is_slim:
        summary_str = f" Caps: $12/5h · $30/wk · $60/mo │ {f_info} │ {v_info}"
    else:
        summary_str = f" Caps: $12/5h · $30/wk · $60/mo │ {f_info} │ {v_info} │ {s_info}"

    diff_notices = []
    diff_parts = []
    if added_ids:
        diff_notices.append(f"{C_BOLD}{C_GREEN}✨ New (+{len(added_ids)}): {', '.join(sorted(added_ids))}{C_RESET}")
        diff_parts.append(f"[+NEW (+{len(added_ids)}): {', '.join(sorted(added_ids))}]")
    if removed_models:
        rem_names = [m.get("model_id", "unknown") for m in removed_models]
        diff_notices.append(f"{C_BOLD}{C_RED}🔻 Removed (-{len(removed_models)}): {', '.join(rem_names)}{C_RESET}")
        diff_parts.append(f"[-REMOVED (-{len(removed_models)}): {', '.join(rem_names)}]")

    out.extend(bc.render_banner_box(
        title_str,
        summary_lines=[summary_str],
        diff_notices=diff_notices,
        inner_w=inner_w,
        color=color,
        plain_title_line=" OPENCODE GO USAGE LIMITS & AGENTIC RADAR — Account Caps: $12/5h · $30/wk · $60/mo",
        plain_diff_parts=diff_parts,
    ))

    if color:
        top_border = "┌" + "┬".join("─" * (w + 2) for _, w, _ in headers) + "┐"
        mid_border = "├" + "┼".join("─" * (w + 2) for _, w, _ in headers) + "┤"
        bot_border = "└" + "┴".join("─" * (w + 2) for _, w, _ in headers) + "┘"

        out.append(f"{C_DIM}{top_border}{C_RESET}")
        hdr_cells = [color_cell(h, C_BOLD + C_WHITE, width=w, align=a, bg=BG_HEADER) for h, w, a in headers]
        out.append(f"{BG_HEADER}{C_DIM}│{C_RESET}" + f"{BG_HEADER}{C_DIM}│{C_RESET}".join(hdr_cells) + f"{BG_HEADER}{C_DIM}│{C_RESET}")
        out.append(f"{C_DIM}{mid_border}{C_RESET}")
    else:
        out.append("-" * (inner_w + 2))
        hdr_str = " ".join([f"{h:^{w}}" if a == "^" else (f"{h:>{w}}" if a == ">" else f"{h:<{w}}") for h, w, a in headers])
        out.append(hdr_str)
        out.append("-" * (inner_w + 2))

    for idx, r in enumerate(models_list):
        rank_num = idx + 1
        bg = BG_ODD if (idx % 2 == 1) else BG_EVEN

        if rank_num == 1:
            rank_str = "🥇#1"
        elif rank_num == 2:
            rank_str = "🥈#2"
        elif rank_num == 3:
            rank_str = "🥉#3"
        else:
            rank_str = f" #{rank_num}"

        is_added = r["model_id"] in added_ids
        m_name_w = 20 if is_slim else 22
        raw_mid = r["model_id"]
        mid_display = f"+{raw_mid}"[:m_name_w] if is_added else raw_mid[:m_name_w]

        usage = r["pricing"]["monthly_usage_limit_usd"]
        usage_str = f"${usage:.0f}/m" if usage is not None else "Free"

        cap_5h_val = r.get("caps", {}).get("cap_5h_usd")
        cap_5h_str = f"${cap_5h_val:.2f}" if cap_5h_val is not None else "—"

        reqs = r.get("requests", {})
        req5_val = reqs.get("per_5h_docs") if reqs.get("per_5h_docs") is not None else reqs.get("per_5h_computed")
        req5_str = format_compact_num(req5_val)

        meds = col_medals.get(r["model_id"], {})
        q_val = r["benchmarks"].get("capability_q", 0)
        p_val = r["benchmarks"].get("p_success", 0)
        eff_c_val = r["value"].get("effective_cost_per_request")
        eff_c_str = f"${eff_c_val:.4f}" if eff_c_val is not None else "—"
        avi_val = r["value"].get("avi_score", 0)
        fgi_val = r["value"].get("fgi_score", 0)
        q_disp = f"{q_val:.1f}" + bc.medal_badge(meds.get("q"), color=color)
        p_disp = f"{p_val:.1f}%" + bc.medal_badge(meds.get("psucc"), color=color)
        avi_disp = f"{avi_val:.1f}" + bc.medal_badge(meds.get("avi"), color=color)
        fgi_disp = f"{fgi_val:.1f}" + bc.medal_badge(meds.get("fgi"), color=color)

        rem = r.get("remaining", {})
        overall = rem.get("overall_pct")
        overall_req = rem.get("overall_req")
        if overall is not None:
            if overall_req is not None:
                rem_str = f"{overall:.0f}%({format_compact_num(overall_req)})"
            else:
                rem_str = f"{overall:.0f}%"
        else:
            if usage_key_present and usage_err:
                rem_str = "ERR"
            elif not usage_key_present and not usage_percents:
                rem_str = "N/A"
            else:
                rem_str = "—"

        lev_val = r["value"].get("leverage_vs_10usd_sub")
        lev_str = f"{lev_val:.1f}x" if lev_val else "—"

        if color:
            # Usage allowance color
            if usage == 60:
                limit_color = C_GREEN
            elif usage == 30:
                limit_color = C_CYAN
            elif usage == 15:
                limit_color = C_YELLOW
            else:
                limit_color = C_GRAY

            # Model name color (added in green, pareto in bold gold, normal in white)
            if is_added:
                mid_color = C_BOLD + C_GREEN
            elif r["model_id"] in pareto_ids:
                mid_color = (C_BOLD + C_GOLD)
            else:
                mid_color = C_WHITE

            # Metric color grading (Monotonic: Green -> Cyan -> Yellow -> Gray)
            q_color = bc.score_color_q(q_val)
            p_color = bc.score_color_p(p_val)
            eff_color = bc.color_ladder(eff_c_val, [
                (lambda v: v < 0.002, C_GREEN),
                (lambda v: v < 0.01, C_CYAN),
                (lambda v: v < 0.03, C_YELLOW),
            ], default_color=C_MAGENTA)
            avi_color = bc.score_color_avi(avi_val)
            fgi_color = bc.score_color_fgi(fgi_val)

            # Remaining color
            rem_color = C_GREEN if (overall and overall > 50) else (C_YELLOW if (overall and overall > 25) else (C_MAGENTA if overall is not None else C_DIM))

            row_cells = [
                color_cell(rank_str, C_BOLD + (C_GOLD if rank_num == 1 else (C_SILVER if rank_num == 2 else (C_BRONZE if rank_num == 3 else C_WHITE))), width=4, align="^", bg=bg),
                color_cell(mid_display, mid_color, width=m_name_w, align="<", bg=bg),
                color_cell(usage_str, limit_color, width=6, align="^", bg=bg),
            ]
            if not is_slim:
                row_cells.append(color_cell(cap_5h_str, C_WHITE, width=6, align=">", bg=bg))
            row_cells.extend([
                color_cell(req5_str, C_CYAN if (req5_val and req5_val >= 3000) else C_WHITE, width=6, align=">", bg=bg),
                color_cell(q_disp, q_color, width=6, align=">", bg=bg),
                color_cell(p_disp, p_color, width=7, align=">", bg=bg),
                color_cell(eff_c_str, eff_color, width=7, align=">", bg=bg),
                color_cell(avi_disp, avi_color, width=5, align=">", bg=bg),
                color_cell(fgi_disp, fgi_color, width=4, align=">", bg=bg),
                color_cell(rem_str, rem_color, width=10, align="^", bg=bg),
            ])
            if not is_slim:
                row_cells.append(color_cell(lev_str, C_DIM, width=4, align=">", bg=bg))

            out.append(f"{bg}{C_DIM}│{C_RESET}" + f"{bg}{C_DIM}│{C_RESET}".join(row_cells) + f"{bg}{C_DIM}│{C_RESET}")
        else:
            row_items = [
                f"{rank_str:^4}",
                f"{mid_display:<{m_name_w}}",
                f"{usage_str:^6}",
            ]
            if not is_slim:
                row_items.append(f"{cap_5h_str:>6}")
            row_items.extend([
                f"{req5_str:>6}",
                f"{q_disp:>6}",
                f"{p_disp:>7}",
                f"{eff_c_str:>7}",
                f"{avi_disp:>5}",
                f"{fgi_disp:>4}",
                f"{rem_str:^10}",
            ])
            if not is_slim:
                row_items.append(f"{lev_str:>4}")
            out.append(" ".join(row_items))

    if color:
        out.append(f"{C_DIM}{bot_border}{C_RESET}")
    else:
        out.append("-" * (inner_w + 2))

    # Removed / Deprecated models display
    if removed_models:
        out.append("")
        out.extend(render_removed_models_cli(removed_models, color=color, is_slim=is_slim, id_key="model_id"))

    out.append("")
    out.extend(bc.render_metric_guide_cli(
        "OpenCode Go Usage Limits & Metric Guide",
        [
            ("Gold Bold", "Pareto Frontier (undefeated capability vs cost curve).", C_GOLD),
            ("Green (+)", "Newly added model vs previous baseline snapshot.", C_GREEN),
            ("Badges ¹²³", "🥇/🥈/🥉 place leaders in respective column.", C_YELLOW),
            ("Quota Model", "Pooled $12/5h · $30/wk · $60/mo. Window cap = $12 × (Usage / 60).", C_WHITE),
            ("$15/mo Tier", "($3.00/5h): GLM-5.3 (~220 req/5h), Kimi K3 (~110) — spec lock, no loops.", C_YELLOW),
            ("$30/mo Tier", "($6.00/5h): DeepSeek V4 Flash (~7.6k req/5h) — daily driver iterative coder.", C_CYAN),
            ("$60/mo Tier", "($12.00/5h): MiMo-V2.5 (~30k), Muse Spark (~45k), LongCat (~16k) — bulk fills.", C_GREEN),
            ("Eff c/r", "Real Cost/Task = Base cost/req × retry multiplier (T_mult).", C_WHITE),
            ("Allowed Limits", "Run 'ocheck --limits' for full multi-window allowed request caps & quota balance.", C_WHITE),
        ],
        color=color,
    ))

    role_recs = compute_role_recommendations(models_list, context="ocheck")
    if role_recs:
        out.append("")
        out.extend(render_role_recommendations_cli(role_recs, color=color, is_slim=is_slim, width=inner_w))

    return "\n".join(out)


def format_countdown(iso_str: str | None) -> str:
    """Format an ISO reset timestamp into a human-readable relative countdown."""
    if not iso_str:
        return "—"
    try:
        target = dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = dt.datetime.now(dt.timezone.utc)
        diff = target - now
        total_sec = int(diff.total_seconds())
        if total_sec <= 0:
            return "resets now"
        days = total_sec // 86400
        hours = (total_sec % 86400) // 3600
        mins = (total_sec % 3600) // 60
        time_part = target.strftime("%Y-%m-%d %H:%M UTC")
        if days > 0:
            return f"in {days}d {hours}h ({time_part})"
        elif hours > 0:
            return f"in {hours}h {mins}m ({time_part})"
        else:
            return f"in {mins}m ({time_part})"
    except Exception:
        return str(iso_str)[:16].replace("T", " ")


def render_limits_table(
    models_list: list[dict],
    usage_raw: dict | None = None,
    usage_percents: dict | None = None,
    usage_resets: dict | None = None,
    usage_err: str | None = None,
    usage_key_present: bool = False,
    color: bool = True,
    slim: bool | None = None,
    wide: bool = False,
) -> str:
    """Render comprehensive OpenCode Go allowed limits, multi-window quotas, and live subscription balance."""
    if usage_percents is None:
        usage_percents = {}
    if usage_resets is None:
        usage_resets = {}

    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_slim = slim if slim is not None else (term_cols < 120 and not wide)

    out = []

    # 1. Section: Subscription Windows Summary Box
    win_headers = [
        ("Window", 14, "<"),
        ("Budget Cap", 11, ">"),
        ("Used (%)", 10, ">"),
        ("Balance ($)", 12, ">"),
        ("Status", 10, "^"),
        ("Resets At / Countdown", 34, "<"),
    ]
    win_inner_w = sum(w + 2 for _, w, _ in win_headers) + len(win_headers) - 1

    top_banner = "⚡ OPENCODE GO SUBSCRIPTION POOLED WINDOWS & LIVE BALANCE"
    sub_banner = "Official limits: $12.00 / 5h rolling · $30.00 / weekly · $60.00 / monthly"
    out.extend(bc.render_banner_box(
        top_banner,
        summary_lines=[sub_banner],
        inner_w=win_inner_w,
        color=color,
        plain_title_line=f" {top_banner}",
    ))

    window_defs = [
        ("rolling", "5h Rolling", 12.00),
        ("weekly", "Weekly", 30.00),
        ("monthly", "Monthly", 60.00),
    ]

    pipe = f"{C_CYAN}│{C_RESET}" if color else "|"
    if color:
        top_border = f"{C_CYAN}┌" + "┬".join("─" * (w + 2) for _, w, _ in win_headers) + f"┐{C_RESET}"
        sep_border = f"{C_CYAN}├" + "┼".join("─" * (w + 2) for _, w, _ in win_headers) + f"┤{C_RESET}"
        bot_border = f"{C_CYAN}└" + "┴".join("─" * (w + 2) for _, w, _ in win_headers) + f"┘{C_RESET}"
    else:
        top_border = "+" + "+".join("-" * (w + 2) for _, w, _ in win_headers) + "+"
        sep_border = "+" + "+".join("-" * (w + 2) for _, w, _ in win_headers) + "+"
        bot_border = "+" + "+".join("-" * (w + 2) for _, w, _ in win_headers) + "+"

    out.append(top_border)
    hdr_cells = []
    for hname, hw, halign in win_headers:
        if halign == ">":
            cell = f" {hname.rjust(hw)} "
        elif halign == "^":
            cell = f" {hname.center(hw)} "
        else:
            cell = f" {hname.ljust(hw)} "
        hdr_cells.append(f"{C_BOLD}{C_WHITE}{cell}{C_RESET}" if color else cell)
    out.append(pipe + pipe.join(hdr_cells) + pipe)
    out.append(sep_border)

    for idx, (w_key, w_name, w_cap) in enumerate(window_defs):
        bg = (BG_EVEN if idx % 2 == 0 else BG_ODD) if color else ""
        pct_used = usage_percents.get(w_key)
        reset_iso = usage_resets.get(w_key)

        if pct_used is not None:
            pct_str = f"{pct_used:.0f}%"
            pct_rem = max(0.0, 100.0 - pct_used)
            bal_usd = w_cap * (pct_rem / 100.0)
            bal_str = f"${bal_usd:.2f}"

            if pct_rem > 50:
                stat_str = "● OK"
                stat_col = C_GREEN
            elif pct_rem > 20:
                stat_str = "▲ WARN"
                stat_col = C_YELLOW
            else:
                stat_str = "✖ CRIT"
                stat_col = C_RED
            countdown_str = format_countdown(reset_iso)
        else:
            pct_str = "N/A"
            bal_str = f"${w_cap:.2f}"
            stat_str = "—"
            stat_col = C_GRAY
            countdown_str = "No active key" if not usage_key_present else "N/A"

        row_vals = [
            (w_name, 14, "<", C_BOLD + C_WHITE if color else ""),
            (f"${w_cap:.2f}", 11, ">", C_CYAN if color else ""),
            (pct_str, 10, ">", _pct_color(100 - pct_used if pct_used is not None else None) if color else ""),
            (bal_str, 12, ">", C_BOLD + (C_GREEN if (pct_used or 0) < 50 else C_YELLOW) if color else ""),
            (stat_str, 10, "^", stat_col if color else ""),
            (countdown_str, 34, "<", C_DIM if color else ""),
        ]

        row_cells = []
        for rtext, rw, ralign, rcol in row_vals:
            if ralign == ">":
                pad_t = rtext.rjust(rw)
            elif ralign == "^":
                pad_t = rtext.center(rw)
            else:
                pad_t = rtext.ljust(rw)
            if color:
                cell_text = f"{bg} {rcol}{pad_t}{C_RESET}{bg} "
            else:
                cell_text = f" {pad_t} "
            row_cells.append(cell_text)

        out.append(pipe + pipe.join(row_cells) + pipe)

    out.append(bot_border)
    out.append("")

    # 2. Section: Per-Model Allowed Limits & Request Capacities
    if is_slim:
        mod_headers = [
            ("Model", 18, "<"),
            ("Tier", 6, "^"),
            ("5h Cap", 6, ">"),
            ("5h Limit", 8, ">"),
            ("Wk Limit", 8, ">"),
            ("Mo Limit", 8, ">"),
            ("5h Rem", 9, ">"),
            ("Mo Rem", 9, ">"),
            ("Cost/Req", 8, ">"),
            ("Pricing ($/1M)", 18, "<"),
        ]
    else:
        mod_headers = [
            ("Model", 22, "<"),
            ("Tier", 6, "^"),
            ("5h Cap", 6, ">"),
            ("5h Limit", 8, ">"),
            ("Wk Limit", 8, ">"),
            ("Mo Limit", 8, ">"),
            ("5h Rem", 11, ">"),
            ("Mo Rem", 11, ">"),
            ("Cost/Req", 8, ">"),
            ("Pricing ($/1M In · Out · CR · CW)", 26, "<"),
        ]

    mod_inner_w = sum(w + 2 for _, w, _ in mod_headers) + len(mod_headers) - 1

    sec2_title = "📋 OPENCODE GO MODEL ALLOWANCES & MULTI-WINDOW REQUEST LIMITS"
    sec2_sub = "Cap formula: Window Limit = Window Pool ($12, $30, $60) * (Tier Cap / $60) / Cost_per_req"

    out.extend(bc.render_banner_box(
        sec2_title,
        summary_lines=[sec2_sub],
        inner_w=mod_inner_w,
        color=color,
        plain_title_line=f" {sec2_title}",
    ))

    if color:
        m_top = f"{C_CYAN}┌" + "┬".join("─" * (w + 2) for _, w, _ in mod_headers) + f"┐{C_RESET}"
        m_sep = f"{C_CYAN}├" + "┼".join("─" * (w + 2) for _, w, _ in mod_headers) + f"┤{C_RESET}"
        m_bot = f"{C_CYAN}└" + "┴".join("─" * (w + 2) for _, w, _ in mod_headers) + f"┘{C_RESET}"
    else:
        m_top = "+" + "+".join("-" * (w + 2) for _, w, _ in mod_headers) + "+"
        m_sep = "+" + "+".join("-" * (w + 2) for _, w, _ in mod_headers) + "+"
        m_bot = "+" + "+".join("-" * (w + 2) for _, w, _ in mod_headers) + "+"

    out.append(m_top)
    m_hdr_cells = []
    for hname, hw, halign in mod_headers:
        if halign == ">":
            cell = f" {hname.rjust(hw)} "
        elif halign == "^":
            cell = f" {hname.center(hw)} "
        else:
            cell = f" {hname.ljust(hw)} "
        m_hdr_cells.append(f"{C_BOLD}{C_WHITE}{cell}{C_RESET}" if color else cell)
    out.append(pipe + pipe.join(m_hdr_cells) + pipe)
    out.append(m_sep)

    def _sort_lim_key(r):
        req5 = r["requests"].get("per_5h_docs") or r["requests"].get("per_5h_computed") or 0
        return (-req5, r["model_id"])

    models_sorted = sorted(models_list, key=_sort_lim_key)

    for idx, r in enumerate(models_sorted):
        bg = (BG_EVEN if idx % 2 == 0 else BG_ODD) if color else ""
        mid = r["model_id"]
        pr = r.get("pricing", {})
        usage_cap = pr.get("monthly_usage_limit_usd")

        if usage_cap is None:
            tier_str = "Free"
            tier_col = C_CYAN
            cap5_str = "—"
        elif usage_cap <= 15:
            tier_str = "$15/m"
            tier_col = C_YELLOW
            cap5_str = "$3.00"
        elif usage_cap <= 30:
            tier_str = "$30/m"
            tier_col = C_CYAN
            cap5_str = "$6.00"
        else:
            tier_str = "$60/m"
            tier_col = C_GREEN
            cap5_str = "$12.00"

        reqs = r.get("requests", {})
        req_5h = reqs.get("per_5h_docs") or reqs.get("per_5h_computed")
        req_wk = reqs.get("per_week_docs") or reqs.get("per_week_computed")
        req_mo = reqs.get("per_month_docs") or reqs.get("per_month_computed")

        req_5h_str = format_compact_num(req_5h) if req_5h else "—"
        req_wk_str = format_compact_num(req_wk) if req_wk else "—"
        req_mo_str = format_compact_num(req_mo) if req_mo else "—"

        rem_dict = r.get("remaining", {}).get("requests", {})
        rem_5h = rem_dict.get("rolling")
        rem_mo = rem_dict.get("monthly")

        pct_rem_5h = r.get("remaining", {}).get("percent", {}).get("rolling")
        pct_rem_mo = r.get("remaining", {}).get("percent", {}).get("monthly")

        if rem_5h is not None and pct_rem_5h is not None:
            rem_5h_str = f"{format_compact_num(rem_5h)} ({pct_rem_5h:.0f}%)" if not is_slim else format_compact_num(rem_5h)
        elif usage_cap is None:
            rem_5h_str = "Unlimited" if not is_slim else "Unlim"
        else:
            rem_5h_str = req_5h_str

        if rem_mo is not None and pct_rem_mo is not None:
            rem_mo_str = f"{format_compact_num(rem_mo)} ({pct_rem_mo:.0f}%)" if not is_slim else format_compact_num(rem_mo)
        elif usage_cap is None:
            rem_mo_str = "Unlimited" if not is_slim else "Unlim"
        else:
            rem_mo_str = req_mo_str

        cost_req = r.get("cost_per_request_usd")
        cost_str = f"${cost_req:.4f}" if cost_req is not None else "—"

        inp_p = pr.get("input_per_1m")
        outp_p = pr.get("output_per_1m")
        cr_p = pr.get("cached_read_per_1m")
        cw_p = pr.get("cached_write_per_1m")

        if is_slim:
            price_str = f"${inp_p or 0:.2f} · ${outp_p or 0:.2f}" if inp_p is not None else "Free / Unpriced"
        else:
            cr_str = f" · ${cr_p:.3f}" if cr_p is not None else ""
            cw_str = f" · ${cw_p:.2f}w" if cw_p is not None else ""
            price_str = f"${inp_p or 0:.2f} / ${outp_p or 0:.2f}{cr_str}{cw_str}" if inp_p is not None else "Free tier"

        mid_w = 18 if is_slim else 22
        m_name = mid[:mid_w]

        m_vals = [
            (m_name, mid_w, "<", C_BOLD + C_WHITE if color else ""),
            (tier_str, 6, "^", tier_col if color else ""),
            (cap5_str, 6, ">", C_DIM if color else ""),
            (req_5h_str, 8, ">", C_BOLD + C_GREEN if color else ""),
            (req_wk_str, 8, ">", C_CYAN if color else ""),
            (req_mo_str, 8, ">", C_WHITE if color else ""),
            (rem_5h_str, 9 if is_slim else 11, ">", C_YELLOW if color else ""),
            (rem_mo_str, 9 if is_slim else 11, ">", C_DIM if color else ""),
            (cost_str, 8, ">", C_DIM if color else ""),
            (price_str, 18 if is_slim else 26, "<", C_GRAY if color else ""),
        ]

        m_row_cells = []
        for rtext, rw, ralign, rcol in m_vals:
            if ralign == ">":
                pad_t = rtext.rjust(rw)
            elif ralign == "^":
                pad_t = rtext.center(rw)
            else:
                pad_t = rtext.ljust(rw)
            if color:
                cell_text = f"{bg} {rcol}{pad_t}{C_RESET}{bg} "
            else:
                cell_text = f" {pad_t} "
            m_row_cells.append(cell_text)

        out.append(pipe + pipe.join(m_row_cells) + pipe)

    out.append(m_bot)
    out.append("")
    out.append(f"🧭 {C_BOLD}OpenCode Go Limits & Tiering Guide:{C_RESET}" if color else "OpenCode Go Limits & Tiering Guide:")
    out.append(f"  • {C_YELLOW}$15/mo Tier{C_RESET} {C_DIM}($3.00/5h window ceiling): High reasoning models (GLM-5.3, Kimi K3, Grok-4.5/4.6). Best for spec lock and deep audits.{C_RESET}" if color else "  • $15/mo Tier ($3.00/5h window ceiling): High reasoning models (GLM-5.3, Kimi K3, Grok-4.5/4.6). Best for spec lock and deep audits.")
    out.append(f"  • {C_CYAN}$30/mo Tier{C_RESET} {C_DIM}($6.00/5h window ceiling): Daily drivers (DeepSeek V4 Flash). High-frequency iteration without quota starvation.{C_RESET}" if color else "  • $30/mo Tier ($6.00/5h window ceiling): Daily drivers (DeepSeek V4 Flash). High-frequency iteration without quota starvation.")
    out.append(f"  • {C_GREEN}$60/mo Tier{C_RESET} {C_DIM}($12.00/5h window ceiling): Bulk generation (MiMo-V2.5, Muse Spark, Minimax M3, Hy3). Massive throughput for boilerplate.{C_RESET}" if color else "  • $60/mo Tier ($12.00/5h window ceiling): Bulk generation (MiMo-V2.5, Muse Spark, Minimax M3, Hy3). Massive throughput for boilerplate.")
    out.append(f"  • {C_BOLD}Live Remaining{C_RESET} {C_DIM}Shows dynamic request headroom computed in real-time against your live /zen/go/v1/usage subscription state.{C_RESET}" if color else "  • Live Remaining: Shows dynamic request headroom computed in real-time against your live /zen/go/v1/usage subscription state.")

    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="OpenCode Go catalog checker — benchmarks + cost/benefit (offline cache by default; live only with --fetch)")
    ap.add_argument("--fetch", "--refresh", action="store_true",
                    help="network path: live-fetch docs/API/OpenRouter/AA/LMArena (+ authenticated usage) and save dated "
                         "snapshots to docs/data/raw/. The default run is fully offline on the snapshot cache: >24h-old "
                         "sources are WARNed and used, never fetched.")
    ap.add_argument("--check", action="store_true",
                    help="print only: writes NOTHING (baseline, reports, raw snapshots) — even combined with --fetch")
    ap.add_argument("--podium", "--winners", action="store_true",
                    help="Display top 3 winners podium table across every metric/column")
    ap.add_argument("--json", action="store_true",
                    help="Output machine-readable JSON to docs/data/ocgo_live.json and docs/reports/ocgo_cost_benefit.json")
    ap.add_argument("--html", action="store_true",
                    help="Generate HTML dashboard in docs/reports/ocgo_cost_benefit.html")
    ap.add_argument("--verbose", action="store_true", help="verbose logging")
    ap.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors and box drawing")
    ap.add_argument("--slim", action="store_true", help="Force compact 102-column table layout (for split panes)")
    ap.add_argument("--wide", action="store_true", help="Force full 120-column table layout")
    ap.add_argument(
        "--limits",
        "--allowed-limits",
        "--allowances",
        action="store_true",
        help="Show detailed OpenCode Go allowed limits, window allowances, and live quota balance",
    )
    ap.add_argument(
        "--sort",
        choices=["avi", "fgi", "bfi", "cap", "req5h", "cost", "intel"],
        default="avi",
        help="Sort order (default: avi)",
    )
    args = ap.parse_args()

    verbose = args.verbose
    do_fetch = bool(args.fetch)
    do_write = not args.check

    print("OpenCode Go — catalog check")
    print(f"  date: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    print(f"  mode: {'fetch (network)' if do_fetch else 'OFFLINE (cache-only)'}" + (" · check: no writes" if args.check else ""))
    data_label = "live fetch"
    if not do_fetch:
        note, data_label = offline_data_note()
        print(note)

    # ---- 1. Fetch OC Go docs + API ----
    pricing_live = {}
    requests_live = {}
    tokens_live = {}
    ocgo_api_ids = []

    if do_fetch:
        body = fetch(OCGO_DOCS, verbose=verbose)
        if body:
            html = body.decode(errors="ignore")
            if do_write:
                snap = RAW / f"opencode_go_docs_{dt.date.today().isoformat().replace('-','')}.html"
                bc.atomic_write_text(snap, html)
                print(f"  saved docs snapshot -> {snap.relative_to(ROOT)} ({len(html)} bytes)")
            pl, rl, tl = parse_ocgo_docs(html, verbose=verbose)
            if pl:
                pricing_live = pl
                print(f"  docs pricing: {len(pl)} models")
            if rl:
                requests_live = rl
            if tl:
                tokens_live = tl
            if verbose:
                print(f"  docs tokens: {len(tl)} models")
        else:
            print("  WARN docs fetch failed, trying snapshot/fallback", file=sys.stderr)

        body = fetch(OCGO_API, verbose=verbose)
        if body:
            try:
                j = json.loads(body)
                if do_write:
                    snap = RAW / f"opencode_go_models_{dt.date.today().isoformat().replace('-','')}.json"
                    bc.atomic_write_text(snap, json.dumps(j, indent=2))
                    print(f"  saved API snapshot -> {snap.relative_to(ROOT)}")
                ids = [m["id"] for m in j.get("data", []) if m.get("id")]
                ocgo_api_ids = ids
                if verbose:
                    print(f"  API models: {len(ids)} -> {ids}")
                else:
                    print(f"  API models: {len(ids)}")
            except Exception as e:
                print(f"  WARN API parse: {e}", file=sys.stderr)
        else:
            print("  WARN API fetch failed", file=sys.stderr)

    if not pricing_live:
        snap_docs = pick_latest_raw("opencode_go_docs")
        if snap_docs:
            try:
                html = snap_docs.read_text(errors="ignore")
                pl, rl, tl = parse_ocgo_docs(html, verbose=verbose)
                if pl:
                    pricing_live = pl
                    print(f"  offline docs pricing: {len(pl)} models ({snap_docs.name})")
                if rl:
                    requests_live = rl
                if tl:
                    tokens_live = tl
            except Exception as e:
                print(f"  WARN offline docs parse: {e}", file=sys.stderr)

    if not ocgo_api_ids:
        snap_api = pick_latest_raw("opencode_go_models")
        if snap_api:
            try:
                j = json.loads(snap_api.read_text(errors="ignore"))
                ids = [m["id"] for m in j.get("data", []) if m.get("id")]
                if ids:
                    ocgo_api_ids = ids
                    print(f"  offline API models: {len(ids)} ({snap_api.name})")
            except Exception as e:
                print(f"  WARN offline API parse: {e}", file=sys.stderr)

    if not ocgo_api_ids:
        ocgo_api_ids = list(FALLBACK_PRICING.keys())
        print(f"  using fallback API ids: {len(ocgo_api_ids)}")
    else:
        for k in FALLBACK_PRICING:
            if k not in ocgo_api_ids and k != "longcat":
                ocgo_api_ids.append(k)

    # Merge pricing: live docs override fallback
    merged_pricing = {}
    for mid in ocgo_api_ids:
        if mid in pricing_live:
            merged_pricing[mid] = pricing_live[mid]
        elif mid in FALLBACK_PRICING:
            merged_pricing[mid] = FALLBACK_PRICING[mid]
        else:
            # Unknown new model not in fallback: try to find pricing from docs via normalized
            merged_pricing[mid] = {"input": None, "output": None, "cached_read": None, "cached_write": None, "usage": 60}

    merged_tokens = {}
    for mid in ocgo_api_ids:
        if mid in tokens_live:
            merged_tokens[mid] = tokens_live[mid]
        elif mid in FALLBACK_TOKENS:
            merged_tokens[mid] = FALLBACK_TOKENS[mid]
        else:
            merged_tokens[mid] = (500, 60000, 200)  # median fallback

    # ---- 2. Fetch OpenRouter ----
    or_map = {}
    if do_fetch:
        body = fetch(OPENROUTER_API, verbose=verbose)
        if body:
            try:
                j = json.loads(body)
                if do_write:
                    snap = RAW / f"openrouter_models_{dt.date.today().isoformat().replace('-','')}.json"
                    bc.atomic_write_text(snap, json.dumps(j, indent=2))
                    print(f"  saved OpenRouter -> {snap.relative_to(ROOT)} ({len(body)} bytes)")
                or_map = parse_openrouter(j, verbose=verbose)
            except Exception as e:
                print(f"  WARN OpenRouter json: {e}", file=sys.stderr)
    if not or_map:
        snap_or = pick_latest_raw("openrouter_models")
        if snap_or:
            try:
                j = json.loads(snap_or.read_text(errors="ignore"))
                or_map = parse_openrouter(j, verbose=verbose)
                print(f"  offline OpenRouter: {len(or_map)} models ({snap_or.name})")
            except Exception as e:
                print(f"  WARN offline OpenRouter parse: {e}", file=sys.stderr)

    # ---- 3. Fetch AA ----
    aa_map = {}
    if do_fetch:
        body = fetch(AA_URL, verbose=verbose)
        if body:
            html = body.decode(errors="ignore")
            if do_write:
                snap = RAW / f"artificial_analysis_{dt.date.today().isoformat().replace('-','')}.html"
                bc.atomic_write_text(snap, html)
                print(f"  saved AA -> {snap.relative_to(ROOT)} ({len(html)} bytes)")
            aa_map = parse_aa(html, verbose=verbose)
        else:
            print("  WARN AA fetch failed", file=sys.stderr)
    if not aa_map:
        snap_aa = pick_latest_raw("artificial_analysis")
        if snap_aa:
            try:
                html = snap_aa.read_text(errors="ignore")
                aa_map = parse_aa(html, verbose=verbose)
                print(f"  offline AA: {len(aa_map)} entries ({snap_aa.name})")
            except Exception as e:
                print(f"  WARN offline AA parse: {e}", file=sys.stderr)

    # ---- 4. Fetch LMArena ----
    lm_map = {}
    if do_fetch:
        body = fetch(LMARENA_URL, verbose=verbose)
        if body:
            html = body.decode(errors="ignore")
            if do_write:
                snap = RAW / f"lmarena_{dt.date.today().isoformat().replace('-','')}.html"
                bc.atomic_write_text(snap, html)
                print(f"  saved LMArena -> {snap.relative_to(ROOT)} ({len(html)} bytes)")
            lm_map = parse_lmarena(html, verbose=verbose)
        else:
            print("  WARN LMArena fetch failed", file=sys.stderr)
    if not lm_map:
        snap_lm = pick_latest_raw("lmarena")
        if snap_lm:
            try:
                html = snap_lm.read_text(errors="ignore")
                lm_map = parse_lmarena(html, verbose=verbose)
                print(f"  offline LMArena: {len(lm_map)} entries ({snap_lm.name})")
            except Exception as e:
                print(f"  WARN offline LMArena parse: {e}", file=sys.stderr)

    # ---- 4b. LiveBench snapshots: newest CSV is primary; older files only fill
    # keys missing from it (S1-C3) — a corrupt snapshot is a logged skip, not a pass.
    live_map = {}
    csv_matches = [p for p in sorted(glob.glob(str(RAW / "*livebench*20*.csv"))) if "cost" not in p]
    for p_csv in reversed(csv_matches):
        try:
            p = pathlib.Path(p_csv)
            date_part = "".join(filter(str.isdigit, p.stem))
            cat_p = RAW / f"livebench_categories_{date_part}.json"
            cat_json = cat_p.read_text(encoding="utf-8", errors="ignore") if cat_p.exists() else None
            data = parse_livebench(p.read_text(encoding="utf-8", errors="ignore"), categories_json=cat_json)
            filled = sum(1 for k in data if k not in live_map)
            for k, v in data.items():
                live_map.setdefault(k, v)
            if verbose:
                print(f"  LiveBench {p.name}: {len(data)} rows, {filled} new keys")
        except Exception as e:  # noqa: BLE001 — never swallow silently (S1-C3)
            print(f"  WARN LiveBench snapshot skipped ({p_csv}): {e}", file=sys.stderr)
    if live_map:
        print(f"  offline LiveBench: {len(live_map)} models loaded")

    # ---- 4c. Fetch current usage (authenticated) ----
    usage_raw = None
    usage_err = None
    usage_percents = {}  # window -> percent used (0-100)
    usage_resets = {}
    usage_key_present = False
    if do_fetch:
        k = get_api_key()
        usage_key_present = bool(k)
        if k:
            usage_raw, usage_err = fetch_usage(k, verbose=verbose)
            if usage_raw and isinstance(usage_raw, dict):
                for w in ("rolling", "weekly", "monthly"):
                    ww = usage_raw.get(w)
                    if isinstance(ww, dict):
                        try:
                            pct = float(ww.get("percent", ww.get("usedPercent", ww.get("used", 0))))
                        except Exception:
                            pct = None
                        if pct is not None:
                            usage_percents[w] = pct
                        if "resetsAt" in ww:
                            usage_resets[w] = ww["resetsAt"]
                        elif "resetAt" in ww:
                            usage_resets[w] = ww["resetAt"]
                if usage_percents:
                    print(f"  usage: {', '.join(f'{w} {usage_percents[w]:.0f}% used' for w in usage_percents)}")
                elif usage_raw:
                    print(f"  usage: got data but no rolling/weekly/monthly percent — keys={list(usage_raw.keys())[:8]}", file=sys.stderr)
                    if verbose:
                        print(f"    raw={str(usage_raw)[:600]}", file=sys.stderr)
            elif usage_err:
                print(f"  usage: {usage_err} — remaining % will be N/A (use $OPENCODE_API_KEY)", file=sys.stderr)
        else:
            if verbose:
                print("  usage: no key ($OPENCODE_API_KEY / auth.json opencode entry) — remaining % N/A")
    else:
        if verbose:
            print("  usage: offline — remaining % N/A")

    # most restrictive = max percent used
    usage_max_pct = max(usage_percents.values()) if usage_percents else None
    usage_remaining_pct = (100 - usage_max_pct) if usage_max_pct is not None else None

    # ---- 5. Build cost/benefit ----
    rows = []
    for mid in ocgo_api_ids:
        pr = merged_pricing.get(mid, {})
        inp = pr.get("input")
        outp = pr.get("output")
        cr = pr.get("cached_read")
        cw = pr.get("cached_write")
        usage = pr.get("usage")

        # For models where docs pricing is None (free) try OpenRouter pricing
        if inp is None and or_map:
            for or_id, or_rec in or_map.items():
                if norm_id(mid) in norm_id(or_id) or norm_id(or_id) in norm_id(mid):
                    prc = or_rec.get("pricing", {})
                    try:
                        p_prompt = float(prc.get("prompt", 0)) * 1_000_000
                        p_compl = float(prc.get("completion", 0)) * 1_000_000
                        if p_prompt > 0 or p_compl > 0:
                            inp = inp if inp is not None else p_prompt
                            outp = outp if outp is not None else p_compl
                            break
                    except Exception:
                        pass

        est_in, est_ca, est_out = merged_tokens.get(mid, (500, 60000, 200))
        # DeepSeek flash off-peak vs peak: we use off-peak as Go likely uses off-peak pricing?
        # Docs show both; we already picked off-peak via first table entry.

        cost_req = compute_cost(inp, outp, cr, est_in, est_ca, est_out)

        # Scaled caps
        if usage is not None:
            cap_mo = float(usage)
            cap_wk = cap_mo * 0.50
            cap_5h = cap_mo * 0.20
        else:
            cap_mo = cap_wk = cap_5h = None

        # Requests per window (computed)
        if cost_req and cost_req > 0 and usage is not None:
            req_5h = cap_5h / cost_req if cap_5h else None
            req_wk = cap_wk / cost_req if cap_wk else None
            req_mo = cap_mo / cost_req if cap_mo else None
        else:
            req_5h = req_wk = req_mo = None

        # Docs estimated requests (if parsed)
        docs_req = requests_live.get(mid, {})

        # Benchmarks
        aa_rec = find_aa_for_ocgo(mid, aa_map) if aa_map else None
        lm_rec = find_lm_for_ocgo(mid, lm_map) if lm_map else None
        or_oid, or_rec = find_or_for_ocgo(mid, or_map) if or_map else (None, None)
        live_rec = find_livebench_for_ocgo(mid, live_map) if live_map else None

        aa_int = _safe_float(aa_rec.get("intelligenceIndex")) if aa_rec else None
        aa_cod = _safe_float(aa_rec.get("codingIndex")) if aa_rec else None
        aa_age = _safe_float(aa_rec.get("agenticIndex")) if aa_rec else None
        aa_tps = _safe_float(aa_rec.get("medianOutputTokensPerSecond")) if aa_rec else None
        aa_ctx = _safe_int(aa_rec.get("contextWindowTokens")) if aa_rec else None
        aa_slug = str(aa_rec.get("slug") or "") if aa_rec and not str(aa_rec.get("slug", "")).startswith("$") else None

        lm_rank = _safe_int(lm_rec.get("rank")) if lm_rec else None
        lm_elo = _safe_float(lm_rec.get("elo")) if lm_rec else None
        lm_votes = _safe_int(lm_rec.get("votes")) if lm_rec else None

        or_ctx = None
        or_price_prompt = None
        if or_rec:
            or_ctx = or_rec.get("context_length")
            try:
                or_price_prompt = float(or_rec.get("pricing", {}).get("prompt", 0)) * 1_000_000
            except Exception:
                pass

        # Value metrics
        intel_per_dollar = (aa_int / cost_req) if (aa_int is not None and cost_req and cost_req > 0) else None
        cost_per_intel = (cost_req / aa_int) if (aa_int and cost_req) else None
        req_per_dollar = (1 / cost_req) if cost_req else None
        # Leverage: $60 of API usage for $10 sub = 6x, but scaled by usage/60
        # Effective: if you max out monthly cap, you get `usage` dollars of API for $10
        leverage = (usage / 10.0) if usage else None

        # Usage remaining (per-window) — from authenticated /zen/go/v1/usage if key present
        # usage_percents holds percent *used* per window (0-100). Remaining % = 100 - used.
        remaining = {}
        remaining_req = {}
        overall_remaining_pct = None
        if usage_percents and cost_req and cost_req > 0 and usage is not None:
            for w, cap in (("rolling", cap_5h), ("weekly", cap_wk), ("monthly", cap_mo)):
                pct_used = usage_percents.get(w)
                if pct_used is None or cap is None:
                    continue
                try:
                    pct_rem = max(0.0, 100.0 - float(pct_used))
                except Exception:
                    continue
                try:
                    remaining[w] = round(pct_rem, 1)
                except Exception:
                    continue
                try:
                    rem_usd = cap * pct_rem / 100.0
                    remaining_req[w] = _safe_int_round(rem_usd / cost_req)
                except Exception:
                    continue
            if remaining:
                try:
                    overall_remaining_pct = min(remaining.values())  # most restrictive window
                except Exception:
                    overall_remaining_pct = None
        elif usage_percents and usage is None:
            # free model: no cap, remaining is same % but no request count
            for w, pct_used in usage_percents.items():
                try:
                    remaining[w] = round(max(0.0, 100.0 - float(pct_used)), 1)
                except Exception:
                    continue
        elif usage_key_present and not usage_percents:
            # key present but fetch failed — leave empty, UI will show N/A + error
            pass

        rows.append({
            "model_id": mid,
            "display": mid,
            "pricing": {"input_per_1m": inp, "output_per_1m": outp, "cached_read_per_1m": cr, "cached_write_per_1m": cw, "monthly_usage_limit_usd": usage},
            "caps": {"cap_5h_usd": cap_5h, "cap_wk_usd": cap_wk, "cap_mo_usd": cap_mo},
            "tokens": {"est_input": est_in, "est_cached": est_ca, "est_output": est_out},
            "cost_per_request_usd": round(cost_req, 6) if cost_req is not None else None,
            "requests": {
                "per_5h_computed": _safe_int_round(req_5h),
                "per_week_computed": _safe_int_round(req_wk),
                "per_month_computed": _safe_int_round(req_mo),
                "per_5h_docs": docs_req.get("per_5h"),
                "per_week_docs": docs_req.get("per_week"),
                "per_month_docs": docs_req.get("per_month"),
            },
            "remaining": {
                "percent": remaining,  # per-window remaining %
                "requests": remaining_req,  # per-window remaining requests
                "overall_pct": overall_remaining_pct,  # min across windows
                "overall_req": min(remaining_req.values()) if remaining_req else None,
            },
            "benchmarks": {
                "aa_slug": aa_slug,
                "aa_intelligence": aa_int,
                "aa_coding": aa_cod,
                "aa_agentic": aa_age,
                "aa_median_tps": aa_tps,
                "aa_context": aa_ctx,
                "lmarena_rank": lm_rank,
                "lmarena_elo": lm_elo,
                "lmarena_votes": lm_votes,
                "livebench": live_rec,
                "openrouter_id": or_oid,
                "openrouter_context": or_ctx,
                "openrouter_prompt_per_1m": or_price_prompt,
            },
            "value": {
                "intelligence_per_dollar": round(intel_per_dollar, 2) if intel_per_dollar else None,
                "cost_per_intelligence_pt_usd": round(cost_per_intel, 6) if cost_per_intel else None,
                "requests_per_dollar": round(req_per_dollar, 1) if req_per_dollar else None,
                "leverage_vs_10usd_sub": round(leverage, 2) if leverage else None,
            },
        })

    # ---- 5b. Normalized Composite Capability & Agentic Indices (bcheck formulas) ----
    z_int = get_z_scores([r["benchmarks"]["aa_intelligence"] for r in rows])
    z_cod = get_z_scores([r["benchmarks"]["aa_coding"] for r in rows])
    z_age = get_z_scores([r["benchmarks"]["aa_agentic"] for r in rows])
    z_elo = get_z_scores([r["benchmarks"]["lmarena_elo"] for r in rows])
    z_live = get_z_scores([
        r["benchmarks"].get("livebench", {}).get("overall")
        if isinstance(r["benchmarks"].get("livebench"), dict)
        else None
        for r in rows
    ])

    for i, r in enumerate(rows):
        b = r["benchmarks"]
        v = r["value"]
        p = r["pricing"]

        coverage = []
        if b["aa_intelligence"] is not None:
            coverage.append("AA")
        if b["lmarena_elo"] is not None:
            coverage.append("LM")
        if b.get("livebench") and b["livebench"].get("overall") is not None:
            coverage.append("Live")
        if not coverage:
            coverage = ["—"]
        r["coverage"] = coverage

        # Weighted composite Z-score across available signals
        weights = []
        z_parts = []
        if b["aa_intelligence"] is not None:
            weights.append(0.30); z_parts.append(0.30 * z_int[i])
        if b["aa_coding"] is not None:
            weights.append(0.20); z_parts.append(0.20 * z_cod[i])
        if b["aa_agentic"] is not None:
            weights.append(0.15); z_parts.append(0.15 * z_age[i])
        if b["lmarena_elo"] is not None:
            weights.append(0.15); z_parts.append(0.15 * z_elo[i])
        if b.get("livebench") and b["livebench"].get("overall") is not None:
            weights.append(0.20); z_parts.append(0.20 * z_live[i])

        tot_w = sum(weights) or 1.0
        cz = sum(z_parts) / tot_w if weights else 0.0
        q_score = compute_capability_q(cz)
        b["composite_score"] = q_score
        b["capability_q"] = q_score

        # Task pass probability on non-trivial agentic task
        p_succ = compute_p_success(q_score)
        b["p_success"] = p_succ

        # Retry / debug token multiplier
        t_mult = compute_token_multiplier(p_succ)
        b["token_multiplier"] = t_mult

        # Effective costs
        pin = float(p.get("input_per_1m") or 0.0)
        pout = float(p.get("output_per_1m") or 0.0)
        blended_price = (0.80 * pin) + (0.20 * pout)
        b["blended_price"] = round(blended_price, 2)
        effective_blended_price = compute_effective_cost(blended_price, t_mult)
        b["effective_cost"] = effective_blended_price
        v["effective_blended_price"] = effective_blended_price

        c_req = r.get("cost_per_request_usd")
        eff_c_req = (c_req * t_mult) if c_req is not None else None
        v["effective_cost_per_request"] = round(eff_c_req, 6) if eff_c_req is not None else None

        req_5h_val = r["requests"].get("per_5h_docs") or r["requests"].get("per_5h_computed")
        eff_req_5h = _safe_int_round(req_5h_val / t_mult) if req_5h_val else None
        v["effective_requests_per_5h"] = eff_req_5h

        req_mo_val = r["requests"].get("per_month_docs") or r["requests"].get("per_month_computed")
        eff_req_mo = _safe_int_round(req_mo_val / t_mult) if req_mo_val else None
        v["effective_requests_per_month"] = eff_req_mo

        # Value indices
        avi = compute_avi(q_score, effective_blended_price)
        b["avi_score"] = avi
        v["avi_score"] = avi

        fgi = compute_fgi(q_score, p_succ)
        b["fgi_score"] = fgi
        v["fgi_score"] = fgi

        speed = _safe_float(b.get("aa_median_tps"), default=60.0) or 60.0
        bfi = compute_bfi(q_score, speed, blended_price)
        b["bfi_score"] = bfi
        v["bfi_score"] = bfi

    # Sort by chosen sort mode (default: avi)
    sort_mode = getattr(args, "sort", "avi")
    def _eff_cost(r):
        # S2-M1 class guard (parity with bc.compute_pareto_frontier._row_cost):
        # 0.0 is a REAL cost — free tiers dominate the frontier/sort; only
        # None falls through, and 999 is for fully-unknown cost only.
        v = r["value"].get("effective_cost_per_request")
        if v is None:
            v = r.get("cost_per_request_usd")
        return 999.0 if v is None else float(v)

    if sort_mode == "fgi":
        sort_key_fn = lambda r: (-(r["value"]["fgi_score"] or -1), -(r["benchmarks"]["capability_q"] or -1), r["model_id"])
    elif sort_mode == "bfi":
        sort_key_fn = lambda r: (-(r["value"]["bfi_score"] or -1), -(r["benchmarks"]["capability_q"] or -1), r["model_id"])
    elif sort_mode == "cap":
        sort_key_fn = lambda r: (-(r["benchmarks"]["capability_q"] or -1), -(r["value"]["avi_score"] or -1), r["model_id"])
    elif sort_mode == "req5h":
        sort_key_fn = lambda r: (-(r["requests"].get("per_5h_docs") or r["requests"].get("per_5h_computed") or 0), -(r["value"]["avi_score"] or -1), r["model_id"])
    elif sort_mode == "cost":
        sort_key_fn = lambda r: (_eff_cost(r), -(r["benchmarks"]["capability_q"] or -1), r["model_id"])
    elif sort_mode == "intel":
        sort_key_fn = lambda r: (-(r["value"]["intelligence_per_dollar"] or -1), -(r["benchmarks"]["capability_q"] or -1), r["model_id"])
    else:  # "avi"
        sort_key_fn = lambda r: (-(r["value"]["avi_score"] or -1), -(r["benchmarks"]["capability_q"] or -1), r["model_id"])

    rows_sorted = sorted(rows, key=sort_key_fn)

    # Pareto frontier (effective cost vs capability) — docs-backed only, for bold highlighting
    dynamic_docs_ids = set(pricing_live.keys()) | DOCS_IDS | ({"ox-alpha-free"} if "ox-alpha-free" in ocgo_api_ids else set())
    pareto_ids = set()
    try:
        cand = [r for r in rows_sorted if r["model_id"] in dynamic_docs_ids]
        for a in cand:
            a_cost = _eff_cost(a)
            a_q = a["benchmarks"].get("capability_q", 0)
            candidates = [
                (_eff_cost(b), b["benchmarks"].get("capability_q", 0))
                for b in cand
                if b is not a
            ]
            if not bc.pareto_dominated(a_cost, a_q, candidates, cost_epsilon=0.0001):
                pareto_ids.add(a["model_id"])
    except Exception:
        pareto_ids = set()

    # Load previous baseline snapshot for catalog diffing (additions in green, removals in red)
    prev_snapshot = load_previous_snapshot(DATA / "ocgo_live.json")

    # Run diff on full rows_sorted to populate first_seen across all model records
    diff_model_catalog(rows_sorted, prev_snapshot)

    # ---- 6. Console report ----
    # Docs-backed and live pricing models
    docs_rows = [r for r in rows_sorted if r["model_id"] in dynamic_docs_ids]
    for r in docs_rows:
        r["is_docs_model"] = True

    catalog_diff = diff_model_catalog(docs_rows, prev_snapshot)
    added_ids = catalog_diff["added_ids"]
    removed_ids = catalog_diff["removed_ids"]
    removed_models = catalog_diff["removed_models"]

    use_color = not (getattr(args, "plain", False) or os.getenv("NO_COLOR"))
    slim_opt = True if getattr(args, "slim", False) else (False if getattr(args, "wide", False) else None)
    if getattr(args, "limits", False):
        print("\n" + render_limits_table(
            docs_rows,
            usage_raw=usage_raw,
            usage_percents=usage_percents,
            usage_resets=usage_resets,
            usage_err=usage_err,
            usage_key_present=usage_key_present,
            color=use_color,
            slim=slim_opt,
            wide=getattr(args, "wide", False),
        ))
    else:
        print("\n" + render_cli_table(
            docs_rows,
            usage_percents=usage_percents,
            usage_err=usage_err,
            usage_key_present=usage_key_present,
            pareto_ids=pareto_ids,
            added_ids=added_ids,
            removed_models=removed_models,
            color=use_color,
            slim=slim_opt,
            wide=getattr(args, "wide", False),
        ))

    # Write outputs
    if do_write:
        # data/ocgo_live.json
        role_recs_export = compute_role_recommendations(docs_rows, context="ocheck")
        live = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sources": {
                "opencode_docs": OCGO_DOCS,
                "opencode_api": OCGO_API,
                "openrouter_api": OPENROUTER_API,
                "artificial_analysis": AA_URL,
                "lmarena": LMARENA_URL,
                "usage_limits": "https://opencode.ai/docs/go/#usage-limits",
                "account_caps": {"cap_5h": ACC_5H, "cap_week": ACC_WK, "cap_month": ACC_MO},
                "note": "per-model caps = account_cap * usage/60; per-model Usage from docs pricing table"
            },
            "catalog_diff": {
                "added": sorted(list(added_ids)),
                "removed": sorted(list(removed_ids)),
                "total_current": len(docs_rows),
                # S1-M1: compare like with like — total_previous counted the FULL
                # baseline (incl. non-docs rows) against the docs-only current set.
                "total_previous": (len([m for m in prev_snapshot.get("models", []) if isinstance(m, dict) and m.get("is_docs_model")]) if (prev_snapshot and "models" in prev_snapshot) else len(docs_rows)),
            },
            "role_recommendations": role_recs_export,
            "models": rows_sorted,
        }
        DATA.mkdir(parents=True, exist_ok=True)
        out_json = DATA / "ocgo_live.json"
        bc.atomic_write_text(out_json, json.dumps(live, indent=2))
        if verbose:
            print(f"wrote {out_json.relative_to(ROOT)} ({len(json.dumps(live))} bytes)")

        # outputs json
        OUT.mkdir(parents=True, exist_ok=True)
        cb_json = OUT / "ocgo_cost_benefit.json"
        bc.atomic_write_text(cb_json, json.dumps(rows_sorted, indent=2))
        if verbose:
            print(f"wrote {cb_json.relative_to(ROOT)}")

        # HTML — with one-sentence current work in footer next to path
        work = one_sentence_work(docs_rows, usage_percents)
        html_path = OUT / "ocgo_cost_benefit.html"
        bc.atomic_write_text(html_path, render_html(docs_rows, work_sentence=work, pareto_ids=pareto_ids, added_ids=added_ids, removed_models=removed_models, data_note=data_label))
        if verbose:
            print(f"wrote {html_path.relative_to(ROOT)} ({html_path.stat().st_size} bytes)")
    else:
        print("\n(check-only, no files written)")


def render_html(rows, work_sentence=None, usage_percents=None, pareto_ids=None, added_ids=None, removed_models=None, data_note=None):
    if work_sentence is None:
        try:
            work_sentence = one_sentence_work(rows, usage_percents)
        except Exception:
            work_sentence = ""
    if pareto_ids is None:
        pareto_ids = set()
    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []
    if data_note is None:
        data_note = "Live check"

    title = f"OpenCode Go — Cost/Benefit ({dt.date.today().isoformat()})"
    role_recs = compute_role_recommendations(rows, context="ocheck")
    role_recs_html = render_role_recommendations_html(role_recs) if role_recs else ""
    # Build table rows
    trs = []
    for r in rows:
        is_added = r["model_id"] in added_ids
        raw_mid = html_lib.escape(r["model_id"])
        mid = f'{raw_mid}<span class="badge badge-new">+NEW</span>' if is_added else raw_mid
        usage = r["pricing"]["monthly_usage_limit_usd"]
        usage_s = f"${usage:.0f}" if usage is not None else "—"
        c = r["cost_per_request_usd"]
        c_s = f"${c:.5f}" if isinstance(c, float) else "—"
        reqs = r.get("requests", {})
        req5 = reqs.get("per_5h_docs") if reqs.get("per_5h_docs") is not None else reqs.get("per_5h_computed")
        reqw = reqs.get("per_week_docs") if reqs.get("per_week_docs") is not None else reqs.get("per_week_computed")
        reqm = reqs.get("per_month_docs") if reqs.get("per_month_docs") is not None else reqs.get("per_month_computed")
        req5_s = f"{req5:,}" if isinstance(req5, int) else "—"
        reqw_s = f"{reqw:,}" if isinstance(reqw, int) else "—"
        reqm_s = f"{reqm:,}" if isinstance(reqm, int) else "—"

        q_val = r["benchmarks"].get("capability_q")
        q_s = f"{q_val:.1f}" if isinstance(q_val, (int, float)) else "—"
        p_val = r["benchmarks"].get("p_success")
        p_s = f"{p_val:.1f}%" if isinstance(p_val, (int, float)) else "—"
        eff_c = r["value"].get("effective_cost_per_request")
        eff_c_s = f"${eff_c:.5f}" if isinstance(eff_c, float) else "—"
        avi_val = r["value"].get("avi_score")
        avi_s = f"{avi_val:.1f}" if isinstance(avi_val, (int, float)) else "—"
        fgi_val = r.get("value", {}).get("fgi_score")
        fgi_s = f"{fgi_val:.1f}" if isinstance(fgi_val, (int, float)) else "—"
        b_bm = r.get("benchmarks", {})
        b_val = r.get("value", {})
        aa_int = b_bm.get("aa_intelligence")
        aa_int_s = f"{aa_int:.1f}" if isinstance(aa_int, (int, float)) else "—"
        aa_cod = b_bm.get("aa_coding")
        aa_cod_s = f"{aa_cod:.1f}" if isinstance(aa_cod, (int, float)) else "—"
        aa_age = b_bm.get("aa_agentic")
        aa_age_s = f"{aa_age:.1f}" if isinstance(aa_age, (int, float)) else "—"
        lm_r = b_bm.get("lmarena_rank")
        lm_s = f"#{lm_r}" if isinstance(lm_r, int) else "—"
        elo = b_bm.get("lmarena_elo")
        elo_s = f"{elo:.0f}" if isinstance(elo, (int, float)) else "—"
        ipd = b_val.get("intelligence_per_dollar")
        ipd_s = f"{ipd:.0f}" if isinstance(ipd, (int, float)) else "—"
        cpi = b_val.get("cost_per_intelligence_pt_usd")
        cpi_s = f"${cpi:.5f}" if isinstance(cpi, float) else "—"
        lev = b_val.get("leverage_vs_10usd_sub")
        lev_s = f"{lev:.1f}×" if isinstance(lev, (int, float)) else "—"
        aa_slug = html_lib.escape(b_bm.get("aa_slug") or "")
        # Remaining % visual
        rem = r.get("remaining", {})
        overall = rem.get("overall_pct")
        overall_req = rem.get("overall_req")
        if overall is not None:
            col, weight = _pct_color(overall, for_html=True)
            try:
                pct = max(0, min(100, float(overall)))
            except Exception:
                pct = 0
            bar = f'<div style="background:var(--line);border-radius:4px;height:6px;width:60px;display:inline-block;vertical-align:middle;margin-left:6px"><div style="background:{col};height:6px;width:{pct:.0f}%;border-radius:4px"></div></div>'
            if overall_req is not None:
                rem_html = f'<span style="color:{col};{weight}">{overall:.0f}%</span><span class="mid">{overall_req:,} req</span>{bar}'
            else:
                rem_html = f'<span style="color:{col};{weight}">{overall:.0f}%</span>{bar}'
        else:
            # no key / error / free
            if r["pricing"]["monthly_usage_limit_usd"] is None:
                rem_html = '<span class="mid">free</span>'
            else:
                rem_html = '<span class="mid">N/A*</span>'
        # Highlight — added / pareto
        cls = ""
        if is_added:
            cls = "added"
        elif r["model_id"] in pareto_ids:
            cls = "pareto"
        elif aa_int and aa_int >= 58:
            cls = "flagship"
        elif r["pricing"]["monthly_usage_limit_usd"] == 60 and ipd and ipd > 800:
            cls = "value"
        elif r["pricing"]["monthly_usage_limit_usd"] is None:
            cls = "free"

        trs.append(
            f'<tr class="{cls}">'
            f'<td class="m">{mid}</td>'
            f'<td class="n">{usage_s}</td>'
            f'<td class="n">{c_s}</td>'
            f'<td class="n">{req5_s}</td><td class="n">{reqw_s}</td><td class="n">{reqm_s}</td>'
            f'<td class="n" style="font-weight:700; color:#2563eb;">{q_s}</td>'
            f'<td class="n">{p_s}</td>'
            f'<td class="n">{eff_c_s}</td>'
            f'<td class="n" style="font-weight:700; color:#10b981;">{avi_s}</td>'
            f'<td class="n" style="font-weight:700; color:#8b5cf6;">{fgi_s}</td>'
            f'<td class="n">{aa_int_s}<span class="mid">{aa_slug}</span></td>'
            f'<td class="n">{aa_cod_s}</td>'
            f'<td class="n">{lm_s}<span class="mid">{elo_s}</span></td>'
            f'<td class="n">{ipd_s}</td><td class="n">{cpi_s}</td><td class="n">{lev_s}</td>'
            f'<td class="n">{rem_html}</td>'
            f'</tr>'
        )

    removed_html = ""
    if removed_models:
        rem_tags = []
        for rm in removed_models:
            rm_id = html_lib.escape(rm.get("model_id", "unknown"))
            pr_lim = rm.get("pricing", {}).get("monthly_usage_limit_usd")
            lim_s = f"${pr_lim:.0f}/mo" if pr_lim is not None else "Free"
            fgi = rm.get("value", {}).get("fgi_score") or rm.get("benchmarks", {}).get("fgi_score")
            fgi_s = f"FGI {fgi:.1f}" if isinstance(fgi, (int, float)) else "FGI —"
            avi = rm.get("value", {}).get("avi_score") or rm.get("benchmarks", {}).get("avi_score")
            avi_s = f"AVI {avi:.1f}" if isinstance(avi, (int, float)) else "AVI —"
            rem_tags.append(f'<span class="removed-tag">❌ <b>{rm_id}</b> <span class="mid">(Prior: {lim_s}, {fgi_s}, {avi_s})</span></span>')

        removed_html = f"""
<div class="removed-section">
  <div class="removed-title">🔻 Removed / Deprecated Models ({len(removed_models)})</div>
  <div class="sub" style="margin-bottom:8px;">These models were present in the previous catalog snapshot but are no longer active in the current OpenCode Go docs or API:</div>
  <div>{''.join(rem_tags)}</div>
</div>
"""
    body = f"""
<h1>{html_lib.escape(title)}</h1>
<p class="sub">{html_lib.escape(data_note)} — OpenCode Go subscription <code>$5 first month, then $10/mo</code> ·Limits: <b>$12/5h · $30/wk · $60/mo</b> pooled, scaled by per-model Usage/60 · <a href="https://opencode.ai/docs/go/#usage-limits" style="color:#58a6ff">docs</a> · Generated {dt.datetime.now(dt.timezone.utc).isoformat()}</p>

<div class="card"><b>How to read:</b> <span style="color:#d29922">■ pareto</span> cost/intelligence frontier · <span style="color:#3fb950">■ flagship</span> intelligence ≥58 · <span style="color:#58a6ff">■ value</span> $60-usage + high int/$ · <b>Q(Cap)</b> = Composite Capability (0-100) · <b>P(Succ)</b> = 1-turn pass rate · <b>Eff c/r</b> = Cost per solved task · <b>AVI (ROI)</b> = Agentic Value Index · <b>FGI (Gate)</b> = Frontier Gate Index · <b>lev</b> = monthly leverage vs $10 sub (<code>usage/10</code>).</div>

<div class="card">
<table id="tbl">
<thead><tr>
<th>model</th><th>$Usage/mo</th><th>$c/req</th><th>req/5h</th><th>req/wk</th><th>req/mo</th><th>Q(Cap)</th><th>P(Succ)</th><th>Eff c/r</th><th>AVI (ROI)</th><th>FGI (Gate)</th><th>AA intel</th><th>AA cod</th><th>LMArena</th><th>int/$</th><th>$c/int</th><th>lev</th><th>remain</th>
</tr></thead>
<tbody>
{''.join(trs)}
</tbody>
</table>
<div class="legend">Click headers to sort. “—” = not benchmarked / free. AA Intelligence/Coding/Agentic from artificialanalysis.ai leaderboard; Arena rank/ELO from arena.ai text leaderboard; pricing from opencode.ai/docs/go. Cross-source scores incomparable.</div>
</div>

{removed_html}

{role_recs_html}

<div class="call"><b>Takeaway:</b> Cheapest per-request (MiMo-V2.5, Muse Spark, Hy3, DeepSeek Flash) buy the most requests from the pooled cap — ideal for high-volume use. Flagship intelligence (Kimi K3, GLM-5.3, Qwen3.8-Max, Grok 4.5, GPT-5.6-Luna) cost more per request but score higher. Best “intelligence per dollar” usually sits in the middle (DeepSeek Flash, Qwen3.7-Plus, GLM-5.2, MiniMax M3). Use the <code>int/$</code> column to pick your tier.</div>

<p class="note">Full JSON: <a href="ocgo_cost_benefit.json" style="color:#58a6ff">ocgo_cost_benefit.json</a> · Raw snapshots in <code>data/raw/</code> when run with <code>--fetch</code>. Stdlib only, no API keys. Re-run: <code>python3 checkers/opencode_cost_benefit_analyzer.py</code>.</p>
<div class="footer"><span class="path">path: outputs/ocgo_cost_benefit.html</span><span class="work">{html_lib.escape(work_sentence)}</span></div>
"""
    return f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html_lib.escape(title)}</title><style>{bc.HTML_CSS_COMMON}</style></head><body><div class=\"wrap\">{body}</div>{bc.HTML_SORT_SCRIPT}</body></html>\n"


def one_sentence_work(rows, usage_percents=None):
    try:
        n = len(rows)
        have_int = sum(1 for r in rows if r["benchmarks"]["aa_intelligence"] is not None)
        # best value among $60 usage
        best = None
        for r in sorted(rows, key=lambda x: -(x["value"]["intelligence_per_dollar"] or -1)):
            if r["pricing"]["monthly_usage_limit_usd"] == 60 and r["value"]["intelligence_per_dollar"]:
                best = r["model_id"]
                break
        # flagship
        flagship = None
        for r in rows:
            if r["benchmarks"]["aa_intelligence"] and r["benchmarks"]["aa_intelligence"] >= 59:
                flagship = r["model_id"]
                break
        rem = "" 
        if usage_percents:
            mx = max(usage_percents.values())
            rem = f", {100-mx:.0f}% quota remaining"
        if best and flagship:
            return f"Current work: live cost/benefit of {n} Go models ({have_int} ranked) — best value {best}, flagship {flagship}{rem}."
        if best:
            return f"Current work: live check of {n} Go models ({have_int} ranked) — best value {best}{rem}."
        return f"Current work: live check of {n} Go models ({have_int} ranked){rem}."
    except Exception:
        return f"Current work: live check of {len(rows)} Go models."


if __name__ == "__main__":
    main()
