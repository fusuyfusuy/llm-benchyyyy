#!/usr/bin/env python3
"""Command Code GOAT catalog & cost/benefit analyzer (`ccheck`).

Checks Command Code GOAT models (https://commandcode.ai/docs/plans/goat) against
Artificial Analysis, LMArena, LiveBench, and OpenRouter benchmarks under pooled
GOAT usage caps ($14/5h, $35/wk, $70/mo). Offline by default (reads dated
snapshots from docs/data/raw/); --fetch is the only network path.
"""

import argparse
import datetime as dt
import html as html_lib
import json
import os
import re
import shutil
import sys
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

import benchmark_common as bc  # noqa: E402
from benchmark_common import (  # noqa: E402
    BG_EVEN,
    BG_HEADER,
    BG_ODD,
    C_BOLD,
    C_BRONZE,
    C_CYAN,
    C_DIM,
    C_GOLD,
    C_GRAY,
    C_GREEN,
    C_MAGENTA,
    C_RED,
    C_RESET,
    C_SILVER,
    C_WHITE,
    C_YELLOW,
)

CC_DOCS = "https://commandcode.ai/docs/plans/goat"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
LMARENA_URL = "https://arena.ai/leaderboard/code/webdev"

ACC_5H, ACC_WK, ACC_MO = 14.0, 35.0, 70.0
EST_INPUT, EST_CACHED, EST_OUTPUT = 800, 50000, 160

_SNAP_LABELS = (
    ("docs", "cc_goat_docs"),
    ("OpenRouter", "openrouter_models"),
    ("AA", "artificial_analysis"),
    ("LMArena", "lmarena"),
    ("LiveBench", "livebench_2"),
)

FALLBACK_PRICING = {
    "gemini-3.8-flash": {"input": 1.5, "output": 7.5, "cached_read": 0.15, "cached_write": None, "credits": 40.0},
    "muse-spark-1.3": {"input": 1.25, "output": 4.25, "cached_read": 0.15, "cached_write": None, "credits": 20.0},
    "muse-spark-1.3-contributor": {"input": 0.1, "output": 0.2, "cached_read": 0.002, "cached_write": None, "credits": 20.0},
    "qwen-3.8-max-0902": {"input": 2.0, "output": 6.0, "cached_read": 0.25, "cached_write": None, "credits": 20.0},
    "deepseek-v4.1-flash": {"input": 0.15, "output": 0.6, "cached_read": 0.003, "cached_write": None, "credits": 60.0},
    "longcat-2.0-free": {"input": None, "output": None, "cached_read": None, "cached_write": None, "credits": None},
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
    "ling-3.0-flash-sante-free": {"input": None, "output": None, "cached_read": None, "cached_write": None, "credits": None},
}

DOCS_IDS = set(FALLBACK_PRICING.keys())

_ID_ALIASES = {
    "deepseek-v4.1-flash": "deepseek-v4.1-flash",
    "deepseek-v4-1-flash": "deepseek-v4.1-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-v4-flash-vision",
    "deepseek-v4-flash-vision-(exp)": "deepseek-v4-flash-vision",
    "tencent-hy4-preview": "tencent-hy4-preview",
    "glm-5.3-flash": "glm-5.3-flash",
    "qwen-3.8-flash": "qwen-3.8-flash",
    "deepseek-v4-flash-fast": "deepseek-v4-flash-fast",
    "kimi-k2.7-code-highspeed": "kimi-k2.7-code-highspeed",
    "kimi-k2-7-code-highspeed": "kimi-k2.7-code-highspeed",
    "muse-spark-1.2-contributor": "muse-spark-1.2-contributor",
    "muse-spark-1.3-contributor": "muse-spark-1.3-contributor",
    "laguna-s-2.1-free": "laguna-s-2.1-free",
    "laguna-s-2.1free": "laguna-s-2.1-free",
    "laguna-s-2.1": "laguna-s-2.1-free",
    "longcat-2.0-free": "longcat-2.0-free",
    "longcat-2.0free": "longcat-2.0-free",
    "ling-3.0-flash-sante-free": "ling-3.0-flash-sante-free",
    "ling-3.0-flash-sante": "ling-3.0-flash-sante-free",
    "ling-3.0-flash-sante:free": "ling-3.0-flash-sante-free",
    "qwen-3.7-flash-(32k)": "qwen-3.7-flash",
    "qwen-3.7-flash-(256k)": "qwen-3.7-flash",
    "qwen-3.7-flash-(>256k)": "qwen-3.7-flash",
}

_OLDER_STANDARD_MODELS = (
    "Kimi K2.6",
    "Kimi K2.5",
    "GLM-5.1",
    "GLM-5",
    "Qwen 3.7 Flash",
    "Qwen 3.6 Max Preview",
    "MiniMax M2.7",
    "MiniMax M2.5",
)

_SLIM_HEADERS = [
    ("Rank", 4, "^"), ("Model", 20, "<"), ("Credits", 8, "^"), ("Req/Mo", 7, ">"),
    ("Q(Cap)", 6, ">"), ("P(Succ)", 7, ">"), ("Eff c/r", 7, ">"), ("Val", 6, ">"), ("AVI", 7, ">"), ("FGI", 5, ">"),
]

_WIDE_HEADERS = [
    ("Rank", 4, "^"), ("Model", 22, "<"), ("Credits", 8, "^"), ("Req/Mo", 8, ">"),
    ("Q(Cap)", 6, ">"), ("P(Succ)", 7, ">"), ("Eff c/r", 7, ">"), ("Value", 6, ">"),
    ("AVI", 7, ">"), ("FGI", 5, ">"), ("CC-Int", 6, ">"), ("Lev", 5, ">"),
]

_METRIC_GUIDE_ITEMS = [
    ("Gold Bold", "Pareto Frontier (undefeated capability vs cost).", C_GOLD),
    ("Green (+)", "Newly added model vs previous baseline.", C_GREEN),
    ("Badges ¹²³", "🥇/🥈/🥉 leaders per column.", C_YELLOW),
    ("Quota", "Pooled $14/5h · $35/wk · $70/mo. Per-model 5h cap = $14 × (credits/70).", C_WHITE),
    ("$70 credits", "GPT-5.6 Sol, GLM-5.2, Tencent Hy3, Qwen 3.8 27B — max monthly headroom.", C_GREEN),
    ("$60 credits", "DeepSeek V4 Flash, Kimi K2.7 Code — daily driver.", C_CYAN),
    ("$20 credits", "New/discounted models — still 2× public pricing.", C_WHITE),
    ("Value (QVI)", "Delivered Task Utility = log10(N_eff + 1) × (Q/70)^2.4 × 100.", C_GREEN),
    ("Eff c/r", "Real cost per solved task = base cost/req × retry multiplier.", C_WHITE),
]

