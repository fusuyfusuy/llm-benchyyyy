#!/usr/bin/env python3
"""
cc_check.py — Command Code GOAT catalog checker

Checks the Command Code GOAT plan catalog (https://commandcode.ai/docs/plans/goat)
against benchmarks from Artificial Analysis / LMArena / LiveBench / OpenRouter, and
produces a cost/benefit analysis against the GOAT usage limits
($14/5h, $35/wk, $70/mo — https://commandcode.ai/docs/plans/goat#usage-limits).
Monthly credits per model vary ($20–$70 visible on the pricing tables).

Offline by default (rule 7): reads dated snapshots from docs/data/raw/;
--fetch is the only network path. No auth, stdlib only.

NOTE: This module deliberately mirrors opencode_cost_benefit_analyzer.py's
layout and divergences from benchmark_common: _safe_float/_safe_int etc. are
redefined locally (stricter "$" rejection). Do not "restore" bc imports.
--fetch writes docs/data/raw/cc_goat_docs_YYYYMMDD.html (not opencode_go_docs).
Like ocheck, --json/--html are accepted but all outputs are always written
unless --check (documented contract drift vs bcheck/fcheck).
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
    compute_effective_cost, compute_avi, compute_fgi, compute_bfi, compute_qvi,
    parse_lmarena,
    compute_role_recommendations, render_role_recommendations_cli,
    render_role_recommendations_html,
    load_previous_snapshot, diff_model_catalog, render_removed_models_cli,
)

CC_DOCS = "https://commandcode.ai/docs/plans/goat"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
LMARENA_URL = "https://arena.ai/leaderboard/code/webdev"
ARENA_URL = "https://arena.ai/leaderboard/code/webdev"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

FALLBACK_PRICING = {
    "tencent-hy4-preview": {"input": 0.834, "output": 2.501, "cached_read": 0.042, "cached_write": None, "credits": 20.0},
    "glm-5.3-flash": {"input": 0.15, "output": 0.5, "cached_read": 0.03, "cached_write": None, "credits": 40.0},
    "qwen-3.8-flash": {"input": 0.16, "output": 0.47, "cached_read": 0.016, "cached_write": None, "credits": 20.0},
    "deepseek-v4-flash-fast": {"input": 0.28, "output": 0.56, "cached_read": 0.07, "cached_write": None, "credits": 20.0},
    "deepseek-v4-flash-vision": {"input": 0.22, "output": 0.66, "cached_read": 0.007, "cached_write": None, "credits": 20.0},
    "glm-5.3": {"input": 1.4, "output": 4.4, "cached_read": 0.26, "cached_write": None, "credits": 20.0},
    "qwen-3.8-27b": {"input": 0.4, "output": 3.0, "cached_read": 0.04, "cached_write": None, "credits": 70.0},
    "deepseek-v4-pro": {"input": 0.66, "output": 1.98, "cached_read": 0.022, "cached_write": None, "credits": 20.0},
    "gemini-3.7-flash": {"input": 1.5, "output": 7.5, "cached_read": 0.15, "cached_write": 0.08334, "credits": 40.0},
    "grok-4.6": {"input": 2.0, "output": 6.0, "cached_read": 0.5, "cached_write": None, "credits": 20.0},
    "muse-spark-1.2": {"input": 1.25, "output": 4.25, "cached_read": 0.15, "cached_write": None, "credits": 20.0},
    "muse-spark-1.2-contributor": {"input": 0.1, "output": 0.2, "cached_read": 0.002, "cached_write": None, "credits": 20.0},
    "qwen-3.8-max": {"input": 2.0, "output": 6.0, "cached_read": 0.25, "cached_write": 2.5, "credits": 20.0},
    "deepseek-v4-flash": {"input": 0.22, "output": 0.66, "cached_read": 0.007, "cached_write": None, "credits": 60.0},
    "inkling-small": {"input": 0.5, "output": 1.2, "cached_read": 0.1, "cached_write": None, "credits": 20.0},
    "qwen-3.7-flash": {"input": 0.03, "output": 0.13, "cached_read": 0.006, "cached_write": 0.038, "credits": 20.0},
    "laguna-s-2.1-free": {"input": None, "output": None, "cached_read": None, "cached_write": None, "credits": None},
    "inkling": {"input": 1.0, "output": 4.05, "cached_read": 0.17, "cached_write": None, "credits": 20.0},
    "kimi-k3": {"input": 3.0, "output": 15.0, "cached_read": 0.3, "cached_write": None, "credits": 20.0},
    "gpt-5.6-luna": {"input": 0.2, "output": 1.2, "cached_read": 0.02, "cached_write": 0.25, "credits": 20.0},
    "gpt-5.6-sol": {"input": 5.0, "output": 30.0, "cached_read": 0.5, "cached_write": 6.25, "credits": 70.0},
    "grok-4.5": {"input": 2.0, "output": 6.0, "cached_read": 0.5, "cached_write": None, "credits": 20.0},
    "tencent-hy3": {"input": 0.14, "output": 0.58, "cached_read": 0.035, "cached_write": None, "credits": 70.0},
    "glm-5.2-fast": {"input": 3.0, "output": 10.25, "cached_read": 0.5, "cached_write": None, "credits": 20.0},
    "glm-5.2": {"input": 1.4, "output": 4.4, "cached_read": 0.26, "cached_write": None, "credits": 70.0},
    "kimi-k2.7-code-highspeed": {"input": 1.9, "output": 8.0, "cached_read": 0.38, "cached_write": None, "credits": 20.0},
    "kimi-k2.7-code": {"input": 0.95, "output": 4.0, "cached_read": 0.19, "cached_write": None, "credits": 60.0},
    "nemotron-3-ultra": {"input": 0.6, "output": 2.4, "cached_read": 0.12, "cached_write": None, "credits": 20.0},
    "minimax-m3": {"input": 0.3, "output": 1.2, "cached_read": 0.06, "cached_write": None, "credits": 47.0},
    "qwen-3.7-plus": {"input": 0.4, "output": 1.6, "cached_read": 0.08, "cached_write": 0.5, "credits": 33.0},
    "step-3.7-flash": {"input": 0.2, "output": 1.15, "cached_read": 0.04, "cached_write": None, "credits": 20.0},
    "mimo-v2.5": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "credits": 30.0},
    "mimo-v2.5-pro": {"input": 0.435, "output": 0.87, "cached_read": 0.0036, "cached_write": None, "credits": 20.0},
    "qwen-3.7-max": {"input": 2.5, "output": 7.5, "cached_read": 0.5, "cached_write": 3.13, "credits": 33.0},
    "step-3.5-flash": {"input": 0.1, "output": 0.3, "cached_read": 0.02, "cached_write": None, "credits": 20.0},
    "glm-5.1": {"input": 1.4, "output": 4.4, "cached_read": 0.26, "cached_write": None, "credits": 20.0},
    "minimax-m2.7": {"input": 0.3, "output": 1.2, "cached_read": 0.06, "cached_write": None, "credits": 20.0},
    "qwen-3.6-max-preview": {"input": 1.3, "output": 7.8, "cached_read": 0.26, "cached_write": 1.63, "credits": 20.0},
    "qwen-3.6-plus": {"input": 0.5, "output": 3.0, "cached_read": 0.1, "cached_write": None, "credits": 33.0},
    "kimi-k2.6": {"input": 0.95, "output": 4.0, "cached_read": 0.16, "cached_write": None, "credits": 20.0},
    "glm-5": {"input": 1.0, "output": 3.2, "cached_read": 0.2, "cached_write": None, "credits": 20.0},
    "kimi-k2.5": {"input": 0.6, "output": 3.0, "cached_read": 0.1, "cached_write": None, "credits": 20.0},
    "minimax-m2.5": {"input": 0.3, "output": 1.2, "cached_read": 0.03, "cached_write": None, "credits": 20.0},
}

DOCS_IDS = set(FALLBACK_PRICING.keys())

ACC_5H, ACC_WK, ACC_MO = 14.0, 35.0, 70.0

# Canonical id aliases: docs display names vary ("DeepSeek V4 Flash Vision (exp)" etc.)
_ID_ALIASES = {
    "deepseek-v4-flash-vision-exp": "deepseek-v4-flash-vision",
    "deepseek-v4-flash-vision-(exp)": "deepseek-v4-flash-vision",
    "tencent-hy4-preview": "tencent-hy4-preview",
    "glm-5.3-flash": "glm-5.3-flash",
    "qwen-3.8-flash": "qwen-3.8-flash",
    "deepseek-v4-flash-fast": "deepseek-v4-flash-fast",
    "kimi-k2.7-code-highspeed": "kimi-k2.7-code-highspeed",
    "kimi-k2-7-code-highspeed": "kimi-k2.7-code-highspeed",
    "muse-spark-1.2-contributor": "muse-spark-1.2-contributor",
    "laguna-s-2.1-free": "laguna-s-2.1-free",
    "laguna-s-2.1free": "laguna-s-2.1-free",
    "laguna-s-2.1": "laguna-s-2.1-free",
    "qwen-3.7-flash-(32k)": "qwen-3.7-flash",
    "qwen-3.7-flash-(256k)": "qwen-3.7-flash",
    "qwen-3.7-flash-(>256k)": "qwen-3.7-flash",
}


def pick_latest_raw(name_part):
    return bc.pick_latest_raw(RAW, name_part)


def offline_data_note():
    labels = (("docs", "cc_goat_docs"), ("OpenRouter", "openrouter_models"), ("AA", "artificial_analysis"),
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


def fetch(url, timeout=20, verbose=False):
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


def _norm_cc_id(raw: str) -> str | None:
    raw = raw.strip()
    raw = re.sub(r"\([^)]*\)", "", raw).strip()
    raw = re.sub(r"\s*Off-peak.*", "", raw, flags=re.I).strip()
    raw = re.sub(r"\s*-\d+%\s*$", "", raw).strip()
    low = raw.lower().replace("_", "-")
    low = re.sub(r"\s+", "-", low)
    low = re.sub(r"-+", "-", low).strip("-")
    if not re.match(r"^[a-z0-9][a-z0-9\.\-]*$", low) or len(low) < 2:
        return None
    return _ID_ALIASES.get(low, low)


def parse_cc_docs(html, verbose=False):
    pricing = {}
    requests = {}
    tables = re.findall(r"<table.*?</table>", html, flags=re.S)
    if verbose:
        print(f"  docs: found {len(tables)} tables")

    def _table_with(header_phrase: str):
        for t in tables:
            m = re.search(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S)
            if not m:
                continue
            hdr = re.sub(r"<[^>]+>", " ", m.group(1)).lower()
            if header_phrase in hdr:
                return t
        return None

    req_tbl = _table_with("requests / 5 hour") or _table_with("requests per 5 hour")
    # Pricing catalog is the first table with Context + caps; credits tables have "monthly credits"
    catalog_tbl = None
    for t in tables:
        m = re.search(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S)
        if not m:
            continue
        hdr = re.sub(r"<[^>]+>", " ", m.group(1)).lower()
        if "context" in hdr and "caps" in hdr:
            catalog_tbl = t
            break
    credits_tbls = []
    for t in tables:
        m = re.search(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S)
        if not m:
            continue
        hdr = re.sub(r"<[^>]+>", " ", m.group(1)).lower()
        if "monthly credits" in hdr:
            credits_tbls.append(t)

    def _eff_price(cell: str):
        nums = re.findall(r"\$([\d\.]+)", cell)
        if not nums:
            return None
        try:
            return float(nums[-1])
        except Exception:
            return None

    if catalog_tbl is not None:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", catalog_tbl, flags=re.S)
        for tr in rows[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
            if len(cells) < 8:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            clean = [" ".join(c.split()) for c in clean]
            model_raw = re.sub(r"\s*-\d+%\s*$", "", clean[0]).strip()
            mid = _norm_cc_id(model_raw)
            if not mid:
                continue
            if mid in pricing:
                continue
            # Free row
            if clean[4].lower() == "free":
                pricing[mid] = {"input": None, "output": None, "cached_read": None, "cached_write": None, "credits": None}
                continue
            pricing[mid] = {
                "input": _eff_price(clean[4]),
                "output": _eff_price(clean[5]),
                "cached_read": _eff_price(clean[6]),
                "cached_write": _eff_price(clean[7]) if clean[7] not in ("—", "-", "") else None,
                "credits": None,
            }

    # Credits from the two monthly-credits tables
    for ctbl in credits_tbls:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", ctbl, flags=re.S)
        for tr in rows[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
            if len(cells) < 6:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            clean = [" ".join(c.split()) for c in clean]
            model_raw = re.sub(r"\s*-\d+%\s*$", "", clean[0]).strip()
            mid = _norm_cc_id(model_raw)
            if not mid:
                continue
            cred_raw = clean[5].replace("$", "").replace(",", "").strip()
            try:
                cred = float(cred_raw) if cred_raw not in ("—", "-", "") else None
            except Exception:
                cred = None
            if mid in pricing:
                pricing[mid]["credits"] = cred
            else:
                pricing[mid] = {"input": _eff_price(clean[1]), "output": _eff_price(clean[2]), "cached_read": _eff_price(clean[3]), "cached_write": _eff_price(clean[4]) if clean[4] not in ("—", "-", "") else None, "credits": cred}
    # Older models paragraph: "all at the standard $20 credits"
    if "Older models also available" in html:
        seg = html[html.find("Older models also available"):html.find("Older models also available")+600]
        seg_text = re.sub(r"<[^>]+>", " ", seg)
        for mname in ["Kimi K2.6", "Kimi K2.5", "GLM-5.1", "GLM-5", "Qwen 3.7 Flash", "Qwen 3.6 Max Preview", "MiniMax M2.7", "MiniMax M2.5"]:
            mid = _norm_cc_id(mname)
            if mid and mid in pricing and pricing[mid].get("credits") is None:
                pricing[mid]["credits"] = 20.0

    # requests table
    if req_tbl is not None:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", req_tbl, flags=re.S)
        for tr in rows[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
            if len(cells) < 4:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).replace(",", "").strip() for c in cells]
            clean = [" ".join(c.split()) for c in clean]
            model_raw = re.sub(r"\s*-\d+%\s*$", "", clean[0]).strip()
            mid = _norm_cc_id(model_raw)
            if not mid:
                continue
            try:
                r5 = int(clean[1]) if clean[1] not in ("-", "—", "") else None
                rw = int(clean[2]) if clean[2] not in ("-", "—", "") else None
                rm = int(clean[3]) if clean[3] not in ("-", "—", "") else None
            except Exception:
                continue
            requests[mid] = {"per_5h": r5, "per_week": rw, "per_month": rm}

    return pricing, requests


norm_id = bc.norm_id
parse_aa = bc.parse_aa
parse_openrouter = bc.parse_openrouter
find_aa_for_cc = bc.find_aa_for_model
find_lm_for_cc = bc.find_lm_for_model
find_or_for_cc = bc.find_or_for_model
parse_livebench = bc.parse_livebench
find_livebench_for_cc = bc.find_livebench_for_model


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


C_RESET = "\033[0m"

def display_len(s):
    clean = re.sub(r"\033\[[0-9;]*m", "", str(s))
    w = 0
    for ch in clean:
        if ord(ch) in (0x1F947, 0x1F948, 0x1F949, 0x1F3C6, 0x26A1) or (0x1F300 <= ord(ch) <= 0x1FAFF):
            w += 2
        else:
            w += 1
    return w


def color_cell(text, color="", width=None, align="<", bg=""):
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


def render_cli_table(models_list, pareto_ids=None, added_ids=None, removed_models=None, color=True, slim=None, wide=False):
    if pareto_ids is None:
        pareto_ids = set()
    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []
    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_slim = slim if slim is not None else (term_cols < 120 and not wide)
    out = []
    if is_slim:
        headers = [
            ("Rank", 4, "^"), ("Model", 20, "<"), ("Credits", 8, "^"), ("Req/5h", 6, ">"),
            ("Q(Cap)", 6, ">"), ("P(Succ)", 7, ">"), ("Eff c/r", 7, ">"), ("Val", 5, ">"), ("AVI", 5, ">"), ("FGI", 4, ">"),
        ]
    else:
        headers = [
            ("Rank", 4, "^"), ("Model", 22, "<"), ("Credits", 8, "^"), ("5h Cap", 7, ">"), ("Req/5h", 7, ">"),
            ("Q(Cap)", 6, ">"), ("P(Succ)", 7, ">"), ("Eff c/r", 7, ">"), ("Value", 5, ">"), ("AVI", 5, ">"), ("FGI", 4, ">"), ("Lev", 5, ">"),
        ]
    total_models = len(models_list)
    scored = [m for m in models_list if m["benchmarks"].get("capability_q") is not None]
    top_val = max(scored, key=lambda m: m["value"].get("qvi_score") or 0) if scored else None
    top_frontier = max(scored, key=lambda m: m["value"].get("fgi_score") or 0) if scored else None
    top_avi = max(scored, key=lambda m: m["value"].get("avi_score") or 0) if scored else None
    top_req = max(models_list, key=lambda m: (m["requests"].get("per_5h_docs") or m["requests"].get("per_5h_computed") or 0)) if models_list else None
    col_medals = bc.compute_column_medals(
        models_list,
        {
            "q": (lambda r: r["benchmarks"].get("capability_q") or 0, True, None),
            "psucc": (lambda r: r["benchmarks"].get("p_success") or 0, True, None),
            "value": (lambda r: r["value"].get("qvi_score") or r["value"].get("value_score") or 0, True, None),
            "avi": (lambda r: r["value"].get("avi_score") or 0, True, None),
            "fgi": (lambda r: r["value"].get("fgi_score") or 0, True, None),
        },
        id_key="model_id",
    )
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    title_str = "⚡ COMMAND CODE GOAT — COST/BENEFIT & AGENTIC RADAR (https://commandcode.ai/docs/plans/goat#usage-limits)"
    v_info = f"Top Val: {top_val['model_id'][:14]} (Val {top_val['value'].get('qvi_score', 0):.1f})" if top_val else ""
    f_info = f"Frontier: {top_frontier['model_id'][:14]} (FGI {top_frontier['value'].get('fgi_score', 0):.1f})" if top_frontier else ""
    top_req_cnt = top_req["requests"].get("per_5h_docs") or top_req["requests"].get("per_5h_computed") or 0 if top_req else 0
    s_info = f"Max Bulk: {top_req['model_id'][:12]} ({format_compact_num(top_req_cnt)}/5h)" if top_req else ""
    if is_slim:
        summary_str = f" Caps: $14/5h · $35/wk · $70/mo · credits $20–$70 │ {v_info} │ {f_info}"
    else:
        summary_str = f" Caps: $14/5h · $35/wk · $70/mo · credits $20–$70 │ {v_info} │ {f_info} │ {s_info}"
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
        title_str, summary_lines=[summary_str], diff_notices=diff_notices, inner_w=inner_w, color=color,
        plain_title_line=" COMMAND CODE GOAT — COST/BENEFIT & AGENTIC RADAR — Caps: $14/5h · $35/wk · $70/mo · credits $20-$70",
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
        credits = r["pricing"].get("monthly_credits")
        credits_str = f"${credits:.0f}" if credits is not None else "Free"
        cap_5h_val = r.get("caps", {}).get("cap_5h_usd")
        cap_5h_str = f"${cap_5h_val:.2f}" if cap_5h_val is not None else "—"
        reqs = r.get("requests", {})
        req5_val = reqs.get("per_5h_docs") if reqs.get("per_5h_docs") is not None else reqs.get("per_5h_computed")
        req5_str = format_compact_num(req5_val)
        meds = col_medals.get(r["model_id"], {})
        q_val = r["benchmarks"].get("capability_q")
        p_val = r["benchmarks"].get("p_success")
        eff_c_val = r["value"].get("effective_cost_per_request")
        eff_c_str = f"${eff_c_val:.4f}" if eff_c_val is not None else "—"
        qvi_val = r["value"].get("qvi_score") or r["value"].get("value_score")
        avi_val = r["value"].get("avi_score")
        fgi_val = r["value"].get("fgi_score")
        q_disp = f"{q_val:.1f}" + bc.medal_badge(meds.get("q"), color=color) if q_val is not None else "—"
        p_disp = f"{p_val:.1f}%" + bc.medal_badge(meds.get("psucc"), color=color) if p_val is not None else "—"
        qvi_disp = f"{qvi_val:.1f}" + bc.medal_badge(meds.get("value"), color=color) if qvi_val is not None else "—"
        avi_disp = f"{avi_val:.1f}" + bc.medal_badge(meds.get("avi"), color=color) if avi_val is not None else "—"
        fgi_disp = f"{fgi_val:.1f}" + bc.medal_badge(meds.get("fgi"), color=color) if fgi_val is not None else "—"
        lev_val = r["value"].get("leverage_vs_10usd_sub")
        lev_str = f"{lev_val:.1f}x" if lev_val else "—"
        if color:
            if credits is None:
                limit_color = C_GRAY
            elif credits >= 60:
                limit_color = C_GREEN
            elif credits >= 40:
                limit_color = C_CYAN
            elif credits >= 30:
                limit_color = C_YELLOW
            else:
                limit_color = C_WHITE
            if is_added:
                mid_color = C_BOLD + C_GREEN
            elif r["model_id"] in pareto_ids:
                mid_color = C_BOLD + C_GOLD
            else:
                mid_color = C_WHITE
            q_color = bc.score_color_q(q_val) if q_val is not None else C_DIM
            p_color = bc.score_color_p(p_val) if p_val is not None else C_DIM
            eff_color = bc.color_ladder(eff_c_val, [(lambda v: v < 0.002, C_GREEN), (lambda v: v < 0.01, C_CYAN), (lambda v: v < 0.03, C_YELLOW)], default_color=C_MAGENTA)
            qvi_color = bc.score_color_qvi(qvi_val) if qvi_val is not None else C_DIM
            avi_color = bc.score_color_avi(avi_val) if avi_val is not None else C_DIM
            fgi_color = bc.score_color_fgi(fgi_val) if fgi_val is not None else C_DIM
            row_cells = [
                color_cell(rank_str, C_BOLD + (C_GOLD if rank_num == 1 else (C_SILVER if rank_num == 2 else (C_BRONZE if rank_num == 3 else C_WHITE))), width=4, align="^", bg=bg),
                color_cell(mid_display, mid_color, width=m_name_w, align="<", bg=bg),
                color_cell(credits_str, limit_color, width=8, align="^", bg=bg),
            ]
            if not is_slim:
                row_cells.append(color_cell(cap_5h_str, C_WHITE, width=7, align=">", bg=bg))
            row_cells.extend([
                color_cell(req5_str, C_CYAN if (req5_val and req5_val >= 3000) else C_WHITE, width=7 if not is_slim else 6, align=">", bg=bg),
                color_cell(q_disp, q_color, width=6, align=">", bg=bg),
                color_cell(p_disp, p_color, width=7, align=">", bg=bg),
                color_cell(eff_c_str, eff_color, width=7, align=">", bg=bg),
                color_cell(qvi_disp, qvi_color, width=5, align=">", bg=bg),
                color_cell(avi_disp, avi_color, width=5, align=">", bg=bg),
                color_cell(fgi_disp, fgi_color, width=4, align=">", bg=bg),
            ])
            if not is_slim:
                row_cells.append(color_cell(lev_str, C_DIM, width=5, align=">", bg=bg))
            out.append(f"{bg}{C_DIM}│{C_RESET}" + f"{bg}{C_DIM}│{C_RESET}".join(row_cells) + f"{bg}{C_DIM}│{C_RESET}")
        else:
            row_items = [f"{rank_str:^4}", f"{mid_display:<{m_name_w}}", f"{credits_str:^8}"]
            if not is_slim:
                row_items.append(f"{cap_5h_str:>7}")
            row_items.extend([f"{req5_str:>{7 if not is_slim else 6}}", f"{q_disp:>6}", f"{p_disp:>7}", f"{eff_c_str:>7}", f"{qvi_disp:>5}", f"{avi_disp:>5}", f"{fgi_disp:>4}"])
            if not is_slim:
                row_items.append(f"{lev_str:>5}")
            out.append(" ".join(row_items))
    if color:
        out.append(f"{C_DIM}{bot_border}{C_RESET}")
    else:
        out.append("-" * (inner_w + 2))
    if removed_models:
        out.append("")
        out.extend(render_removed_models_cli(removed_models, color=color, is_slim=is_slim, id_key="model_id"))
    out.append("")
    out.extend(bc.render_metric_guide_cli(
        "Command Code GOAT — Usage Limits & Metric Guide",
        [
            ("Gold Bold", "Pareto Frontier (undefeated capability vs cost).", C_GOLD),
            ("Green (+)", "Newly added model vs previous baseline.", C_GREEN),
            ("Badges ¹²³", "🥇/🥈/🥉 leaders per column.", C_YELLOW),
            ("Quota", "Pooled $14/5h · $35/wk · $70/mo. Per-model 5h cap = $14 × (credits/70).", C_WHITE),
            ("$70 credits", "GPT-5.6 Sol, GLM-5.2, Tencent Hy3, Qwen 3.8 27B — max monthly headroom.", C_GREEN),
            ("$60 credits", "DeepSeek V4 Flash, Kimi K2.7 Code — daily driver.", C_CYAN),
            ("$20 credits", "New/discounted models — still 2× public pricing.", C_WHITE),
            ("Value (QVI)", "Delivered Task Utility = log10(N_eff + 1) × (Q/70)^2.4 × 100.", C_GREEN),
            ("Eff c/r", "Real cost per solved task = base cost/req × retry multiplier.", C_WHITE),
        ],
        color=color,
    ))
    role_recs = compute_role_recommendations(models_list, context="ccheck")
    if role_recs:
        out.append("")
        out.extend(render_role_recommendations_cli(role_recs, color=color, is_slim=is_slim, width=inner_w))
    return "\n".join(out)


def build_sort_key(sort_mode, eff_cost_fn):
    def _cq(r):
        return r["benchmarks"]["capability_q"] or -1
    def _avi(r):
        return r["value"]["avi_score"] or -1
    def _qvi(r):
        return r["value"].get("qvi_score") or r["value"].get("value_score") or -1

    if sort_mode in ("value", "qvi"):
        return lambda r: (-_qvi(r), -_cq(r), r["model_id"])
    if sort_mode == "fgi":
        return lambda r: (-(r["value"]["fgi_score"] or -1), -_cq(r), r["model_id"])
    if sort_mode == "bfi":
        return lambda r: (-(r["value"]["bfi_score"] or -1), -_cq(r), r["model_id"])
    if sort_mode == "cap":
        return lambda r: (-_cq(r), -_avi(r), r["model_id"])
    if sort_mode == "quality":
        # Raw AA intelligenceIndex (benchmark results), then capability_q composite;
        # uncovered models (aa_intelligence None) fall last.
        return lambda r: (-(r["benchmarks"].get("aa_intelligence") or -1), -_cq(r), r["model_id"])
    if sort_mode == "req5h":
        return lambda r: (-(r["requests"].get("per_5h_docs") or r["requests"].get("per_5h_computed") or 0), -_avi(r), r["model_id"])
    if sort_mode == "cost":
        return lambda r: (eff_cost_fn(r), -_cq(r), r["model_id"])
    if sort_mode == "intel":
        return lambda r: (-(r["value"]["intelligence_per_dollar"] or -1), -_cq(r), r["model_id"])
    if sort_mode == "avi":
        return lambda r: (-_avi(r), -_cq(r), r["model_id"])
    raise ValueError(f"unknown sort mode: {sort_mode}")


def main():
    ap = argparse.ArgumentParser(description="Command Code GOAT catalog checker — benchmarks + cost/benefit (offline cache by default; live only with --fetch)")
    ap.add_argument("--fetch", "--refresh", action="store_true", help="live-fetch GOAT docs + OpenRouter/AA/LMArena snapshots to docs/data/raw/")
    ap.add_argument("--check", action="store_true", help="print only: writes NOTHING (even with --fetch)")
    ap.add_argument("--podium", "--winners", action="store_true", help="Display top 3 winners podium (no-op, kept for parity)")
    ap.add_argument("--json", action="store_true", help="Accepted for parity; outputs always written unless --check")
    ap.add_argument("--html", action="store_true", help="Accepted for parity; HTML always written unless --check")
    ap.add_argument("--verbose", action="store_true", help="verbose logging")
    ap.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors")
    ap.add_argument("--slim", action="store_true", help="Force compact table layout")
    ap.add_argument("--wide", action="store_true", help="Force full table layout")
    ap.add_argument("--sort", choices=["value", "qvi", "avi", "fgi", "bfi", "cap", "quality", "req5h", "cost", "intel"], default="value", help="Sort order (default: value)")
    args = ap.parse_args()
    verbose = args.verbose
    do_fetch = bool(args.fetch)
    do_write = not args.check
    print("Command Code GOAT — catalog check")
    print(f"  date: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    print(f"  mode: {'fetch (network)' if do_fetch else 'OFFLINE (cache-only)'}" + (" · check: no writes" if args.check else ""))
    data_label = "live fetch"
    if not do_fetch:
        note, data_label = offline_data_note()
        print(note)

    pricing_live = {}
    requests_live = {}
    cc_ids = []

    if do_fetch:
        body = fetch(CC_DOCS, verbose=verbose)
        if body:
            html = body.decode(errors="ignore")
            if do_write:
                snap = RAW / f"cc_goat_docs_{dt.date.today().isoformat().replace('-','')}.html"
                bc.atomic_write_text(snap, html)
                print(f"  saved GOAT docs -> {snap.relative_to(ROOT)} ({len(html)} bytes)")
            pl, rl = parse_cc_docs(html, verbose=verbose)
            if pl:
                pricing_live = pl
                print(f"  docs pricing: {len(pl)} models")
            if rl:
                requests_live = rl
                print(f"  docs requests: {len(rl)} models")
        else:
            print("  WARN GOAT docs fetch failed, trying snapshot/fallback", file=sys.stderr)

        for url, tag in [(OPENROUTER_API, "openrouter_models"), (AA_URL, "artificial_analysis"), (LMARENA_URL, "lmarena")]:
            body = fetch(url, verbose=verbose)
            if body and do_write:
                snap = RAW / f"{tag}_{dt.date.today().isoformat().replace('-','')}.{'json' if tag=='openrouter_models' else 'html'}"
                bc.atomic_write_text(snap, body.decode(errors="ignore") if tag != "openrouter_models" else json.dumps(json.loads(body), indent=2))
                print(f"  saved {tag} -> {snap.relative_to(ROOT)}")

    if not pricing_live:
        snap_docs = pick_latest_raw("cc_goat_docs") or pick_latest_raw("cc_goat")
        # also accept the scratchpad file if present (dev)
        if snap_docs:
            try:
                html = snap_docs.read_text(errors="ignore")
                pl, rl = parse_cc_docs(html, verbose=verbose)
                if pl:
                    pricing_live = pl
                    print(f"  offline GOAT docs: {len(pl)} models ({snap_docs.name})")
                if rl:
                    requests_live = rl
            except Exception as e:
                print(f"  WARN offline GOAT docs parse: {e}", file=sys.stderr)

    if pricing_live:
        cc_ids = list(pricing_live.keys())
    if not cc_ids:
        cc_ids = list(FALLBACK_PRICING.keys())
        print(f"  using fallback catalog: {len(cc_ids)}")
    else:
        for k in FALLBACK_PRICING:
            if k not in cc_ids:
                cc_ids.append(k)

    merged_pricing = {}
    for mid in cc_ids:
        if mid in pricing_live:
            merged_pricing[mid] = pricing_live[mid]
        elif mid in FALLBACK_PRICING:
            merged_pricing[mid] = FALLBACK_PRICING[mid]
        else:
            merged_pricing[mid] = {"input": None, "output": None, "cached_read": None, "cached_write": None, "credits": 20.0}

    # Patch missing credits from fallback when docs left it None
    for mid, pr in list(merged_pricing.items()):
        if pr.get("credits") is None and mid in FALLBACK_PRICING and FALLBACK_PRICING[mid].get("credits") is not None:
            # free tier stays None
            if mid != "laguna-s-2.1-free":
                pr["credits"] = FALLBACK_PRICING[mid]["credits"]

    or_map = {}
    snap_or = pick_latest_raw("openrouter_models")
    if snap_or:
        try:
            j = json.loads(snap_or.read_text(errors="ignore"))
            or_map = bc.parse_openrouter(j, verbose=verbose)
            print(f"  OpenRouter: {len(or_map)} models ({snap_or.name})")
        except Exception as e:
            print(f"  WARN OpenRouter parse: {e}", file=sys.stderr)

    aa_map = {}
    snap_aa = pick_latest_raw("artificial_analysis")
    if snap_aa:
        try:
            aa_map = bc.parse_aa(snap_aa.read_text(errors="ignore"), verbose=verbose)
            print(f"  AA: {len(aa_map)} entries ({snap_aa.name})")
        except Exception as e:
            print(f"  WARN AA parse: {e}", file=sys.stderr)

    lm_map = {}
    snap_lm = pick_latest_raw("lmarena")
    if snap_lm:
        try:
            lm_map = bc.parse_lmarena(snap_lm.read_text(errors="ignore"), verbose=verbose)
            print(f"  LMArena: {len(lm_map)} entries ({snap_lm.name})")
        except Exception as e:
            print(f"  WARN LMArena parse: {e}", file=sys.stderr)

    live_map = {}
    csv_matches = [p for p in sorted(glob.glob(str(RAW / "*livebench*20*.csv"))) if "cost" not in p]
    for p_csv in reversed(csv_matches):
        try:
            p = pathlib.Path(p_csv)
            date_part = "".join(filter(str.isdigit, p.stem))
            cat_p = RAW / f"livebench_categories_{date_part}.json"
            cat_json = cat_p.read_text(encoding="utf-8", errors="ignore") if cat_p.exists() else None
            data = bc.parse_livebench(p.read_text(encoding="utf-8", errors="ignore"), categories_json=cat_json)
            filled = sum(1 for k in data if k not in live_map)
            for k, v in data.items():
                live_map.setdefault(k, v)
            if verbose:
                print(f"  LiveBench {p.name}: {len(data)} rows, {filled} new keys")
        except Exception as e:
            print(f"  WARN LiveBench skipped ({p_csv}): {e}", file=sys.stderr)
    if live_map:
        print(f"  LiveBench: {len(live_map)} models loaded")

    EST_INPUT, EST_CACHED, EST_OUTPUT = 800, 50000, 160

    rows = []
    for mid in cc_ids:
        pr = merged_pricing.get(mid, {})
        inp = pr.get("input")
        outp = pr.get("output")
        cr = pr.get("cached_read")
        cw = pr.get("cached_write")
        credits = pr.get("credits")
        cost_req = compute_cost(inp, outp, cr, EST_INPUT, EST_CACHED, EST_OUTPUT, cached_write_per_1m=cw, est_cached_write=0)
        # caps scaled from credits (GOAT pooled caps): 5h = 14*credits/70, wk = 35*credits/70, mo = credits
        if credits is not None:
            cap_mo = float(credits)
            cap_wk = cap_mo * (ACC_WK / ACC_MO)
            cap_5h = cap_mo * (ACC_5H / ACC_MO)
        else:
            cap_mo = cap_wk = cap_5h = None
        if cost_req and cost_req > 0 and credits is not None:
            req_5h = cap_5h / cost_req if cap_5h else None
            req_wk = cap_wk / cost_req if cap_wk else None
            req_mo = cap_mo / cost_req if cap_mo else None
        else:
            req_5h = req_wk = req_mo = None
        docs_req = requests_live.get(mid, {})
        aa_rec = find_aa_for_cc(mid, aa_map) if aa_map else None
        lm_rec = find_lm_for_cc(mid, lm_map) if lm_map else None
        or_oid, or_rec = find_or_for_cc(mid, or_map) if or_map else (None, None)
        live_rec = find_livebench_for_cc(mid, live_map) if live_map else None
        aa_int = _safe_float(aa_rec.get("intelligenceIndex")) if aa_rec else None
        aa_cod = _safe_float(aa_rec.get("codingIndex")) if aa_rec else None
        aa_age = _safe_float(aa_rec.get("agenticIndex")) if aa_rec else None
        aa_tps = _safe_float(aa_rec.get("medianOutputTokensPerSecond")) if aa_rec else None
        aa_ctx = _safe_int(aa_rec.get("contextWindowTokens")) if aa_rec else None
        raw_slug = aa_rec.get("slug") if aa_rec else None
        aa_slug = str(raw_slug) if raw_slug and not str(raw_slug).startswith("$") else None
        lm_rank = _safe_int(lm_rec.get("rank")) if lm_rec else None
        lm_elo = _safe_float(lm_rec.get("elo")) if lm_rec else None
        lm_votes = _safe_int(lm_rec.get("votes")) if lm_rec else None
        or_ctx = or_rec.get("context_length") if or_rec else None
        or_price_prompt = None
        if or_rec:
            try:
                or_price_prompt = float(or_rec.get("pricing", {}).get("prompt", 0)) * 1_000_000
            except Exception:
                pass
        intel_per_dollar = (aa_int / cost_req) if (aa_int is not None and cost_req and cost_req > 0) else None
        cost_per_intel = (cost_req / aa_int) if (aa_int and cost_req) else None
        req_per_dollar = (1 / cost_req) if cost_req else None
        leverage = (credits / 10.0) if credits else None
        rows.append({
            "model_id": mid,
            "display": mid,
            "pricing": {"input_per_1m": inp, "output_per_1m": outp, "cached_read_per_1m": cr, "cached_write_per_1m": cw, "monthly_credits": credits},
            "caps": {"cap_5h_usd": cap_5h, "cap_wk_usd": cap_wk, "cap_mo_usd": cap_mo},
            "tokens": {"est_input": EST_INPUT, "est_cached": EST_CACHED, "est_output": EST_OUTPUT},
            "cost_per_request_usd": round(cost_req, 6) if cost_req is not None else None,
            "requests": {
                "per_5h_computed": _safe_int_round(req_5h),
                "per_week_computed": _safe_int_round(req_wk),
                "per_month_computed": _safe_int_round(req_mo),
                "per_5h_docs": docs_req.get("per_5h"),
                "per_week_docs": docs_req.get("per_week"),
                "per_month_docs": docs_req.get("per_month"),
            },
            "benchmarks": {
                "aa_slug": aa_slug, "aa_intelligence": aa_int, "aa_coding": aa_cod, "aa_agentic": aa_age,
                "aa_median_tps": aa_tps, "aa_context": aa_ctx,
                "lmarena_rank": lm_rank, "lmarena_elo": lm_elo, "lmarena_votes": lm_votes,
                "livebench": live_rec, "openrouter_id": or_oid, "openrouter_context": or_ctx,
                "openrouter_prompt_per_1m": or_price_prompt,
            },
            "value": {
                "intelligence_per_dollar": round(intel_per_dollar, 2) if intel_per_dollar else None,
                "cost_per_intelligence_pt_usd": round(cost_per_intel, 6) if cost_per_intel else None,
                "requests_per_dollar": round(req_per_dollar, 1) if req_per_dollar else None,
                "leverage_vs_10usd_sub": round(leverage, 2) if leverage else None,
            },
        })

    z_int = get_z_scores([r["benchmarks"]["aa_intelligence"] for r in rows])
    z_cod = get_z_scores([r["benchmarks"]["aa_coding"] for r in rows])
    z_age = get_z_scores([r["benchmarks"]["aa_agentic"] for r in rows])
    z_elo = get_z_scores([r["benchmarks"]["lmarena_elo"] for r in rows])
    z_live = get_z_scores([r["benchmarks"].get("livebench", {}).get("overall") if isinstance(r["benchmarks"].get("livebench"), dict) else None for r in rows])
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
        if not weights:
            # No third-party benchmark coverage: do NOT fabricate a capability
            # score (fake Q=78 made unscored cheap models dominate AVI/FGI/quality
            # rankings). Uncovered models sort last under benchmark orders.
            b["composite_score"] = None
            b["capability_q"] = None
            b["p_success"] = None
            b["token_multiplier"] = None
            v["effective_cost_per_request"] = None
            v["effective_requests_per_5h"] = None
            v["effective_requests_per_month"] = None
            v["qvi_score"] = None
            v["value_score"] = None
            v["avi_score"] = None
            v["fgi_score"] = None
            v["bfi_score"] = None
            b["qvi_score"] = None
            b["avi_score"] = None
            b["fgi_score"] = None
            b["bfi_score"] = None
            continue
        tot_w = sum(weights) or 1.0
        cz = sum(z_parts) / tot_w if weights else 0.0
        q_score = compute_capability_q(cz)
        b["composite_score"] = q_score
        b["capability_q"] = q_score
        p_succ = compute_p_success(q_score)
        b["p_success"] = p_succ
        t_mult = compute_token_multiplier(p_succ)
        b["token_multiplier"] = t_mult
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
        qvi = compute_qvi(q_score, eff_req_5h)
        b["qvi_score"] = qvi
        v["qvi_score"] = qvi
        v["value_score"] = qvi
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

    sort_mode = getattr(args, "sort", "value")
    def _eff_cost(r):
        if r["pricing"].get("monthly_credits") is None or "free" in r["model_id"].lower():
            return 0.0
        v = r["value"].get("effective_cost_per_request")
        if v is None:
            v = r.get("cost_per_request_usd")
        return 999.0 if v is None else float(v)
    sort_key_fn = build_sort_key(sort_mode, _eff_cost)
    rows_sorted = sorted(rows, key=sort_key_fn)
    pareto_ids = set()
    try:
        cand = [r for r in rows_sorted if r["model_id"] in DOCS_IDS and r["benchmarks"].get("capability_q") is not None]
        for a in cand:
            a_cost = _eff_cost(a)
            a_q = a["benchmarks"].get("capability_q") or 0.0
            candidates = [(_eff_cost(b), b["benchmarks"].get("capability_q") or 0.0) for b in cand if b is not a]
            if not bc.pareto_dominated(a_cost, a_q, candidates, cost_epsilon=0.0001):
                pareto_ids.add(a["model_id"])
    except Exception:
        pareto_ids = set()

    prev_snapshot = load_previous_snapshot(DATA / "cc_live.json")
    diff_model_catalog(rows_sorted, prev_snapshot)
    docs_rows = [r for r in rows_sorted if r["model_id"] in DOCS_IDS]
    for r in docs_rows:
        r["is_docs_model"] = True
    catalog_diff = diff_model_catalog(docs_rows, prev_snapshot)
    added_ids = catalog_diff["added_ids"]
    removed_ids = catalog_diff["removed_ids"]
    removed_models = catalog_diff["removed_models"]
    use_color = not (getattr(args, "plain", False) or os.getenv("NO_COLOR"))
    slim_opt = True if getattr(args, "slim", False) else (False if getattr(args, "wide", False) else None)
    print("\n" + render_cli_table(docs_rows, pareto_ids=pareto_ids, added_ids=added_ids, removed_models=removed_models, color=use_color, slim=slim_opt, wide=getattr(args, "wide", False)))

    if do_write:
        role_recs_export = compute_role_recommendations(docs_rows, context="ccheck")
        live = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sources": {
                "commandcode_docs": CC_DOCS, "openrouter_api": OPENROUTER_API,
                "artificial_analysis": AA_URL, "lmarena": LMARENA_URL,
                "usage_limits": "https://commandcode.ai/docs/plans/goat#usage-limits",
                "account_caps": {"cap_5h": ACC_5H, "cap_week": ACC_WK, "cap_month": ACC_MO},
                "note": "per-model caps = $14*credits/70 (5h), $35*credits/70 (wk), credits (mo); credits from GOAT pricing tables; --fetch saves cc_goat_docs snapshot"
            },
            "catalog_diff": {"added": sorted(list(added_ids)), "removed": sorted(list(removed_ids)), "total_current": len(docs_rows), "total_previous": (len([m for m in prev_snapshot.get("models", []) if isinstance(m, dict) and m.get("is_docs_model")]) if (prev_snapshot and "models" in prev_snapshot) else len(docs_rows))},
            "role_recommendations": role_recs_export,
            "models": rows_sorted,
        }
        DATA.mkdir(parents=True, exist_ok=True)
        out_json = DATA / "cc_live.json"
        bc.atomic_write_text(out_json, json.dumps(live, indent=2))
        if verbose:
            print(f"wrote {out_json.relative_to(ROOT)}")
        OUT.mkdir(parents=True, exist_ok=True)
        cb_json = OUT / "cc_cost_benefit.json"
        bc.atomic_write_text(cb_json, json.dumps(rows_sorted, indent=2))
        if verbose:
            print(f"wrote {cb_json.relative_to(ROOT)}")
        work = one_sentence_work(docs_rows)
        html_path = OUT / "cc_cost_benefit.html"
        bc.atomic_write_text(html_path, render_html(docs_rows, work_sentence=work, pareto_ids=pareto_ids, added_ids=added_ids, removed_models=removed_models, data_note=data_label))
        if verbose:
            print(f"wrote {html_path.relative_to(ROOT)} ({html_path.stat().st_size} bytes)")
    else:
        print("\n(check-only, no files written)")


def render_html(rows, work_sentence=None, pareto_ids=None, added_ids=None, removed_models=None, data_note=None):
    if work_sentence is None:
        try:
            work_sentence = one_sentence_work(rows)
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
    title = f"Command Code GOAT — Cost/Benefit ({dt.date.today().isoformat()})"
    role_recs = compute_role_recommendations(rows, context="ccheck")
    role_recs_html = render_role_recommendations_html(role_recs) if role_recs else ""
    trs = []
    for r in rows:
        is_added = r["model_id"] in added_ids
        raw_mid = html_lib.escape(r["model_id"])
        mid = f'{raw_mid}<span class="badge badge-new">+NEW</span>' if is_added else raw_mid
        credits = r["pricing"].get("monthly_credits")
        credits_s = f"${credits:.0f}" if credits is not None else "—"
        c = r["cost_per_request_usd"]
        c_s = f"${c:.5f}" if isinstance(c, float) else "—"
        reqs = r.get("requests", {})
        req5 = reqs.get("per_5h_docs") if reqs.get("per_5h_docs") is not None else reqs.get("per_5h_computed")
        reqw = reqs.get("per_week_docs") if reqs.get("per_week_docs") is not None else reqs.get("per_week_computed")
        reqm = reqs.get("per_month_docs") if reqs.get("per_month_docs") is not None else reqs.get("per_month_computed")
        req5_s = f"{req5:,}" if isinstance(req5, int) else "—"
        reqw_s = f"{reqw:,}" if isinstance(reqw, int) else "—"
        reqm_s = f"{reqm:,}" if isinstance(reqm, int) else "—"
        cap5 = r.get("caps", {}).get("cap_5h_usd")
        cap5_s = f"${cap5:.2f}" if isinstance(cap5, float) else "—"
        q_val = r["benchmarks"].get("capability_q")
        q_s = f"{q_val:.1f}" if isinstance(q_val, (int, float)) else "—"
        p_val = r["benchmarks"].get("p_success")
        p_s = f"{p_val:.1f}%" if isinstance(p_val, (int, float)) else "—"
        eff_c = r["value"].get("effective_cost_per_request")
        eff_c_s = f"${eff_c:.5f}" if isinstance(eff_c, float) else "—"
        qvi_val = r["value"].get("qvi_score") or r["value"].get("value_score")
        qvi_s = f"{qvi_val:.1f}" if isinstance(qvi_val, (int, float)) else "—"
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
        cls = ""
        if is_added:
            cls = "added"
        elif r["model_id"] in pareto_ids:
            cls = "pareto"
        elif aa_int and aa_int >= 58:
            cls = "flagship"
        elif credits == 70 and ipd and ipd > 800:
            cls = "value"
        elif credits is None:
            cls = "free"
        trs.append(
            f'<tr class="{cls}">'
            f'<td class="m">{mid}</td>'
            f'<td class="n">{credits_s}</td>'
            f'<td class="n">{cap5_s}</td>'
            f'<td class="n">{c_s}</td>'
            f'<td class="n">{req5_s}</td><td class="n">{reqw_s}</td><td class="n">{reqm_s}</td>'
            f'<td class="n" style="font-weight:700; color:#2563eb;">{q_s}</td>'
            f'<td class="n">{p_s}</td>'
            f'<td class="n">{eff_c_s}</td>'
            f'<td class="n" style="font-weight:700; color:#059669;">{qvi_s}</td>'
            f'<td class="n" style="font-weight:700; color:#10b981;">{avi_s}</td>'
            f'<td class="n" style="font-weight:700; color:#8b5cf6;">{fgi_s}</td>'
            f'<td class="n">{aa_int_s}<span class="mid">{aa_slug}</span></td>'
            f'<td class="n">{aa_cod_s}</td>'
            f'<td class="n">{lm_s}<span class="mid">{elo_s}</span></td>'
            f'<td class="n">{ipd_s}</td><td class="n">{cpi_s}</td><td class="n">{lev_s}</td>'
            f'</tr>'
        )
    removed_html = ""
    if removed_models:
        rem_tags = []
        for rm in removed_models:
            rm_id = html_lib.escape(rm.get("model_id", "unknown"))
            pr_lim = rm.get("pricing", {}).get("monthly_credits")
            lim_s = f"${pr_lim:.0f}" if pr_lim is not None else "Free"
            fgi = rm.get("value", {}).get("fgi_score") or rm.get("benchmarks", {}).get("fgi_score")
            fgi_s = f"FGI {fgi:.1f}" if isinstance(fgi, (int, float)) else "FGI —"
            avi = rm.get("value", {}).get("avi_score") or rm.get("benchmarks", {}).get("avi_score")
            avi_s = f"AVI {avi:.1f}" if isinstance(avi, (int, float)) else "AVI —"
            rem_tags.append(f'<span class="removed-tag">❌ <b>{rm_id}</b> <span class="mid">(Prior: {lim_s}, {fgi_s}, {avi_s})</span></span>')
        removed_html = f"""