_HTML_COLS = [
    "model", "credits/mo", "5h Cap", "$c/req", "req/5h", "req/wk", "req/mo",
    "Q(Cap)", "P(Succ)", "Eff c/r", "Value", "AVI", "FGI", "AA intel", "AA cod",
    "CC intel", "CC cod", "CC TPS", "LMArena", "int/$", "$c/int", "lev",
]

_EFF_LADDER = [(lambda v: v < 0.002, C_GREEN), (lambda v: v < 0.01, C_CYAN), (lambda v: v < 0.03, C_YELLOW)]
_RANK_MEDALS = {1: ("🥇#1", C_GOLD), 2: ("🥈#2", C_SILVER), 3: ("🥉#3", C_BRONZE)}
_DASH_CELLS = ("—", "-", "")


def _sf(val, default=None):
    return bc._safe_float(val, default=default, strip_currency=False)


def _si(val, default=None):
    return bc._safe_int(val, default=default, strip_currency=False)


def _si_round(val) -> int | None:
    return int(round(val)) if bc._is_num(val) else None


def _norm_cc_id(raw: str) -> str | None:
    cleaned = re.sub(r"\([^)]*\)", "", raw.strip()).strip()
    cleaned = re.sub(r"\s*Off-peak.*", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s*-\d+%\s*$", "", cleaned).strip()
    low = re.sub(r"\s+", "-", cleaned.lower().replace("_", "-").replace(":", "-"))
    low = re.sub(r"-+", "-", low).strip("-")
    if not re.match(r"^[a-z0-9][a-z0-9\.\-]*$", low) or len(low) < 2:
        return None
    return _ID_ALIASES.get(low, low)


def _find_json_array_end(text: str, start: int) -> int:
    depth, pos, in_str, esc = 1, start, False, False
    while pos < len(text) and depth > 0:
        ch = text[pos]
        if esc:
            esc = False
        elif in_str and ch == "\\":
            esc = True
        elif ch == '"':
            in_str = not in_str
        elif not in_str and ch in "[]":
            depth += 1 if ch == "[" else -1
        pos += 1
    return pos


def _scan_rsc_span(unescaped: str) -> tuple[int, int] | None:
    best_span = None
    pos = 0
    while (idx := unescaped.find('"models":[', pos)) != -1:
        pos = idx + 1
        if "intelligenceIndex" not in unescaped[idx : idx + 3000]:
            continue
        end = _find_json_array_end(unescaped, idx + len('"models":['))
        if best_span is None or (end - idx) > (best_span[1] - best_span[0]):
            best_span = (idx, end)
    return best_span


def _extract_rsc_intel(unescaped: str, verbose: bool) -> dict:
    span = _scan_rsc_span(unescaped)
    if span is None:
        return {}
    try:
        models = json.loads("{" + unescaped[span[0] : span[1]] + "}")["models"]
    except Exception as exc:
        if verbose:
            print(f"  WARN docs intel parse: {exc}", file=sys.stderr)
        return {}
    intel = {}
    for m in models:
        cc_id = _norm_cc_id(m.get("name") or m.get("slug") or "")
        if cc_id:
            intel[cc_id] = {
                "intelligenceIndex": _sf(m.get("intelligenceIndex")),
                "codingIndex": _sf(m.get("codingIndex")),
                "outputTokensPerSec": _sf(m.get("outputTokensPerSec")),
                "contextWindow": m.get("contextWindow"),
                "minPlanName": m.get("minPlanName"),
                "name": m.get("name"),
                "slug": m.get("slug"),
            }
    return intel


def _table_header_text(table_html: str) -> str:
    m = re.search(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", m.group(1)).lower() if m else ""


def _clean_cells(tr_html: str) -> list[str]:
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_html, flags=re.S)
    return [" ".join(re.sub(r"<[^>]+>", " ", c).split()) for c in cells]


def _eff_price(cell: str) -> float | None:
    nums = re.findall(r"\$([\d\.]+)", cell)
    if not nums:
        return None
    try:
        return float(nums[-1])
    except ValueError:
        return None


def _detect_catalog_cols(rows: list[str]) -> tuple[int, int, int, int]:
    hdr = [c.lower() for c in _clean_cells(rows[0])] if rows else []
    cols = {"input": -1, "output": -1, "cache read": -1, "cache write": -1}
    for key in cols:
        cols[key] = next((i for i, h in enumerate(hdr) if key in h), -1)
    ci = cols["input"] if cols["input"] != -1 else (4 if len(hdr) >= 9 else 3)
    return (
        ci,
        cols["output"] if cols["output"] != -1 else ci + 1,
        cols["cache read"] if cols["cache read"] != -1 else ci + 2,
        cols["cache write"] if cols["cache write"] != -1 else ci + 3,
    )


def _cell_at(clean: list[str], idx: int) -> str:
    return clean[idx] if idx < len(clean) else ""


def _parse_catalog_row(clean: list[str], cols: tuple[int, int, int, int], pricing: dict) -> None:
    if len(clean) < 7:
        return
    mid = _norm_cc_id(re.sub(r"\s*-\d+%\s*$", "", clean[0]).strip())
    if not mid or mid in pricing:
        return
    ci, co, cr, cw = cols
    if _cell_at(clean, ci).lower() == "free" or _cell_at(clean, 4).lower() == "free":
        pricing[mid] = {"input": None, "output": None, "cached_read": None, "cached_write": None, "credits": None}
        return
    cw_cell = _cell_at(clean, cw)
    pricing[mid] = {
        "input": _eff_price(_cell_at(clean, ci)),
        "output": _eff_price(_cell_at(clean, co)),
        "cached_read": _eff_price(_cell_at(clean, cr)),
        "cached_write": _eff_price(cw_cell) if cw_cell not in _DASH_CELLS else None,
        "credits": None,
    }


def _parse_catalog_table(table_html: str, pricing: dict) -> None:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.S)
    cols = _detect_catalog_cols(rows)
    for tr in rows[1:]:
        _parse_catalog_row(_clean_cells(tr), cols, pricing)


def _parse_credit_cell(raw_cell: str, clean_cell: str) -> float | None:
    cred = _eff_price(raw_cell)
    if cred is not None:
        return cred
    # Anchored so promotional multipliers like "1.5x" do not parse as dollar credits.
    tokens = re.findall(r"^\$?(\d+(?:\.\d+)?)$", clean_cell.strip())
    return float(tokens[-1]) if tokens else None


def _parse_credits_table(table_html: str, pricing: dict) -> None:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.S)
    for tr in rows[1:]:
        raw_cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
        clean = _clean_cells(tr)
        if len(clean) < 6:
            continue
        mid = _norm_cc_id(re.sub(r"\s*-\d+%\s*$", "", clean[0]).strip())
        if not mid:
            continue
        cred = _parse_credit_cell(raw_cells[5], clean[5])
        if mid in pricing:
            pricing[mid]["credits"] = cred
            continue
        cw_cell = clean[4]
        pricing[mid] = {
            "input": _eff_price(clean[1]),
            "output": _eff_price(clean[2]),
            "cached_read": _eff_price(clean[3]),
            "cached_write": _eff_price(cw_cell) if cw_cell not in _DASH_CELLS else None,
            "credits": cred,
        }


def _parse_requests_table(table_html: str, requests: dict) -> None:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.S)
    for tr in rows[1:]:
        clean = [c.replace(",", "") for c in _clean_cells(tr)]
        if len(clean) < 4:
            continue
        mid = _norm_cc_id(re.sub(r"\s*-\d+%\s*$", "", clean[0]).strip())
        if not mid:
            continue
        vals = [int(clean[i]) if clean[i] not in _DASH_CELLS else None for i in (1, 2, 3)]
        requests[mid] = {"per_5h": vals[0], "per_week": vals[1], "per_month": vals[2]}


def _patch_older_credits(html: str, pricing: dict) -> None:
    if "Older models also available" not in html:
        return
    for mname in _OLDER_STANDARD_MODELS:
        mid = _norm_cc_id(mname)
        if mid and mid in pricing and pricing[mid].get("credits") is None:
            pricing[mid]["credits"] = 20.0


def _parse_non_catalog_tables(tables: list[str], pricing: dict, requests: dict) -> None:
    for tbl in tables:
        hdr = _table_header_text(tbl)
        if "monthly credits" in hdr:
            _parse_credits_table(tbl, pricing)
        elif ("requests / 5 hour" in hdr or "requests per 5 hour" in hdr) and not requests:
            _parse_requests_table(tbl, requests)


def parse_cc_docs(html: str, verbose: bool = False) -> tuple[dict, dict, dict]:
    """Parse GOAT docs HTML tables and embedded Next.js RSC model intelligence."""
    pricing: dict = {}
    requests: dict = {}
    tables = re.findall(r"<table.*?</table>", html, flags=re.S)
    if verbose:
        print(f"  docs: found {len(tables)} tables")
    intel = _extract_rsc_intel(html.replace('\\"', '"').replace("\\/", "/"), verbose)

    for tbl in tables:
        hdr = _table_header_text(tbl)
        if "context" in hdr and "caps" in hdr and not pricing:
            _parse_catalog_table(tbl, pricing)
    _parse_non_catalog_tables(tables, pricing, requests)
    _patch_older_credits(html, pricing)
    return pricing, requests, intel


def build_sort_key(sort_mode: str, eff_cost_fn):
    return bc.build_analyzer_sort_key(sort_mode, eff_cost_fn)


def _metric_num(row: dict, section: str, key: str) -> float | None:
    val = row.get(section, {}).get(key)
    return float(val) if bc._is_num(val) else None


def _req_mo_val(row: dict):
    reqs = row.get("requests", {})
    docs = reqs.get("per_month_docs")
    return docs if docs is not None else reqs.get("per_month_computed")


def _max_by_metric(rows: list[dict], section: str, key: str) -> tuple[dict | None, float]:
    best, best_v = None, -1.0
    for row in rows:
        val = _metric_num(row, section, key)
        if val is not None and val > best_v:
            best, best_v = row, val
    return best, best_v


def _banner_summary(models_list: list[dict], is_slim: bool) -> str:
    scored = [m for m in models_list if _metric_num(m, "benchmarks", "capability_q") is not None]
    top_val, top_val_n = _max_by_metric(scored, "value", "qvi_score")
    top_fgi, top_fgi_n = _max_by_metric(scored, "value", "fgi_score")
    top_req = max(models_list, key=lambda m: _req_mo_val(m) or 0) if models_list else None

    v_s = f"Top Val: {top_val['model_id'][:14]} (Val {top_val_n:.1f})" if top_val else ""
    f_s = f"Frontier: {top_fgi['model_id'][:14]} (FGI {top_fgi_n:.1f})" if top_fgi else ""
    req_cnt = (_req_mo_val(top_req) or 0) if top_req else 0
    s_s = f"Max Bulk: {top_req['model_id'][:12]} ({bc.format_compact_num(req_cnt)}/mo)" if top_req else ""
    base = f" Caps: $14/5h · $35/wk · $70/mo · credits $20–$70 │ {v_s} │ {f_s}"
    return base if is_slim else f"{base} │ {s_s}"


def _limit_color(credits) -> str:
    if credits is None:
        return C_GRAY
    if credits >= 60:
        return C_GREEN
    if credits >= 40:
        return C_CYAN
    if credits >= 30:
        return C_YELLOW
    return C_WHITE


def _score_cell(val, fmt: str, medal: int | None, score_fn, width: int, color: bool) -> tuple[str, str, int, str]:
    if val is None:
        return "—", C_DIM, width, ">"
    return fmt.format(val) + bc.medal_badge(medal, color=color), score_fn(val), width, ">"


def _credits_label(credits, mid: str) -> str:
    if credits is not None:
        return f"${credits:.0f}"
    return "Free" if "free" in mid.lower() else "—"


def _row_prefix_specs(idx: int, row: dict, ctx: dict) -> list[tuple[str, str, int, str]]:
    rank = idx + 1
    rank_str, rank_col = _RANK_MEDALS.get(rank, (f" #{rank}", C_WHITE))
    mid = row["model_id"]
    is_added = mid in ctx["added_ids"]
    name_w = 20 if ctx["is_slim"] else 22
    mid_disp = (f"+{mid}" if is_added else mid)[:name_w]
    mid_col = (C_BOLD + C_GREEN) if is_added else ((C_BOLD + C_GOLD) if mid in ctx["pareto_ids"] else C_WHITE)
    credits = row["pricing"].get("monthly_credits")
    req_mo = _req_mo_val(row)
    req_col = C_CYAN if (req_mo is not None and req_mo >= 15000) else C_WHITE
    return [
        (rank_str, C_BOLD + rank_col, 4, "^"),
        (mid_disp, mid_col, name_w, "<"),
        (_credits_label(credits, mid), _limit_color(credits), 8, "^"),
        (bc.format_compact_num(req_mo), req_col, 7 if ctx["is_slim"] else 8, ">"),
    ]