<div class="removed-section">
  <div class="removed-title">🔻 Removed / Deprecated Models ({len(removed_models)})</div>
  <div class="sub" style="margin-bottom:8px;">These models were present in the previous GOAT snapshot but are no longer advertised on the pricing page:</div>
  <div>{''.join(rem_tags)}</div>
</div>
"""
    body = f"""
<h1>{html_lib.escape(title)}</h1>
<p class="sub">{html_lib.escape(data_note)} — Command Code GOAT <code>$10/mo (first month $5)</code> · Caps: <b>$14/5h · $35/wk · $70/mo</b> pooled, per-model scaled by <code>credits/70</code> · <a href="https://commandcode.ai/docs/plans/goat#usage-limits" style="color:#58a6ff">usage limits</a> · Generated {dt.datetime.now(dt.timezone.utc).isoformat()}</p>
<div class="card"><b>How to read:</b> <span style="color:#d29922">■ pareto</span> frontier · <span style="color:#3fb950">■ flagship</span> int ≥58 · <span style="color:#58a6ff">■ value</span> $70 credits + high int/$ · <b>Q(Cap)</b>=Capability · <b>P(Succ)</b>=pass rate · <b>Eff c/r</b>=cost per solved task · <b>Value</b>=quota utility · <b>AVI</b>=ROI · <b>FGI</b>=gate · <b>lev</b>=credits/10.</div>
<div class="card">
<table id="tbl">
<thead><tr>
<th>model</th><th>credits/mo</th><th>5h Cap</th><th>$c/req</th><th>req/5h</th><th>req/wk</th><th>req/mo</th><th>Q(Cap)</th><th>P(Succ)</th><th>Eff c/r</th><th>Value</th><th>AVI</th><th>FGI</th><th>AA intel</th><th>AA cod</th><th>LMArena</th><th>int/$</th><th>$c/int</th><th>lev</th>
</tr></thead>
<tbody>
{''.join(trs)}
</tbody>
</table>
<div class="legend">Click headers to sort. "—" = not benchmarked / free. AA/LMArena from shared snapshots; pricing from commandcode.ai/docs/plans/goat. Cross-source scores incomparable.</div>
</div>
{removed_html}
{role_recs_html}
<div class="call"><b>Takeaway:</b> Cheapest/req (MiMo-V2.5, DeepSeek Flash, Hy3) buys the most requests per 5h window — bulk fills. Flagship intelligence (Grok 4.6, GPT-5.6 Sol, Kimi K3) costs more/req but scores higher. Best int/$ usually in the middle (GLM-5.2, DeepSeek Flash, MiniMax M3). Use the <code>int/$</code> column to pick your tier.</div>
<p class="note">Full JSON: <a href="cc_cost_benefit.json" style="color:#58a6ff">cc_cost_benefit.json</a> · Raw snapshot: <code>data/raw/cc_goat_docs_YYYYMMDD.html</code> with <code>--fetch</code>. Stdlib only. Re-run: <code>python3 checkers/commandcode_cost_benefit_analyzer.py</code>.</p>
<div class="footer"><span class="path">path: outputs/cc_cost_benefit.html</span><span class="work">{html_lib.escape(work_sentence)}</span></div>
"""
    return f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html_lib.escape(title)}</title><style>{bc.HTML_CSS_COMMON}</style></head><body><div class=\"wrap\">{body}</div>{bc.HTML_SORT_SCRIPT}</body></html>\n"


def one_sentence_work(rows):
    try:
        n = len(rows)
        have_int = sum(1 for r in rows if r["benchmarks"]["aa_intelligence"] is not None)
        best = None
        for r in sorted(rows, key=lambda x: -(x["value"]["intelligence_per_dollar"] or -1)):
            if r["pricing"].get("monthly_credits") == 70 and r["value"]["intelligence_per_dollar"]:
                best = r["model_id"]
                break
        flagship = None
        for r in rows:
            if r["benchmarks"]["aa_intelligence"] and r["benchmarks"]["aa_intelligence"] >= 59:
                flagship = r["model_id"]
                break
        if best and flagship:
            return f"Current work: live GOAT cost/benefit of {n} models ({have_int} ranked) — best value {best}, flagship {flagship}."
        if best:
            return f"Current work: live GOAT check of {n} models ({have_int} ranked) — best value {best}."
        return f"Current work: live GOAT check of {n} models ({have_int} ranked)."
    except Exception:
        return f"Current work: live check of {len(rows)} GOAT models."


if __name__ == "__main__":
    main()