def _wide_extra_specs(bm: dict, val: dict) -> list[tuple[str, str, int, str]]:
    cc_int, lev = bm.get("cc_intelligence"), val.get("leverage_vs_10usd_sub")
    cc_s = f"{cc_int:.1f}" if cc_int is not None else "—"
    cc_col = C_DIM if cc_int is None else C_CYAN
    return [(cc_s, cc_col, 6, ">"), (f"{lev:.1f}x" if lev else "—", C_DIM, 5, ">")]


def _row_specs(idx: int, row: dict, ctx: dict) -> tuple[list[tuple[str, str, int, str]], str]:
    meds = ctx["col_medals"].get(row["model_id"], {})
    bm, val = row.get("benchmarks", {}), row.get("value", {})
    eff_c = val.get("effective_cost_per_request")
    eff_s = f"${eff_c:.4f}" if eff_c is not None else "—"
    color = ctx["color"]

    specs = _row_prefix_specs(idx, row, ctx) + [
        _score_cell(bm.get("capability_q"), "{:.1f}", meds.get("q"), bc.score_color_q, 6, color),
        _score_cell(bm.get("p_success"), "{:.1f}%", meds.get("psucc"), bc.score_color_p, 7, color),
        (eff_s, bc.color_ladder(eff_c, _EFF_LADDER, default_color=C_MAGENTA), 7, ">"),
        _score_cell(val.get("qvi_score"), "{:.1f}", meds.get("value"), bc.score_color_qvi, 6, color),
        _score_cell(val.get("avi_score"), "{:.1f}", meds.get("avi"), bc.score_color_avi, 7, color),
        _score_cell(val.get("fgi_score"), "{:.1f}", meds.get("fgi"), bc.score_color_fgi, 5, color),
    ]
    if not ctx["is_slim"]:
        specs.extend(_wide_extra_specs(bm, val))
    return specs, (BG_ODD if idx % 2 == 1 else BG_EVEN)


def _format_cli_row(idx: int, row: dict, ctx: dict) -> str:
    specs, bg = _row_specs(idx, row, ctx)
    if ctx["color"]:
        cells = [bc.color_cell(txt, col, width=w, align=aln, bg=bg) for txt, col, w, aln in specs]
        sep = f"{bg}{C_DIM}│{C_RESET}"
        return sep + sep.join(cells) + sep
    return " ".join(bc.pad_display(txt, w, aln) for txt, _, w, aln in specs)


def _diff_banner_lists(added_ids: set | None, removed_models: list[dict] | None) -> tuple[list[str], list[str]]:
    notices, parts = [], []
    if added_ids:
        names = ", ".join(sorted(added_ids))
        notices.append(f"{C_BOLD}{C_GREEN}✨ New (+{len(added_ids)}): {names}{C_RESET}")
        parts.append(f"[+NEW (+{len(added_ids)}): {names}]")
    if removed_models:
        rem = ", ".join(m.get("model_id", "unknown") for m in removed_models)
        notices.append(f"{C_BOLD}{C_RED}🔻 Removed (-{len(removed_models)}): {rem}{C_RESET}")
        parts.append(f"[-REMOVED (-{len(removed_models)}): {rem}]")
    return notices, parts


def _table_chrome(headers: list, inner_w: int, color: bool) -> tuple[list[str], str]:
    if color:
        hdr_cells = [bc.color_cell(h, C_BOLD + C_WHITE, width=w, align=a, bg=BG_HEADER) for h, w, a in headers]
        sep = f"{BG_HEADER}{C_DIM}│{C_RESET}"
        head = [
            f"{C_DIM}┌{'┬'.join('─' * (w + 2) for _, w, _ in headers)}┐{C_RESET}",
            sep + sep.join(hdr_cells) + sep,
            f"{C_DIM}├{'┼'.join('─' * (w + 2) for _, w, _ in headers)}┤{C_RESET}",
        ]
        return head, f"{C_DIM}└{'┴'.join('─' * (w + 2) for _, w, _ in headers)}┘{C_RESET}"
    rule = "-" * (inner_w + 2)
    return [rule, " ".join(bc.pad_display(h, w, a) for h, w, a in headers), rule], rule


def _build_cli_ctx(models_list: list[dict], pareto_ids: set | None, added_ids: set | None, is_slim: bool, color: bool) -> dict:
    col_medals = bc.compute_column_medals(
        models_list,
        {
            "q": (lambda r: r["benchmarks"].get("capability_q") or 0, True, None),
            "psucc": (lambda r: r["benchmarks"].get("p_success") or 0, True, None),
            "value": (lambda r: r["value"].get("qvi_score") or 0, True, None),
            "avi": (lambda r: r["value"].get("avi_score") or 0, True, None),
            "fgi": (lambda r: r["value"].get("fgi_score") or 0, True, None),
        },
        id_key="model_id",
    )
    return {
        "pareto_ids": pareto_ids or set(),
        "added_ids": added_ids or set(),
        "is_slim": is_slim,
        "color": color,
        "col_medals": col_medals,
    }


def _cli_footer_lines(models_list: list[dict], removed_models: list[dict] | None, role_recs, is_slim: bool, inner_w: int, color: bool) -> list[str]:
    out = []
    if removed_models:
        out.extend(["", *bc.render_removed_models_cli(removed_models, color=color, is_slim=is_slim, id_key="model_id")])
    out.extend(["", *bc.render_metric_guide_cli("Command Code GOAT — Usage Limits & Metric Guide", _METRIC_GUIDE_ITEMS, color=color)])
    recs = role_recs if role_recs is not None else bc.compute_role_recommendations(models_list, context="ccheck")
    if recs:
        out.extend(["", *bc.render_role_recommendations_cli(recs, color=color, is_slim=is_slim, width=inner_w)])
    return out


def render_cli_table(
    models_list,
    pareto_ids=None,
    added_ids=None,
    removed_models=None,
    color=True,
    slim=None,
    wide=False,
    role_recs=None,
):
    is_slim = slim if slim is not None else (shutil.get_terminal_size((120, 24)).columns < 120 and not wide)
    headers = _SLIM_HEADERS if is_slim else _WIDE_HEADERS
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1

    diff_notices, diff_parts = _diff_banner_lists(added_ids, removed_models)
    out = bc.render_banner_box(
        f"⚡ COMMAND CODE GOAT — COST/BENEFIT & AGENTIC RADAR ({CC_DOCS}#usage-limits)",
        summary_lines=[_banner_summary(models_list, is_slim)],
        diff_notices=diff_notices,
        inner_w=inner_w,
        color=color,
        plain_title_line=" COMMAND CODE GOAT — COST/BENEFIT & AGENTIC RADAR — Caps: $14/5h · $35/wk · $70/mo · credits $20-$70",
        plain_diff_parts=diff_parts,
    )
    head_lines, bot_line = _table_chrome(headers, inner_w, color)
    out.extend(head_lines)

    ctx = _build_cli_ctx(models_list, pareto_ids, added_ids, is_slim, color)
    out.extend(_format_cli_row(idx, r, ctx) for idx, r in enumerate(models_list))
    out.append(bot_line)
    out.extend(_cli_footer_lines(models_list, removed_models, role_recs, is_slim, inner_w, color))
    return "\n".join(out)


def _fmt(val, pattern: str, fallback: str = "—") -> str:
    return pattern.format(val) if bc._is_num(val) else fallback


def _html_row_class(row: dict, pareto_ids: set, added_ids: set, aa_int, credits, ipd) -> str:
    if row["model_id"] in added_ids:
        return "added"
    if row["model_id"] in pareto_ids:
        return "pareto"
    if aa_int is not None and aa_int >= 58:
        return "flagship"
    if credits == 70 and ipd is not None and ipd > 800:
        return "value"
    if credits is None and "free" in row["model_id"].lower():
        return "free"
    return ""


def _render_html_tr(row: dict, pareto_ids: set, added_ids: set) -> str:
    bm, val, reqs = row.get("benchmarks", {}), row.get("value", {}), row.get("requests", {})
    raw_mid = html_lib.escape(row["model_id"])
    mid = f'{raw_mid}<span class="badge badge-new">+NEW</span>' if row["model_id"] in added_ids else raw_mid
    credits = row["pricing"].get("monthly_credits")
    req5 = reqs.get("per_5h_docs") if reqs.get("per_5h_docs") is not None else reqs.get("per_5h_computed")
    reqw = reqs.get("per_week_docs") if reqs.get("per_week_docs") is not None else reqs.get("per_week_computed")
    reqm = reqs.get("per_month_docs") if reqs.get("per_month_docs") is not None else reqs.get("per_month_computed")
    aa_int, ipd = bm.get("aa_intelligence"), val.get("intelligence_per_dollar")
    cls = _html_row_class(row, pareto_ids, added_ids, aa_int, credits, ipd)
    aa_slug = html_lib.escape(bm.get("aa_slug") or "")
    lm_r = bm.get("lmarena_rank")
    lm_s = f"#{int(lm_r)}" if bc._is_num(lm_r) else "—"
    return (
        f'<tr class="{cls}"><td class="m">{mid}</td><td class="n">{_fmt(credits, "${:.0f}")}</td>'
        f'<td class="n">{_fmt(row.get("caps", {}).get("cap_5h_usd"), "${:.2f}")}</td>'
        f'<td class="n">{_fmt(row.get("cost_per_request_usd"), "${:.5f}")}</td>'
        f'<td class="n">{_fmt(req5, "{:,}")}</td><td class="n">{_fmt(reqw, "{:,}")}</td><td class="n">{_fmt(reqm, "{:,}")}</td>'
        f'<td class="n" style="font-weight:700; color:#2563eb;">{_fmt(bm.get("capability_q"), "{:.1f}")}</td>'
        f'<td class="n">{_fmt(bm.get("p_success"), "{:.1f}%")}</td>'
        f'<td class="n">{_fmt(val.get("effective_cost_per_request"), "${:.5f}")}</td>'
        f'<td class="n" style="font-weight:700; color:#059669;">{_fmt(val.get("qvi_score"), "{:.1f}")}</td>'
        f'<td class="n" style="font-weight:700; color:#10b981;">{_fmt(val.get("avi_score"), "{:.1f}")}</td>'
        f'<td class="n" style="font-weight:700; color:#8b5cf6;">{_fmt(val.get("fgi_score"), "{:.1f}")}</td>'
        f'<td class="n">{_fmt(aa_int, "{:.1f}")}<span class="mid">{aa_slug}</span></td>'
        f'<td class="n">{_fmt(bm.get("aa_coding"), "{:.1f}")}</td>'
        f'<td class="n" style="font-weight:700; color:#c084fc;">{_fmt(bm.get("cc_intelligence"), "{:.1f}")}</td>'
        f'<td class="n">{_fmt(bm.get("cc_coding"), "{:.1f}")}</td><td class="n">{_fmt(bm.get("cc_tps"), "{:.0f}")}</td>'
        f'<td class="n">{lm_s}<span class="mid">{_fmt(bm.get("lmarena_elo"), "{:.0f}")}</span></td>'
        f'<td class="n">{_fmt(ipd, "{:.0f}")}</td>'
        f'<td class="n">{_fmt(val.get("cost_per_intelligence_pt_usd"), "${:.5f}")}</td>'
        f'<td class="n">{_fmt(val.get("leverage_vs_10usd_sub"), "{:.1f}×")}</td></tr>'
    )


def render_html(
    rows,
    work_sentence=None,
    pareto_ids=None,
    added_ids=None,
    removed_models=None,
    data_note=None,
    role_recs=None,
):
    pareto_ids = pareto_ids or set()
    added_ids = added_ids or set()
    removed_models = removed_models or []
    work_sentence = one_sentence_work(rows) if work_sentence is None else work_sentence
    recs = role_recs if role_recs is not None else bc.compute_role_recommendations(rows, context="ccheck")
    role_recs_html = bc.render_role_recommendations_html(recs) if recs else ""

    def _cc_removed_limit(rm: dict) -> str:
        pr = rm.get("pricing", {}).get("monthly_credits")
        return f"${pr:.0f}" if pr is not None else ("Free" if "free" in rm.get("model_id", "").lower() else "—")

    removed_html = bc.render_removed_html_section(
        removed_models,
        _cc_removed_limit,
        "These models were present in the previous GOAT snapshot but are no longer advertised on the pricing page:",
    )
    title = f"Command Code GOAT — Cost/Benefit ({dt.date.today().isoformat()})"
    subtitle_html = (
        f'{html_lib.escape(data_note or "Live check")} — Command Code GOAT <code>$10/mo (first month $5)</code> · '
        f'Caps: <b>$14/5h · $35/wk · $70/mo</b> pooled, per-model scaled by <code>credits/70</code> · '
        f'<a href="{CC_DOCS}#usage-limits" style="color:#58a6ff">usage limits</a> · Generated {dt.datetime.now(dt.UTC).isoformat()}'
    )
    legend_top = (
        '<b>How to read:</b> <span style="color:#d29922">■ pareto</span> frontier · '
        '<span style="color:#3fb950">■ flagship</span> int ≥58 · <span style="color:#58a6ff">■ value</span> '
        '$70 credits + high int/$ · <b>Q(Cap)</b>=Capability · <b>P(Succ)</b>=pass rate · '
        '<b>Eff c/r</b>=cost per solved task · <b>Value</b>=quota utility · <b>AVI</b>=ROI · <b>FGI</b>=gate · <b>lev</b>=credits/10.'
    )
    takeaway = (
        "<b>Takeaway:</b> Cheapest/req (MiMo-V2.5, DeepSeek Flash, Hy3) buys the most requests per monthly quota — bulk fills. "
        "Flagship intelligence (Grok 4.6, GPT-5.6 Sol, Kimi K3) costs more/req but scores higher. "
        "Best int/$ usually in the middle (GLM-5.2, DeepSeek Flash, MiniMax M3). Use the <code>int/$</code> column to pick your tier."
    )
    footer_note = (
        'Full JSON: <a href="cc_cost_benefit.json" style="color:#58a6ff">cc_cost_benefit.json</a> · '
        'Raw snapshot: <code>docs/data/raw/cc_goat_docs_YYYYMMDD.html</code> with <code>--fetch</code>. '
        'Stdlib only. Re-run: <code>uv run python checkers/commandcode_cost_benefit_analyzer.py</code>.'
    )
    return bc.render_analyzer_html_shell(
        title=title,
        subtitle_html=subtitle_html,
        legend_top_html=legend_top,
        th_cols=_HTML_COLS,
        trs=[_render_html_tr(r, pareto_ids, added_ids) for r in rows],
        legend_bot=(
            'Click headers to sort. "—" = not benchmarked / free. AA/LMArena from shared snapshots; '
            "CC intel/cod/TPS are Command Code's official scores from commandcode.ai/docs/plans/goat; "
            "pricing from the same page. Cross-source scores incomparable."
        ),
        removed_html=removed_html,
        role_recs_html=role_recs_html,
        takeaway_html=takeaway,
        footer_note_html=footer_note,
        work_sentence=work_sentence,
        out_href="docs/reports/cc_cost_benefit.html",
    )


def _best_value_id(rows: list[dict]) -> str | None:
    best, best_ipd = None, -1.0
    for row in rows:
        ipd = row["value"].get("intelligence_per_dollar")
        if row["pricing"].get("monthly_credits") == 70 and ipd and ipd > best_ipd:
            best, best_ipd = row["model_id"], ipd
    return best


def one_sentence_work(rows: list[dict]) -> str:
    have_int = sum(1 for r in rows if r["benchmarks"]["aa_intelligence"] is not None)
    best = _best_value_id(rows)
    flag_row = next((r for r in rows if r["benchmarks"]["aa_intelligence"] and r["benchmarks"]["aa_intelligence"] >= 59), None)
    flagship = flag_row["model_id"] if flag_row else None
    if best and flagship:
        return f"Current work: live GOAT cost/benefit of {len(rows)} models ({have_int} ranked) — best value {best}, flagship {flagship}."
    if best:
        return f"Current work: live GOAT check of {len(rows)} models ({have_int} ranked) — best value {best}."
    return f"Current work: live GOAT check of {len(rows)} models ({have_int} ranked)."


def _fetch_live_sources(do_write: bool, verbose: bool) -> tuple[dict, dict, dict, dict]:
    pricing_live, requests_live, intel_live = {}, {}, {}
    fetched_maps: dict[str, dict] = {}
    body = bc.fetch_bytes(CC_DOCS, verbose=verbose)
    if body:
        html_txt = body.decode(errors="ignore")
        if do_write:
            snap = RAW / f"cc_goat_docs_{dt.date.today().isoformat().replace('-', '')}.html"
            bc.atomic_write_text(snap, html_txt)
            print(f"  saved GOAT docs -> {snap.relative_to(ROOT)} ({len(html_txt)} bytes)")
        pricing_live, requests_live, intel_live = parse_cc_docs(html_txt, verbose=verbose)
        print(f"  docs: pricing={len(pricing_live)}, requests={len(requests_live)}, intel={len(intel_live)}")
    else:
        print("  WARN GOAT docs fetch failed, trying snapshot/fallback", file=sys.stderr)

    payload = bc.fetch_lmarena_hf_snapshot(RAW, verbose=verbose, do_write=do_write)
    if payload:
        fetched_maps["lmarena"] = bc.parse_lmarena_hf(payload, verbose=verbose)

    for url, tag in ((OPENROUTER_API, "openrouter_models"), (AA_URL, "artificial_analysis")):
        src_body = bc.fetch_bytes(url, verbose=verbose)
        if not src_body:
            continue
        try:
            text = src_body.decode(errors="ignore")
            if tag == "openrouter_models":
                parsed = json.loads(text)
                fetched_maps[tag] = bc.parse_openrouter(parsed, verbose=verbose)
                text = json.dumps(parsed, indent=2)
            else:
                fetched_maps[tag] = bc.parse_aa(text, verbose=verbose)
        except Exception as exc:
            print(f"  WARN {tag} live parse failed, falling back to snapshot: {exc}", file=sys.stderr)
            continue
        if do_write:
            ext = "json" if tag == "openrouter_models" else "html"
            snap = RAW / f"{tag}_{dt.date.today().isoformat().replace('-', '')}.{ext}"
            bc.atomic_write_text(snap, text)
            print(f"  saved {tag} -> {snap.relative_to(ROOT)}")
    return pricing_live, requests_live, intel_live, fetched_maps


def _load_offline_docs(verbose: bool) -> tuple[dict, dict, dict]:
    snap = bc.pick_latest_raw(RAW, "cc_goat_docs") or bc.pick_latest_raw(RAW, "cc_goat")
    if snap is None:
        return {}, {}, {}
    try:
        pl, rl, il = parse_cc_docs(snap.read_text(errors="ignore"), verbose=verbose)
        if pl:
            print(f"  offline GOAT docs: {len(pl)} models ({snap.name})")
        return pl, rl, il
    except Exception as exc:
        print(f"  WARN offline GOAT docs parse: {exc}", file=sys.stderr)
        return {}, {}, {}


def _resolve_pricing(mid: str, pricing_live: dict) -> dict:
    pr = dict(pricing_live.get(mid) or FALLBACK_PRICING.get(mid) or {
        "input": None, "output": None, "cached_read": None, "cached_write": None, "credits": 20.0,
    })
    if pr.get("credits") is None and "free" not in mid.lower() and mid in FALLBACK_PRICING:
        pr["credits"] = FALLBACK_PRICING[mid].get("credits")
    return pr


def _merge_pricing(pricing_live: dict) -> tuple[list[str], dict]:
    if not pricing_live:
        cc_ids = list(FALLBACK_PRICING.keys())
        print(f"  using fallback catalog: {len(cc_ids)}")
    else:
        cc_ids = list(pricing_live.keys()) + [k for k in FALLBACK_PRICING if k not in pricing_live]
    return cc_ids, {mid: _resolve_pricing(mid, pricing_live) for mid in cc_ids}


def _load_or_cache_map(fetched: dict, tag: str, parser, label: str, verbose: bool) -> dict:
    if tag in fetched:
        data = dict(fetched[tag])
        print(f"  {label}: {len(data)} entries (live fetch)")
        return data
    snap = bc.pick_latest_raw(RAW, tag)
    if snap is None:
        return {}
    try:
        raw_txt = snap.read_text(errors="ignore")
        payload = json.loads(raw_txt) if snap.suffix == ".json" else raw_txt
        data = parser(payload, verbose=verbose)
        print(f"  {label}: {len(data)} entries ({snap.name})")
        return data
    except Exception as exc:
        print(f"  WARN {label} parse: {exc}", file=sys.stderr)
        return {}


def _load_source_maps(fetched_maps: dict, verbose: bool) -> tuple[dict, dict, dict, dict]:
    or_map = _load_or_cache_map(fetched_maps, "openrouter_models", bc.parse_openrouter, "OpenRouter", verbose)
    aa_map = _load_or_cache_map(fetched_maps, "artificial_analysis", bc.parse_aa, "AA", verbose)
    lm_map = dict(fetched_maps.get("lmarena", {})) or bc.load_lmarena_map(RAW, verbose=verbose)
    if lm_map:
        print(f"  LMArena: {len(lm_map)} models")
    live_map = bc.load_livebench_snapshots(RAW, verbose=verbose)
    if live_map:
        print(f"  LiveBench: {len(live_map)} models loaded")
    return or_map, aa_map, lm_map, live_map


def _pick_num(rec: dict | None, key: str, fn=_sf):
    return fn(rec.get(key)) if rec else None


def _build_benchmarks_block(aa_rec, lm_rec, or_oid, or_rec, live_rec, cc_rec: dict) -> dict:
    raw_slug = aa_rec.get("slug") if aa_rec else None
    aa_slug = str(raw_slug) if raw_slug and not str(raw_slug).startswith("$") else None
    or_prompt = _sf((or_rec.get("pricing") or {}).get("prompt")) if or_rec else None
    return {
        "aa_slug": aa_slug,
        "aa_intelligence": _pick_num(aa_rec, "intelligenceIndex"),
        "aa_coding": _pick_num(aa_rec, "codingIndex"),
        "aa_agentic": _pick_num(aa_rec, "agenticIndex"),
        "aa_median_tps": _pick_num(aa_rec, "medianOutputTokensPerSecond"),
        "aa_context": _pick_num(aa_rec, "contextWindowTokens", _si),
        "lmarena_rank": _pick_num(lm_rec, "rank", _si),
        "lmarena_elo": _pick_num(lm_rec, "elo"),
        "lmarena_votes": _pick_num(lm_rec, "votes", _si),
        "livebench": live_rec,
        "openrouter_id": or_oid,
        "openrouter_context": or_rec.get("context_length") if or_rec else None,
        "openrouter_prompt_per_1m": or_prompt * 1_000_000 if or_prompt is not None else None,
        "cc_intelligence": _pick_num(cc_rec, "intelligenceIndex"),
        "cc_coding": _pick_num(cc_rec, "codingIndex"),
        "cc_tps": _pick_num(cc_rec, "outputTokensPerSec"),
    }


def _build_requests_block(caps: tuple, cost_req, docs_req: dict) -> dict:
    cap_5h, cap_wk, cap_mo = caps
    pos_cost = cost_req is not None and cost_req > 0 and cap_mo is not None
    return {
        "per_5h_computed": _si_round(cap_5h / cost_req) if pos_cost else None,
        "per_week_computed": _si_round(cap_wk / cost_req) if pos_cost else None,
        "per_month_computed": _si_round(cap_mo / cost_req) if pos_cost else None,
        "per_5h_docs": docs_req.get("per_5h"),
        "per_week_docs": docs_req.get("per_week"),
        "per_month_docs": docs_req.get("per_month"),
    }


def _build_value_block(aa_int, cost_req, credits) -> dict:
    pos = cost_req is not None and cost_req > 0
    ipd = (aa_int / cost_req) if (aa_int is not None and pos) else None
    cpi = (cost_req / aa_int) if (aa_int and pos) else None
    return {
        "intelligence_per_dollar": round(ipd, 2) if ipd else None,
        "cost_per_intelligence_pt_usd": round(cpi, 6) if cpi else None,
        "requests_per_dollar": round(1.0 / cost_req, 1) if pos else None,
        "leverage_vs_10usd_sub": round(credits / 10.0, 2) if credits else None,
    }


def _build_model_row(mid: str, pr: dict, reqs_live: dict, intel_live: dict, maps: tuple[dict, dict, dict, dict]) -> dict:
    or_map, aa_map, lm_map, live_map = maps
    inp, outp, cr, cw, credits = pr.get("input"), pr.get("output"), pr.get("cached_read"), pr.get("cached_write"), pr.get("credits")
    cost_req = bc.compute_cost(inp, outp, cr, EST_INPUT, EST_CACHED, EST_OUTPUT, cached_write_per_1m=cw, est_cached_write=0)
    cap_mo = _sf(credits)
    cap_wk = cap_mo * (ACC_WK / ACC_MO) if cap_mo is not None else None
    cap_5h = cap_mo * (ACC_5H / ACC_MO) if cap_mo is not None else None

    aa_rec = bc.find_aa_for_model(mid, aa_map) if aa_map else None
    lm_rec = bc.find_lm_for_model(mid, lm_map) if lm_map else None
    or_oid, or_rec = bc.find_or_for_model(mid, or_map) if or_map else (None, None)
    live_rec = bc.find_livebench_for_model(mid, live_map) if live_map else None
    bm = _build_benchmarks_block(aa_rec, lm_rec, or_oid, or_rec, live_rec, intel_live.get(mid) or {})
    return {
        "model_id": mid,
        "display": mid,
        "is_docs_model": True,
        "pricing": {"input_per_1m": inp, "output_per_1m": outp, "cached_read_per_1m": cr, "cached_write_per_1m": cw, "monthly_credits": credits},
        "caps": {"cap_5h_usd": cap_5h, "cap_wk_usd": cap_wk, "cap_mo_usd": cap_mo},
        "tokens": {"est_input": EST_INPUT, "est_cached": EST_CACHED, "est_output": EST_OUTPUT},
        "cost_per_request_usd": round(cost_req, 6) if cost_req is not None else None,
        "requests": _build_requests_block((cap_5h, cap_wk, cap_mo), cost_req, reqs_live.get(mid, {})),
        "benchmarks": bm,
        "value": _build_value_block(bm["aa_intelligence"], cost_req, credits),
    }


def _eff_cost(row: dict) -> float:
    if "free" in row["model_id"].lower():
        return 0.0
    val = row["value"].get("effective_cost_per_request")
    raw = val if val is not None else row.get("cost_per_request_usd")
    num = _sf(raw)
    return 999.0 if num is None else num


def _prev_docs_count(prev_snapshot, fallback_len: int) -> int:
    if not isinstance(prev_snapshot, dict) or "models" not in prev_snapshot:
        return fallback_len
    return sum(1 for m in prev_snapshot.get("models", []) if m and m.get("is_docs_model"))


def _write_outputs(
    rows_sorted: list[dict],
    pareto_ids: set,
    added_ids: set,
    removed_ids: set,
    removed_models: list[dict],
    prev_snapshot,
    data_label: str,
    role_recs: dict,
    verbose: bool,
) -> None:
    live = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "sources": {
            "commandcode_docs": CC_DOCS,
            "openrouter_api": OPENROUTER_API,
            "artificial_analysis": AA_URL,
            "lmarena": LMARENA_URL,
            "usage_limits": f"{CC_DOCS}#usage-limits",
            "account_caps": {"cap_5h": ACC_5H, "cap_week": ACC_WK, "cap_month": ACC_MO},
            "note": "per-model caps = $14*credits/70 (5h), $35*credits/70 (wk), credits (mo); credits from GOAT pricing tables",
        },
        "catalog_diff": {
            "added": sorted(added_ids),
            "removed": sorted(removed_ids),
            "total_current": len(rows_sorted),
            "total_previous": _prev_docs_count(prev_snapshot, len(rows_sorted)),
        },
        "role_recommendations": role_recs,
        "models": rows_sorted,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    out_json = DATA / "cc_live.json"
    cb_json = OUT / "cc_cost_benefit.json"
    html_path = OUT / "cc_cost_benefit.html"
    bc.atomic_write_text(out_json, json.dumps(live, indent=2))
    bc.atomic_write_text(cb_json, json.dumps(rows_sorted, indent=2))
    html_txt = render_html(
        rows_sorted,
        work_sentence=one_sentence_work(rows_sorted),
        pareto_ids=pareto_ids,
        added_ids=added_ids,
        removed_models=removed_models,
        data_note=data_label,
        role_recs=role_recs,
    )
    bc.atomic_write_text(html_path, html_txt)
    if verbose:
        print(f"wrote {out_json.relative_to(ROOT)}, {cb_json.relative_to(ROOT)}, {html_path.relative_to(ROOT)}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Command Code GOAT catalog checker (offline cache by default; live only with --fetch)")
    ap.add_argument("--fetch", "--refresh", action="store_true", help="Live-fetch GOAT docs + OpenRouter/AA/LMArena snapshots")
    ap.add_argument("--check", action="store_true", help="Print only: writes NOTHING (even with --fetch)")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging")
    ap.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors")
    ap.add_argument("--slim", action="store_true", help="Force compact table layout")
    ap.add_argument("--wide", action="store_true", help="Force full table layout")
    ap.add_argument(
        "--sort",
        choices=["value", "qvi", "avi", "fgi", "bfi", "cap", "quality", "reqmo", "req5h", "cost", "intel", "intel-cc"],
        default="value",
        help="Sort order (default: value)",
    )
    return ap.parse_args()


def _gather_inputs(do_fetch: bool, do_write: bool, verbose: bool) -> tuple[dict, dict, dict, dict, str]:
    data_label = "live fetch"
    if not do_fetch:
        note, data_label = bc.offline_snapshot_note(RAW, _SNAP_LABELS)
        print(note)
    pl, rl, il, fetched = _fetch_live_sources(do_write, verbose) if do_fetch else ({}, {}, {}, {})
    if not pl:
        pl, rl_off, il_off = _load_offline_docs(verbose)
        rl = rl or rl_off
        il = il or il_off
    return pl, rl, il, fetched, data_label


def main():
    args = _parse_args()
    do_fetch, do_write = bool(args.fetch), not args.check
    mode_tag = "fetch (network)" if do_fetch else "OFFLINE (cache-only)"
    check_tag = " · check: no writes" if args.check else ""
    print(f"Command Code GOAT — catalog check\n  date: {dt.datetime.now(dt.UTC).isoformat()}\n  mode: {mode_tag}{check_tag}")

    pricing_live, reqs_live, intel_live, fetched_maps, data_label = _gather_inputs(do_fetch, do_write, args.verbose)
    cc_ids, merged_pricing = _merge_pricing(pricing_live)
    maps = _load_source_maps(fetched_maps, args.verbose)
    rows = [_build_model_row(mid, merged_pricing[mid], reqs_live, intel_live, maps) for mid in cc_ids]
    bc.score_analyzer_rows(rows)

    rows_sorted = sorted(rows, key=build_sort_key(args.sort, _eff_cost))
    pareto_ids = bc.compute_pareto_ids(rows_sorted, _eff_cost, set(pricing_live.keys()) | DOCS_IDS)
    prev_snapshot = bc.load_previous_snapshot(DATA / "cc_live.json")
    catalog_diff = bc.diff_model_catalog(rows_sorted, prev_snapshot)
    rows_sorted = catalog_diff["rows"]
    role_recs = bc.compute_role_recommendations(rows_sorted, context="ccheck")

    slim_opt = True if args.slim else (False if args.wide else None)
    print("\n" + render_cli_table(
        rows_sorted,
        pareto_ids=pareto_ids,
        added_ids=catalog_diff["added_ids"],
        removed_models=catalog_diff["removed_models"],
        color=not (args.plain or os.getenv("NO_COLOR")),
        slim=slim_opt,
        wide=args.wide,
        role_recs=role_recs,
    ))
    if do_write:
        _write_outputs(
            rows_sorted, pareto_ids, catalog_diff["added_ids"], catalog_diff["removed_ids"],
            catalog_diff["removed_models"], prev_snapshot, data_label, role_recs, args.verbose,
        )
    else:
        print("\n(check-only, no files written)")


if __name__ == "__main__":
    main()
