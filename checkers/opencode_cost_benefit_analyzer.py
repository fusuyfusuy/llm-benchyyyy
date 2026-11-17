#!/usr/bin/env python3
"""OpenCode Go catalog & cost/benefit analyzer (`ocheck`).

Checks OpenCode Go (https://opencode.ai/v2/docs/console/go/) models against
Artificial Analysis, LMArena, LiveBench, and OpenRouter benchmarks under shared
percentage allowances (5h=20%, wk=50%, mo=100%). Offline by default; --fetch is
the only network path.
"""

import argparse
import datetime as dt
import html as html_lib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
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

OCGO_DOCS = bc.OCGO_DOCS
OCGO_API = "https://opencode.ai/zen/go/v1/models"
OCGO_USAGE_API = "https://opencode.ai/zen/go/v1/usage"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
LMARENA_URL = "https://arena.ai/leaderboard/code/webdev"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

_SNAP_LABELS = (
    ("docs", "opencode_go_docs"),
    ("OpenCode API", "opencode_go_models"),
    ("OpenRouter", "openrouter_models"),
    ("AA", "artificial_analysis"),
    ("LMArena", "lmarena"),
    ("LiveBench", "livebench_2"),
)

FALLBACK_PRICING = {
    "grok-4.6": {"input": 2.00, "output": 6.00, "cached_read": 0.50, "cached_write": None, "usage": 15},
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cached_read": 0.02, "cached_write": 0.25, "usage": 15},
    "glm-5.3-flash": {"input": 0.15, "output": 0.50, "cached_read": 0.03, "cached_write": None, "usage": 15},
    "glm-5.3": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 15},
    "glm-5.2": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "glm-5.1": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "kimi-k3": {"input": 3.00, "output": 15.00, "cached_read": 0.30, "cached_write": None, "usage": 15},
    "kimi-k2.7-code": {"input": 0.95, "output": 4.00, "cached_read": 0.19, "cached_write": None, "usage": 60},
    "kimi-k2.6": {"input": 0.95, "output": 4.00, "cached_read": 0.16, "cached_write": None, "usage": 60},
    "mimo-v2.5": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "mimo-v2.5-pro": {"input": 0.435, "output": 0.87, "cached_read": 0.003625, "cached_write": None, "usage": 15},
    "minimax-m3": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": None, "usage": 60},
    "minimax-m2.7": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": 0.375, "usage": 60},
    "minimax-m2.5": {"input": 0.30, "output": 1.20, "cached_read": 0.06, "cached_write": 0.375, "usage": 60},
    "muse-spark-1.2-contributor": {"input": 0.10, "output": 0.20, "cached_read": 0.002, "cached_write": None, "usage": 60},
    "muse-spark-1.3-contributor": {"input": 0.10, "output": 0.20, "cached_read": 0.002, "cached_write": None, "usage": 60},
    "qwen3.8-max": {"input": 2.00, "output": 6.00, "cached_read": 0.25, "cached_write": 2.50, "usage": 15},
    "qwen3.8-flash": {"input": 0.15, "output": 0.47, "cached_read": 0.016, "cached_write": 0.20, "usage": 30},
    "qwen3.7-max": {"input": 2.50, "output": 7.50, "cached_read": 0.50, "cached_write": 3.125, "usage": 30},
    "qwen3.7-plus": {"input": 0.40, "output": 1.60, "cached_read": 0.04, "cached_write": 0.50, "usage": 60},
    "qwen3.6-plus": {"input": 0.50, "output": 3.00, "cached_read": 0.05, "cached_write": 0.625, "usage": 60},
    "deepseek-v4-pro": {"input": 0.66, "output": 1.98, "cached_read": 0.022, "cached_write": None, "usage": 15},
    "deepseek-v4-flash": {"input": 0.22, "output": 0.66, "cached_read": 0.007, "cached_write": None, "usage": 30},
    "deepseek-v4.1-flash": {"input": 0.15, "output": 0.60, "cached_read": 0.003, "cached_write": None, "usage": 100},
    "deepseek-flash": {"input": 0.15, "output": 0.60, "cached_read": 0.003, "cached_write": None, "usage": 15},
    "deepseek-v4-flash-vision-exp": {"input": 0.22, "output": 0.66, "cached_read": 0.007, "cached_write": None, "usage": 15},
    "hy4-preview": {"input": 0.834, "output": 2.501, "cached_read": 0.042, "cached_write": None, "usage": 30},
    "hy3": {"input": 0.14, "output": 0.58, "cached_read": 0.035, "cached_write": None, "usage": 60},
    "longcat-2.0": {"input": 0.30, "output": 1.20, "cached_read": 0.006, "cached_write": None, "usage": 60},
    "omen-alpha": {"input": 0.20, "output": 0.66, "cached_read": 0.04, "cached_write": None, "usage": 100},
    "grok-4.5": {"input": 2.00, "output": 6.00, "cached_read": 0.30, "cached_write": None, "usage": 15},
    "glm-5": {"input": 1.40, "output": 4.40, "cached_read": 0.26, "cached_write": None, "usage": 60},
    "kimi-k2.5": {"input": 0.95, "output": 4.00, "cached_read": 0.16, "cached_write": None, "usage": 60},
    "mimo-v2-pro": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "mimo-v2-omni": {"input": 0.14, "output": 0.28, "cached_read": 0.0028, "cached_write": None, "usage": 60},
    "qwen3.5-plus": {"input": 0.40, "output": 1.60, "cached_read": 0.04, "cached_write": 0.50, "usage": 60},
    "hy3-preview": {"input": 0.14, "output": 0.58, "cached_read": 0.035, "cached_write": None, "usage": 60},
}

DOCS_IDS = {
    "grok-4.6", "gpt-5.6-luna", "glm-5.3-flash", "glm-5.3", "glm-5.2", "glm-5.1",
    "kimi-k3", "kimi-k2.7-code", "kimi-k2.6", "mimo-v2.5", "mimo-v2.5-pro",
    "minimax-m3", "minimax-m2.7", "minimax-m2.5", "muse-spark-1.2-contributor",
    "muse-spark-1.3-contributor", "qwen3.8-max", "qwen3.8-flash", "qwen3.7-max",
    "qwen3.7-plus", "qwen3.6-plus", "deepseek-v4-pro", "deepseek-v4-flash",
    "deepseek-v4.1-flash", "deepseek-v4-flash-vision-exp", "hy4-preview", "hy3",
    "longcat-2.0", "omen-alpha",
}

FALLBACK_TOKENS = {
    "grok-4.6": (390, 32500, 120),
    "glm-5.3-flash": (1000, 55000, 200),
    "glm-5.3": (700, 52000, 150),
    "glm-5.2": (700, 52000, 150),
    "glm-5.1": (700, 52000, 150),
    "gpt-5.6-luna": (1000, 50000, 220),
    "kimi-k3": (1050, 76500, 300),
    "kimi-k2.7-code": (870, 55000, 200),
    "kimi-k2.6": (870, 55000, 200),
    "mimo-v2.5": (830, 71500, 295),
    "mimo-v2.5-pro": (790, 86000, 305),
    "minimax-m3": (510, 56000, 190),
    "minimax-m2.7": (300, 55000, 125),
    "minimax-m2.5": (300, 55000, 125),
    "muse-spark-1.2-contributor": (620, 71400, 300),
    "muse-spark-1.3-contributor": (620, 71400, 300),
    "qwen3.8-max": (420, 66000, 200),
    "qwen3.8-flash": (600, 58000, 200),
    "qwen3.7-max": (420, 66000, 200),
    "qwen3.7-plus": (500, 57000, 190),
    "qwen3.6-plus": (500, 57000, 190),
    "deepseek-v4-pro": (750, 82000, 290),
    "deepseek-v4-flash": (410, 71300, 310),
    "deepseek-v4.1-flash": (410, 71300, 310),
    "deepseek-flash": (410, 71300, 310),
    "deepseek-v4-flash-vision-exp": (410, 71300, 310),
    "hy4-preview": (830, 71500, 295),
    "hy3": (830, 71500, 295),
    "longcat-2.0": (920, 88900, 200),
    "omen-alpha": (300, 40000, 100),
    "grok-4.5": (1100, 71500, 220),
    "glm-5": (700, 52000, 150),
    "kimi-k2.5": (870, 55000, 200),
    "mimo-v2-pro": (830, 71500, 295),
    "mimo-v2-omni": (830, 71500, 295),
    "qwen3.5-plus": (500, 57000, 190),
    "hy3-preview": (830, 71500, 295),
}

_MODEL_ID_MAP = {
    "grok 4.6": "grok-4.6",
    "gpt 5.6 luna": "gpt-5.6-luna",
    "glm-5.3-flash": "glm-5.3-flash",
    "glm-5.3": "glm-5.3",
    "glm-5.2": "glm-5.2",
    "glm-5.1": "glm-5.1",
    "kimi k3": "kimi-k3",
    "kimi k2.7 code": "kimi-k2.7-code",
    "kimi k2.6": "kimi-k2.6",
    "mimo v2.5": "mimo-v2.5",
    "mimo v2.5 pro": "mimo-v2.5-pro",
    "mimo-v2.5": "mimo-v2.5",
    "mimo-v2.5-pro": "mimo-v2.5-pro",
    "minimax m3": "minimax-m3",
    "minimax m2.7": "minimax-m2.7",
    "minimax m2.5": "minimax-m2.5",
    "muse spark 1.2 contributor": "muse-spark-1.2-contributor",
    "muse spark 1.3 contributor": "muse-spark-1.3-contributor",
    "qwen3.8 max": "qwen3.8-max",
    "qwen3.8 flash": "qwen3.8-flash",
    "qwen3.7 max": "qwen3.7-max",
    "qwen3.7 plus": "qwen3.7-plus",
    "qwen3.6 plus": "qwen3.6-plus",
    "deepseek v4 pro": "deepseek-v4-pro",
    "deepseek v4 flash": "deepseek-v4-flash",
    "deepseek v4.1 flash": "deepseek-v4.1-flash",
    "deepseek-v4.1-flash": "deepseek-v4.1-flash",
    "deepseek flash": "deepseek-flash",
    "deepseek-flash": "deepseek-flash",
    "deepseek v4 flash vision exp": "deepseek-v4-flash-vision-exp",
    "hy4 preview": "hy4-preview",
    "hy3": "hy3",
    "longcat 2.0": "longcat-2.0",
    "longcat-2.0": "longcat-2.0",
    "longcat": "longcat-2.0",
    "omen alpha": "omen-alpha",
}

_SLIM_CLI_HEADERS = [
    ("Rank", 4, "^"), ("Model", 20, "<"), ("Limit", 6, "^"), ("Req/Mo", 7, ">"),
    ("Q(Cap)", 6, ">"), ("P(Succ)", 7, ">"), ("Eff c/r", 7, ">"), ("Val", 6, ">"),
    ("AVI", 7, ">"), ("FGI", 5, ">"), ("Remain", 10, "^"),
]

_WIDE_CLI_HEADERS = [
    ("Rank", 4, "^"), ("Model", 22, "<"), ("Limit", 6, "^"), ("Req/Mo", 7, ">"),
    ("Q(Cap)", 6, ">"), ("P(Succ)", 7, ">"), ("Eff c/r", 7, ">"), ("Value", 6, ">"),
    ("AVI", 7, ">"), ("FGI", 5, ">"), ("Remain", 10, "^"), ("Lev", 4, ">"),
]

_WIN_HEADERS = [
    ("Window", 14, "<"), ("Budget Cap", 11, ">"), ("Used (%)", 10, ">"),
    ("Balance ($)", 12, ">"), ("Status", 10, "^"), ("Resets At / Countdown", 34, "<"),
]

_SLIM_MOD_HEADERS = [
    ("Model", 18, "<"), ("Tier", 6, "^"), ("5h Cap", 6, ">"), ("5h Limit", 8, ">"),
    ("Wk Limit", 8, ">"), ("Mo Limit", 8, ">"), ("5h Rem", 9, ">"), ("Mo Rem", 9, ">"),
    ("Cost/Req", 8, ">"), ("Pricing ($/1M)", 18, "<"),
]

_WIDE_MOD_HEADERS = [
    ("Model", 22, "<"), ("Tier", 6, "^"), ("5h Cap", 6, ">"), ("5h Limit", 8, ">"),
    ("Wk Limit", 8, ">"), ("Mo Limit", 8, ">"), ("5h Rem", 11, ">"), ("Mo Rem", 11, ">"),
    ("Cost/Req", 8, ">"), ("Pricing ($/1M In · Out · CR · CW)", 26, "<"),
]

_WINDOW_DEFS = (("rolling", "5h Rolling", 12.00), ("weekly", "Weekly", 30.00), ("monthly", "Monthly", 60.00))
_RANK_MEDALS = {1: ("🥇#1", C_GOLD), 2: ("🥈#2", C_SILVER), 3: ("🥉#3", C_BRONZE)}
_EFF_LADDER = [(lambda v: v < 0.002, C_GREEN), (lambda v: v < 0.01, C_CYAN), (lambda v: v < 0.03, C_YELLOW)]
_PCT_ANSI_LADDER = [(lambda v: v > 50, "\033[38;5;48m"), (lambda v: v > 25, "\033[38;5;221m"), (lambda v: v > 10, "\033[38;5;205m")]

_CLI_GUIDE_ITEMS = [
    ("Gold Bold", "Pareto Frontier (undefeated capability vs cost).", C_GOLD),
    ("Green (+)", "Newly added model to OpenCode Go docs or API.", C_GREEN),
    ("Badges ¹²³", "🥇/🥈/🥉 Rank-1/2/3 leaders per metric column.", C_YELLOW),
    ("Shared Pool", "All models share 20% (5h) · 50% (wk) · 100% (mo) pool; Limit = model drain denominator.", C_WHITE),
    ("$15/mo Tier", "Kimi K3, GLM-5.3, Grok 4.6 — flagship reasoning models.", C_YELLOW),
    ("$30/mo Tier", "DeepSeek V4 Flash (~38k req/mo) — daily driver iterative coder.", C_CYAN),
    ("$60/mo Tier", "MiMo-V2.5 (~150k), Muse Spark (~227k), LongCat (~80k) — bulk fills.", C_GREEN),
    ("Eff c/r", "Real Cost/Task = Base cost/req × retry multiplier (T_mult).", C_WHITE),
    ("Allowed Limits", "Run 'ocheck --limits' for full multi-window allowed request caps & quota balance.", C_WHITE),
]

_HTML_COLS = [
    "model", "$Usage/mo", "$c/req", "req/5h", "req/wk", "req/mo", "Q(Cap)",
    "P(Succ)", "Eff c/r", "Value", "AVI (ROI)", "FGI (Gate)", "AA intel",
    "AA cod", "LMArena", "int/$", "$c/int", "lev", "remain",
]

_PLAN_ALIASES = {"go-plus": "go-plus", "go plus": "go-plus", "plus": "go-plus"}


def _sf(val, default=None):
    return bc._safe_float(val, default=default, strip_currency=False)


def _si(val, default=None):
    return bc._safe_int(val, default=default, strip_currency=False)


def _si_round(val) -> int | None:
    return int(round(val)) if bc._is_num(val) else None


def _tier_color(usage_cap) -> str:
    if usage_cap is None:
        return C_GRAY
    if usage_cap >= 60:
        return C_GREEN
    if usage_cap >= 30:
        return C_CYAN
    return C_YELLOW if usage_cap >= 15 else C_GRAY


def _eff_price(cell: str) -> float | None:
    strong = re.search(r"<strong>.*?\$([\d.]+)", cell or "", flags=re.S)
    if strong:
        try:
            return float(strong.group(1))
        except ValueError:
            pass
    nums = re.findall(r"\$([\d.]+)", re.sub(r"<[^>]+>", " ", cell or ""))
    if nums:
        try:
            return float(nums[-1])
        except ValueError:
            return None
    return bc.parse_price(cell)


def _eff_count(cell: str) -> int | None:
    strong = re.search(r"<strong>\s*([\d,]+)", cell or "", flags=re.S)
    if strong:
        try:
            return int(strong.group(1).replace(",", ""))
        except ValueError:
            pass
    nums = re.findall(r"[\d][\d,]*", re.sub(r"<[^>]+>", " ", cell or ""))
    if nums:
        try:
            return int(nums[-1].replace(",", ""))
        except ValueError:
            return None
    return None


def model_to_id(raw: str) -> str | None:
    """Normalize a docs display model name to its canonical OpenCode Go id."""
    cleaned = re.split(r"·", raw.strip())[0].strip()
    cleaned = re.sub(r"\s*\d+(?:\.\d+)?x\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\([^)]*\)", "", cleaned).strip()
    low = cleaned.lower()
    if low in _MODEL_ID_MAP:
        return _MODEL_ID_MAP[low]
    generic = re.sub(r"-+", "-", low.replace(" ", "-").replace("_", "-")).strip("-")
    for key in FALLBACK_PRICING:
        if key.replace(".", "-") == generic.replace(".", "-"):
            return key
    if re.match(r"^[a-z0-9][a-z0-9\.\-]*$", generic) and len(generic) >= 2:
        return generic
    return None


def _table_header(tbl: str) -> str:
    m = re.search(r"<tr[^>]*>(.*?)</tr>", tbl, flags=re.S)
    return re.sub(r"<[^>]+>", " ", m.group(1)).lower() if m else ""


def _pick_plan_tables(html: str, plan: str) -> tuple[str | None, str | None]:
    plan_norm = _PLAN_ALIASES.get(plan.strip().lower(), plan.strip().lower())
    panels = bc.extract_panels_by_plan(html, plan_norm)
    panel_tables = [t for p in panels for t in re.findall(r"<table.*?</table>", p, flags=re.S)]
    pool = panel_tables if panel_tables else re.findall(r"<table.*?</table>", html, flags=re.S)
    price_tbl = next((t for t in pool if "cached write" in _table_header(t)), None)
    req_tbl = next((t for t in pool if "requests per 5 hour" in _table_header(t)), None)
    if price_tbl is None and len(panel_tables) >= 1:
        price_tbl = panel_tables[0]
    if req_tbl is None and len(panel_tables) >= 2:
        req_tbl = panel_tables[1]
    return price_tbl, req_tbl


def _parse_pricing_tbl(price_tbl: str | None, verbose: bool) -> dict:
    pricing: dict = {}
    if not price_tbl:
        return pricing
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", price_tbl, flags=re.S)[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
        if len(cells) < 6:
            continue
        mid = model_to_id(re.sub(r"<[^>]+>", "", cells[0]).strip())
        if not mid or mid in pricing:
            continue
        pricing[mid] = {
            "input": _eff_price(cells[1]),
            "output": _eff_price(cells[2]),
            "cached_read": _eff_price(cells[3]),
            "cached_write": _eff_price(cells[4]),
            "usage": _eff_price(cells[5]),
        }
        if verbose and mid in ("grok-4.6", "glm-5.3", "hy3"):
            print(f"    pricing {mid}: {pricing[mid]}")
    return pricing


def _parse_req_tbl(req_tbl: str | None) -> dict:
    requests: dict = {}
    if not req_tbl:
        return requests
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", req_tbl, flags=re.S)[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
        if len(cells) < 4:
            continue
        mid = model_to_id(re.sub(r"<[^>]+>", "", cells[0]))
        if mid:
            requests[mid] = {
                "per_5h": _eff_count(cells[1]),
                "per_week": _eff_count(cells[2]),
                "per_month": _eff_count(cells[3]),
            }
    return requests


def _assign_token_part(part: str, base_mid: str | None, est: tuple[int, int, int], tokens: dict) -> None:
    if re.fullmatch(r"[\d.]+", part) and base_mid:
        mid = model_to_id(f"{base_mid.split('-')[0]} {part}")
    else:
        mid = model_to_id(part)
    if mid:
        tokens[mid] = est
    elif "kimi k2.7" in part.lower() or "kimi k2.6" in part.lower():
        for k in ("kimi-k2.7-code", "kimi-k2.6"):
            tokens[k] = est


def _parse_token_estimates(html: str) -> dict:
    tokens: dict = {}
    ul = re.search(r"(?:following\s+)?token counts per request.*?<ul>(.*?)</ul>", html, flags=re.S)
    if not ul:
        ul = re.search(r"requests per month.*?</table>(.*?)<h2", html, flags=re.S)
    if not ul:
        return tokens
    for li in re.findall(r"<li[^>]*>(.*?)</li>", ul.group(1), flags=re.S):
        txt = re.sub(r"<[^>]+>", "", li).strip()
        m = re.search(r"([\d,]+)\s+input.*?([\d,]+)\s+cached.*?([\d,]+)\s+output", txt)
        if not m:
            continue
        est = tuple(int(m.group(i).replace(",", "")) for i in (1, 2, 3))
        model_part = re.split(r"\s+[—–-]\s+", txt)[0].strip()
        parts = [p.strip() for p in re.split(r"\s*/\s*", model_part) if p.strip()]
        base_mid = model_to_id(parts[0]) if parts else None
        for part in parts:
            _assign_token_part(part, base_mid, est, tokens)
    return tokens


def parse_ocgo_docs(html: str, verbose: bool = False, plan: str = "go") -> tuple[dict, dict, dict]:
    """Parse pricing, request estimates, and token assumptions from Go docs HTML."""
    price_tbl, req_tbl = _pick_plan_tables(html, plan)
    pricing = _parse_pricing_tbl(price_tbl, verbose)
    requests = _parse_req_tbl(req_tbl)
    tokens = _parse_token_estimates(html)
    for mid in pricing:
        if mid not in tokens and mid in FALLBACK_TOKENS:
            tokens[mid] = FALLBACK_TOKENS[mid]
    return pricing, requests, tokens


def _lookup_provider_key(d) -> str | None:
    if not isinstance(d, dict):
        return None
    for name in ("opencode-go", "opencode"):
        entry = d.get(name)
        if isinstance(entry, dict):
            key = entry.get("key") or entry.get("token")
            if key:
                return str(key).strip()
    return None


def _read_auth_key(path: Path, warn_missing: bool) -> str | None:
    if not path.exists():
        return None
    try:
        key = _lookup_provider_key(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN {path}: unreadable auth.json: {exc}", file=sys.stderr)
        return None
    if key:
        return key
    if warn_missing:
        print(f"  WARN {path}: no opencode-go/opencode provider entry", file=sys.stderr)
    return None


def get_api_key() -> str | None:
    """Resolve OpenCode Go API key from env vars or opencode-specific auth.json entries."""
    for env_var in ("OPENCODE_GO_API_KEY", "OPENCODE_API_KEY", "OPENCODE_GO_KEY"):
        val = os.environ.get(env_var)
        if val:
            return val.strip()
    candidates = [
        (Path.home() / ".pi" / "agent" / "auth.json", False),
        (Path.home() / ".local" / "share" / "opencode" / "auth.json", True),
        (Path.home() / ".config" / "opencode" / "auth.json", True),
    ]
    for path, warn in candidates:
        key = _read_auth_key(path, warn)
        if key:
            return key
    return None


def fetch_usage(key: str | None, verbose: bool = False):
    """Fetch authenticated OpenCode Go quota telemetry."""
    if not key:
        return None, "no key"
    req = urllib.request.Request(OCGO_USAGE_API, headers={"User-Agent": UA, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
            usage = data.get("usage", data) if isinstance(data, dict) else data
            if verbose:
                print(f"  usage: HTTP {resp.status}")
            return usage, None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:200] if hasattr(exc, "read") else str(exc)
        return None, f"HTTP {exc.code}: {body}"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def extract_usage_windows(usage_raw) -> tuple[dict, dict]:
    """Extract percent-used and reset ISO strings from a /zen/go/v1/usage payload."""
    percents, resets = {}, {}
    if not isinstance(usage_raw, dict):
        return percents, resets
    for w in ("rolling", "weekly", "monthly"):
        ww = usage_raw.get(w)
        if not isinstance(ww, dict):
            continue
        pct = _sf(ww.get("percent", ww.get("usedPercent", ww.get("used", 0))))
        if pct is not None:
            percents[w] = pct
        rst = ww.get("resetsAt") or ww.get("resetAt")
        if rst is not None:
            resets[w] = rst
    return percents, resets


def format_countdown(iso_str: str | None) -> str:
    """Format an ISO timestamp into a concise relative reset countdown."""
    if not iso_str:
        return "—"
    target = bc.parse_iso_utc(iso_str)
    if target is None:
        return str(iso_str)[:16].replace("T", " ")
    rel = bc.format_relative_time(target, dt.datetime.now(dt.UTC))
    time_part = target.strftime("%Y-%m-%d %H:%M UTC")
    return "resets now" if rel == "now" else f"in {rel} ({time_part})"


def build_sort_key(sort_mode: str, eff_cost_fn):
    return bc.build_analyzer_sort_key(sort_mode, eff_cost_fn)


def _req_field(row: dict, doc_k: str, comp_k: str):
    reqs = row.get("requests", {})
    val = reqs.get(doc_k)
    return val if val is not None else reqs.get(comp_k)


def _max_val_row(rows: list[dict], section: str, key: str) -> tuple[dict | None, float]:
    best, best_v = None, -1.0
    for row in rows:
        val = row.get(section, {}).get(key)
        if bc._is_num(val) and val > best_v:
            best, best_v = row, float(val)
    return best, best_v


def _cli_banner_summary(models_list: list[dict], is_slim: bool, usage_note: str) -> str:
    top_val, tv = _max_val_row(models_list, "value", "qvi_score")
    top_fgi, tf = _max_val_row(models_list, "value", "fgi_score")
    top_req = max(models_list, key=lambda m: _req_field(m, "per_month_docs", "per_month_computed") or 0) if models_list else None
    v_info = f"Top Val: {top_val['model_id'][:14]} (Val {tv:.1f})" if top_val else ""
    f_info = f"Frontier: {top_fgi['model_id'][:14]} (FGI {tf:.1f})" if top_fgi else ""
    req_cnt = (_req_field(top_req, "per_month_docs", "per_month_computed") or 0) if top_req else 0
    s_info = f"Max Bulk: {top_req['model_id'][:12]} ({bc.format_compact_num(req_cnt)}/mo)" if top_req else ""
    u_part = f" │ Usage: {usage_note}" if usage_note else ""
    base = f" Shared Allowance (20% 5h · 50% wk · 100% mo) │ {v_info} │ {f_info}"
    return (base if is_slim else f"{base} │ {s_info}") + u_part


def _remain_cell(row: dict, usage_err, usage_key_present: bool, has_usage: bool) -> tuple[str, str]:
    rem = row.get("remaining", {})
    overall, overall_req = rem.get("overall_pct"), rem.get("overall_req")
    if overall is not None:
        txt = f"{overall:.0f}%({bc.format_compact_num(overall_req)})" if overall_req is not None else f"{overall:.0f}%"
        col = C_GREEN if overall > 50 else (C_YELLOW if overall > 25 else C_MAGENTA)
        return txt, col
    if usage_key_present and usage_err:
        return "ERR", C_DIM
    return ("N/A" if (not usage_key_present and not has_usage) else "—"), C_DIM


def _score_spec(val, fmt: str, medal: int | None, col_fn, width: int, color: bool) -> tuple[str, str, int, str]:
    if val is None:
        return "—", C_DIM, width, ">"
    return fmt.format(val) + bc.medal_badge(medal, color=color), col_fn(val), width, ">"


def _cli_prefix_specs(idx: int, row: dict, ctx: dict) -> list[tuple[str, str, int, str]]:
    rank = idx + 1
    rank_s, rank_col = _RANK_MEDALS.get(rank, (f" #{rank}", C_WHITE))
    mid = row["model_id"]
    is_added = mid in ctx["added_ids"]
    name_w = 20 if ctx["is_slim"] else 22
    mid_disp = (f"+{mid}" if is_added else mid)[:name_w]
    mid_col = (C_BOLD + C_GREEN) if is_added else ((C_BOLD + C_GOLD) if mid in ctx["pareto_ids"] else C_WHITE)
    usage = row["pricing"]["monthly_usage_limit_usd"]
    req_mo = _req_field(row, "per_month_docs", "per_month_computed")
    req_col = C_CYAN if (req_mo is not None and req_mo >= 15000) else C_WHITE
    return [
        (rank_s, C_BOLD + rank_col, 4, "^"),
        (mid_disp, mid_col, name_w, "<"),
        (f"${usage:.0f}/m" if usage is not None else "Free", _tier_color(usage), 6, "^"),
        (bc.format_compact_num(req_mo), req_col, 7, ">"),
    ]


def _cli_row_specs(idx: int, row: dict, ctx: dict) -> tuple[list[tuple[str, str, int, str]], str]:
    bm, val = row["benchmarks"], row["value"]
    meds = ctx["col_medals"].get(row["model_id"], {})
    eff_c = val.get("effective_cost_per_request")
    rem_s, rem_col = _remain_cell(row, ctx["usage_err"], ctx["usage_key_present"], ctx["has_usage"])
    color = ctx["color"]

    specs = _cli_prefix_specs(idx, row, ctx) + [
        _score_spec(bm.get("capability_q"), "{:.1f}", meds.get("q"), bc.score_color_q, 6, color),
        _score_spec(bm.get("p_success"), "{:.1f}%", meds.get("psucc"), bc.score_color_p, 7, color),
        (f"${eff_c:.4f}" if eff_c is not None else "—", bc.color_ladder(eff_c, _EFF_LADDER, default_color=C_MAGENTA), 7, ">"),
        _score_spec(val.get("qvi_score"), "{:.1f}", meds.get("value"), bc.score_color_qvi, 6, color),
        _score_spec(val.get("avi_score"), "{:.1f}", meds.get("avi"), bc.score_color_avi, 7, color),
        _score_spec(val.get("fgi_score"), "{:.1f}", meds.get("fgi"), bc.score_color_fgi, 5, color),
        (rem_s, rem_col, 10, "^"),
    ]
    if not ctx["is_slim"]:
        lev = val.get("leverage_vs_10usd_sub")
        specs.append((f"{lev:.1f}x" if lev else "—", C_DIM, 4, ">"))
    return specs, (BG_ODD if idx % 2 == 1 else BG_EVEN)


def _format_row_line(specs: list[tuple[str, str, int, str]], bg: str, color: bool) -> str:
    if color:
        cells = [bc.color_cell(t, col, width=w, align=aln, bg=bg) for t, col, w, aln in specs]
        sep = f"{bg}{C_DIM}│{C_RESET}"
        return sep + sep.join(cells) + sep
    return " ".join(bc.pad_display(t, w, aln) for t, _, w, aln in specs)


def _table_chrome(headers: list, inner_w: int, color: bool) -> tuple[list[str], str]:
    if color:
        hdrs = [bc.color_cell(h, C_BOLD + C_WHITE, width=w, align=a, bg=BG_HEADER) for h, w, a in headers]
        sep = f"{BG_HEADER}{C_DIM}│{C_RESET}"
        head = [
            f"{C_DIM}┌{'┬'.join('─' * (w + 2) for _, w, _ in headers)}┐{C_RESET}",
            sep + sep.join(hdrs) + sep,
            f"{C_DIM}├{'┼'.join('─' * (w + 2) for _, w, _ in headers)}┤{C_RESET}",
        ]
        return head, f"{C_DIM}└{'┴'.join('─' * (w + 2) for _, w, _ in headers)}┘{C_RESET}"
    rule = "-" * (inner_w + 2)
    return [rule, " ".join(bc.pad_display(h, w, a) for h, w, a in headers), rule], rule


def _diff_banner(added_ids: set | None, removed_models: list[dict] | None) -> tuple[list[str], list[str]]:
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


def _cli_footer(models_list: list[dict], removed_models: list[dict] | None, role_recs, is_slim: bool, inner_w: int, color: bool) -> list[str]:
    out = []
    if removed_models:
        out.extend(["", *bc.render_removed_models_cli(removed_models, color=color, is_slim=is_slim, id_key="model_id")])
    out.extend(["", *bc.render_metric_guide_cli("OpenCode Go Metrics & Shared Quota Guide", _CLI_GUIDE_ITEMS, color=color)])
    recs = role_recs if role_recs is not None else bc.compute_role_recommendations(models_list, context="ocheck")
    if recs:
        out.extend(["", *bc.render_role_recommendations_cli(recs, color=color, is_slim=is_slim, width=inner_w)])
    return out


def _build_cli_ctx(models_list: list[dict], opts: dict) -> dict:
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
    return {**opts, "col_medals": col_medals}


def render_cli_table(
    models_list,
    usage_percents=None,
    usage_err=None,
    usage_key_present=False,
    pareto_ids=None,
    added_ids=None,
    removed_models=None,
    color=True,
    slim=None,
    wide=False,
    usage_note="",
    role_recs=None,
):
    is_slim = slim if slim is not None else (shutil.get_terminal_size((120, 24)).columns < 120 and not wide)
    headers = _SLIM_CLI_HEADERS if is_slim else _WIDE_CLI_HEADERS
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    diff_notices, diff_parts = _diff_banner(added_ids, removed_models)
    u_sfx = f" │ usage: {usage_note}" if usage_note else ""

    out = bc.render_banner_box(
        f"⚡ OPENCODE GO USAGE LIMITS & AGENTIC RADAR ({OCGO_DOCS}#usage-limits)",
        summary_lines=[_cli_banner_summary(models_list, is_slim, usage_note)],
        diff_notices=diff_notices,
        inner_w=inner_w,
        color=color,
        plain_title_line=f" OPENCODE GO USAGE LIMITS & AGENTIC RADAR — Shared Allowance (5h=20% · wk=50% · mo=100%){u_sfx}",
        plain_diff_parts=diff_parts,
    )
    head_lines, bot_line = _table_chrome(headers, inner_w, color)
    out.extend(head_lines)

    ctx = _build_cli_ctx(models_list, {
        "pareto_ids": pareto_ids or set(),
        "added_ids": added_ids or set(),
        "is_slim": is_slim,
        "color": color,
        "usage_err": usage_err,
        "usage_key_present": usage_key_present,
        "has_usage": bool(usage_percents),
    })
    out.extend(_format_row_line(*_cli_row_specs(i, r, ctx), color) for i, r in enumerate(models_list))
    out.append(bot_line)
    out.extend(_cli_footer(models_list, removed_models, role_recs, is_slim, inner_w, color))
    return "\n".join(out)


def _limits_chrome(headers: list, color: bool) -> tuple[list[str], str, str]:
    pipe = f"{C_CYAN}│{C_RESET}" if color else "|"
    if color:
        top = f"{C_CYAN}┌{'┬'.join('─' * (w + 2) for _, w, _ in headers)}┐{C_RESET}"
        sep = f"{C_CYAN}├{'┼'.join('─' * (w + 2) for _, w, _ in headers)}┤{C_RESET}"
        bot = f"{C_CYAN}└{'┴'.join('─' * (w + 2) for _, w, _ in headers)}┘{C_RESET}"
    else:
        top = sep = bot = "+" + "+".join("-" * (w + 2) for _, w, _ in headers) + "+"
    cells = [bc.color_cell(h, C_BOLD + C_WHITE, width=w, align=a) if color else f" {bc.pad_display(h, w, a)} " for h, w, a in headers]
    return [top, pipe + pipe.join(cells) + pipe, sep], bot, pipe


def _window_status(pct_used: float) -> tuple[str, str]:
    pct_rem = max(0.0, 100.0 - pct_used)
    if pct_rem > 50:
        return "● OK", C_GREEN
    return ("▲ WARN", C_YELLOW) if pct_rem > 20 else ("✖ CRIT", C_RED)


def _render_window_row(idx: int, w_def: tuple, usage_percents: dict, usage_resets: dict, usage_key_present: bool, color: bool, pipe: str) -> str:
    w_key, w_name, w_cap = w_def
    pct_used = usage_percents.get(w_key)
    bg = (BG_EVEN if idx % 2 == 0 else BG_ODD) if color else ""
    if pct_used is None:
        pct_s, bal_s, pct_col = "N/A", f"${w_cap:.2f}", C_DIM
        stat_s, stat_col = "—", C_GRAY
        rst_s = "No active key" if not usage_key_present else "N/A"
    else:
        pct_rem = max(0.0, 100.0 - pct_used)
        pct_s, bal_s = f"{pct_used:.0f}%", f"${w_cap * (pct_rem / 100.0):.2f}"
        pct_col = bc.color_ladder(pct_rem, _PCT_ANSI_LADDER, default_color="\033[38;5;196;1m")
        stat_s, stat_col = _window_status(pct_used)
        rst_s = format_countdown(usage_resets.get(w_key))
    bal_col = C_BOLD + (C_GREEN if (pct_used or 0) < 50 else C_YELLOW)
    specs = [
        (w_name, C_BOLD + C_WHITE, 14, "<"),
        (f"${w_cap:.2f}", C_CYAN, 11, ">"),
        (pct_s, pct_col, 10, ">"),
        (bal_s, bal_col, 12, ">"),
        (stat_s, stat_col, 10, "^"),
        (rst_s, C_DIM, 34, "<"),
    ]
    if color:
        return _format_row_line(specs, bg, True)
    return pipe + pipe.join(f" {bc.pad_display(t, w, a)} " for t, _, w, a in specs) + pipe


def _rem_label(rem_req, pct_rem, base_s: str, usage_cap, is_slim: bool) -> str:
    if rem_req is not None and pct_rem is not None:
        comp = bc.format_compact_num(rem_req)
        return comp if is_slim else f"{comp} ({pct_rem:.0f}%)"
    if usage_cap is None:
        return "Unlim" if is_slim else "Unlimited"
    return base_s


def _price_summary(pr: dict, is_slim: bool) -> str:
    inp_p, outp_p, cr_p, cw_p = pr.get("input_per_1m"), pr.get("output_per_1m"), pr.get("cached_read_per_1m"), pr.get("cached_write_per_1m")
    if inp_p is None:
        return "Free / Unpriced" if is_slim else "Free tier"
    out_v = outp_p or 0.0
    if is_slim:
        return f"${inp_p:.2f} · ${out_v:.2f}"
    cr_s = f" · ${cr_p:.3f}" if cr_p is not None else ""
    cw_s = f" · ${cw_p:.2f}w" if cw_p is not None else ""
    return f"${inp_p:.2f} / ${out_v:.2f}{cr_s}{cw_s}"


def _limit_req_triplet(row: dict) -> tuple[str, str, str]:
    r5 = _req_field(row, "per_5h_docs", "per_5h_computed")
    rw = _req_field(row, "per_week_docs", "per_week_computed")
    rm = _req_field(row, "per_month_docs", "per_month_computed")
    return (
        bc.format_compact_num(r5) if r5 is not None else "—",
        bc.format_compact_num(rw) if rw is not None else "—",
        bc.format_compact_num(rm) if rm is not None else "—",
    )


def _limit_model_specs(row: dict, is_slim: bool) -> list[tuple[str, str, int, str]]:
    pr = row.get("pricing", {})
    usage_cap = pr.get("monthly_usage_limit_usd")
    tier_s = f"${usage_cap:.0f}/m" if usage_cap is not None else "Free"
    cap5_s = f"${usage_cap * 0.20:.2f}" if usage_cap is not None else "Unlim"
    r5_s, rw_s, rm_s = _limit_req_triplet(row)
    rem = row.get("remaining", {})
    rem_d, pct_d = rem.get("requests", {}), rem.get("percent", {})
    rem_w = 9 if is_slim else 11
    mid_w = 18 if is_slim else 22
    c_req = row.get("cost_per_request_usd")
    return [
        (row["model_id"][:mid_w], C_BOLD + C_WHITE, mid_w, "<"),
        (tier_s, _tier_color(usage_cap), 6, "^"),
        (cap5_s, C_DIM, 6, ">"),
        (r5_s, C_BOLD + C_GREEN, 8, ">"),
        (rw_s, C_CYAN, 8, ">"),
        (rm_s, C_WHITE, 8, ">"),
        (_rem_label(rem_d.get("rolling"), pct_d.get("rolling"), r5_s, usage_cap, is_slim), C_YELLOW, rem_w, ">"),
        (_rem_label(rem_d.get("monthly"), pct_d.get("monthly"), rm_s, usage_cap, is_slim), C_DIM, rem_w, ">"),
        (f"${c_req:.4f}" if c_req is not None else "—", C_DIM, 8, ">"),
        (_price_summary(pr, is_slim), C_GRAY, 18 if is_slim else 26, "<"),
    ]


def _render_limit_model_row(idx: int, row: dict, is_slim: bool, color: bool, pipe: str) -> str:
    specs = _limit_model_specs(row, is_slim)
    if color:
        return _format_row_line(specs, BG_EVEN if idx % 2 == 0 else BG_ODD, True)
    return pipe + pipe.join(f" {bc.pad_display(t, w, a)} " for t, _, w, a in specs) + pipe


def _limits_footer(color: bool) -> list[str]:
    if not color:
        return [
            "OpenCode Go Limits & Tiering Guide:",
            "  • $15-$20/mo Tier ($3.00-$4.00/5h ceiling): High reasoning models.",
            "  • $30/mo Tier ($6.00/5h ceiling): Daily drivers (DeepSeek V4 Flash).",
            "  • $60-$100/mo Tier ($12.00-$20.00/5h ceiling): Bulk generation & high-cap Flash tiers.",
        ]
    return [
        f"🧭 {C_BOLD}OpenCode Go Limits & Tiering Guide:{C_RESET}",
        f"  • {C_YELLOW}$15–$20/mo Tier{C_RESET} {C_DIM}($3.00–$4.00/5h ceiling): High reasoning models (GLM-5.3, Kimi K3, Grok 4.6).{C_RESET}",
        f"  • {C_CYAN}$30/mo Tier{C_RESET} {C_DIM}($6.00/5h ceiling): Daily drivers (DeepSeek V4 Flash).{C_RESET}",
        f"  • {C_GREEN}$60–$100/mo Tier{C_RESET} {C_DIM}($12.00–$20.00/5h ceiling): Bulk generation (MiMo-V2.5, DeepSeek V4.1 Flash, Omen Alpha).{C_RESET}",
    ]


def _limits_win_section(usage_percents: dict, usage_resets: dict, usage_key_present: bool, usage_note: str, color: bool) -> list[str]:
    win_inner_w = sum(w + 2 for _, w, _ in _WIN_HEADERS) + len(_WIN_HEADERS) - 1
    top_banner = "⚡ OPENCODE GO SUBSCRIPTION POOLED WINDOWS & LIVE BALANCE"
    summary = ["Official limits: $12.00 / 5h rolling · $30.00 / weekly · $60.00 / monthly"]
    if usage_note:
        summary.append(f"Usage data source: {usage_note}")
    u_sfx = f" │ usage: {usage_note}" if usage_note else ""
    out = bc.render_banner_box(top_banner, summary_lines=summary, inner_w=win_inner_w, color=color, plain_title_line=f" {top_banner}{u_sfx}")
    w_head, w_bot, w_pipe = _limits_chrome(_WIN_HEADERS, color)
    out.extend(w_head)
    out.extend(_render_window_row(i, wd, usage_percents, usage_resets, usage_key_present, color, w_pipe) for i, wd in enumerate(_WINDOW_DEFS))
    out.extend([w_bot, ""])
    return out


def render_limits_table(
    models_list: list[dict],
    usage_percents: dict | None = None,
    usage_resets: dict | None = None,
    usage_key_present: bool = False,
    usage_note: str = "",
    color: bool = True,
    slim: bool | None = None,
    wide: bool = False,
) -> str:
    """Render OpenCode Go subscription pooled windows and per-model tier caps."""
    is_slim = slim if slim is not None else (shutil.get_terminal_size((120, 24)).columns < 120 and not wide)
    out = _limits_win_section(usage_percents or {}, usage_resets or {}, usage_key_present, usage_note, color)

    mod_headers = _SLIM_MOD_HEADERS if is_slim else _WIDE_MOD_HEADERS
    mod_inner_w = sum(w + 2 for _, w, _ in mod_headers) + len(mod_headers) - 1
    out.extend(bc.render_banner_box(
        "📋 OPENCODE GO MODEL ALLOWANCES & MULTI-WINDOW REQUEST LIMITS",
        summary_lines=["Cap formula: Window Limit = Window Pool ($12, $30, $60) * (Tier Cap / $60) / Cost_per_req"],
        inner_w=mod_inner_w,
        color=color,
        plain_title_line=" 📋 OPENCODE GO MODEL ALLOWANCES & MULTI-WINDOW REQUEST LIMITS",
    ))
    m_head, m_bot, m_pipe = _limits_chrome(mod_headers, color)
    out.extend(m_head)
    out.extend(_render_limit_model_row(i, r, is_slim, color, m_pipe) for i, r in enumerate(models_list))
    out.extend([m_bot, "", *_limits_footer(color)])
    return "\n".join(out)


def _fmt(val, pattern: str, fallback: str = "—") -> str:
    return pattern.format(val) if bc._is_num(val) else fallback


def _html_row_class(row: dict, pareto_ids: set, added_ids: set, aa_int, usage, ipd) -> str:
    if row["model_id"] in added_ids:
        return "added"
    if row["model_id"] in pareto_ids:
        return "pareto"
    if aa_int is not None and aa_int >= 58:
        return "flagship"
    if usage is not None and usage >= 60 and ipd is not None and ipd > 800:
        return "value"
    return "free" if usage is None else ""


def _rem_html_td(row: dict) -> str:
    rem = row.get("remaining", {})
    ov, ov_r = rem.get("overall_pct"), rem.get("overall_req")
    if ov is None:
        return '<td class="n">—</td>'
    rem_s = f"{ov:.0f}%" if ov_r is None else f"{ov:.0f}% ({ov_r})"
    rem_col = "#3fb950" if ov > 50 else ("#d29922" if ov > 25 else "#f85149")
    return f'<td class="n" style="color:{rem_col};font-weight:700;">{rem_s}</td>'


def _render_html_tr(row: dict, pareto_ids: set, added_ids: set) -> str:
    bm, val = row.get("benchmarks", {}), row.get("value", {})
    raw_mid = html_lib.escape(row["model_id"])
    mid = f'{raw_mid}<span class="badge badge-new">+NEW</span>' if row["model_id"] in added_ids else raw_mid
    usage = row["pricing"].get("monthly_usage_limit_usd")
    req5 = _req_field(row, "per_5h_docs", "per_5h_computed")
    reqw = _req_field(row, "per_week_docs", "per_week_computed")
    reqm = _req_field(row, "per_month_docs", "per_month_computed")
    aa_int, ipd = bm.get("aa_intelligence"), val.get("intelligence_per_dollar")
    cls = _html_row_class(row, pareto_ids, added_ids, aa_int, usage, ipd)
    lm_r = bm.get("lmarena_rank")
    lm_s = f"#{int(lm_r)}" if bc._is_num(lm_r) else "—"
    return (
        f'<tr class="{cls}"><td class="m">{mid}</td><td class="n">{_fmt(usage, "${:.0f}")}</td>'
        f'<td class="n">{_fmt(row.get("cost_per_request_usd"), "${:.5f}")}</td>'
        f'<td class="n">{_fmt(req5, "{:,}")}</td><td class="n">{_fmt(reqw, "{:,}")}</td><td class="n">{_fmt(reqm, "{:,}")}</td>'
        f'<td class="n" style="font-weight:700; color:#2563eb;">{_fmt(bm.get("capability_q"), "{:.1f}")}</td>'
        f'<td class="n">{_fmt(bm.get("p_success"), "{:.1f}%")}</td>'
        f'<td class="n">{_fmt(val.get("effective_cost_per_request"), "${:.5f}")}</td>'
        f'<td class="n" style="font-weight:700; color:#059669;">{_fmt(val.get("qvi_score"), "{:.1f}")}</td>'
        f'<td class="n" style="font-weight:700; color:#10b981;">{_fmt(val.get("avi_score"), "{:.1f}")}</td>'
        f'<td class="n" style="font-weight:700; color:#8b5cf6;">{_fmt(val.get("fgi_score"), "{:.1f}")}</td>'
        f'<td class="n">{_fmt(aa_int, "{:.1f}")}<span class="mid">{html_lib.escape(bm.get("aa_slug") or "")}</span></td>'
        f'<td class="n">{_fmt(bm.get("aa_coding"), "{:.1f}")}</td>'
        f'<td class="n">{lm_s}<span class="mid">{_fmt(bm.get("lmarena_elo"), "{:.0f}")}</span></td>'
        f'<td class="n">{_fmt(ipd, "{:.0f}")}</td>'
        f'<td class="n">{_fmt(val.get("cost_per_intelligence_pt_usd"), "${:.5f}")}</td>'
        f'<td class="n">{_fmt(val.get("leverage_vs_10usd_sub"), "{:.1f}×")}</td>'
        f'{_rem_html_td(row)}</tr>'
    )


def render_html(
    rows,
    work_sentence=None,
    pareto_ids=None,
    added_ids=None,
    removed_models=None,
    data_note=None,
    usage_note=None,
    role_recs=None,
):
    pareto_ids = pareto_ids or set()
    added_ids = added_ids or set()
    removed_models = removed_models or []
    work_sentence = one_sentence_work(rows) if work_sentence is None else work_sentence
    recs = role_recs if role_recs is not None else bc.compute_role_recommendations(rows, context="ocheck")
    role_recs_html = bc.render_role_recommendations_html(recs) if recs else ""

    def _oc_removed_limit(rm: dict) -> str:
        pr = rm.get("pricing", {}).get("monthly_usage_limit_usd")
        return f"${pr:.0f}/mo" if pr is not None else "Free"

    removed_html = bc.render_removed_html_section(
        removed_models,
        _oc_removed_limit,
        "These models were present in the previous catalog snapshot but are no longer active in the current OpenCode Go docs or API:",
    )
    title = f"OpenCode Go — Cost/Benefit ({dt.date.today().isoformat()})"
    subtitle_html = (
        f'{html_lib.escape(data_note or "Live check")} — OpenCode Go <code>$10/mo</code> (Go Plus <code>$40/mo</code>) · '
        f'Shared allowance (<b>5h = 20%</b>, <b>weekly = 50%</b>, <b>monthly = 100%</b>; model limit = drain denominator) · '
        f'usage source: <b>{html_lib.escape(usage_note or "unavailable")}</b> · '
        f'<a href="{OCGO_DOCS}#usage-limits" style="color:#58a6ff">docs</a> · Generated {dt.datetime.now(dt.UTC).isoformat()}'
    )
    legend_top = (
        '<b>How to read:</b> <span style="color:#d29922">■ pareto</span> cost/intelligence frontier · '
        '<span style="color:#3fb950">■ flagship</span> intelligence ≥58 · <span style="color:#58a6ff">■ value</span> '
        '$60+ usage + high int/$ · <b>Q(Cap)</b> = Capability · <b>P(Succ)</b> = 1-turn pass rate · '
        '<b>Eff c/r</b> = Cost per solved task · <b>Value</b> = Quota utility · <b>AVI</b> = ROI · <b>FGI</b> = Gate · <b>lev</b> = <code>usage/10</code>.'
    )
    takeaway = (
        "<b>Takeaway:</b> Cheapest per-request (MiMo-V2.5, Muse Spark, Hy3, DeepSeek Flash) buy the most requests from the pooled cap — "
        "ideal for high-volume use. Flagship intelligence (Kimi K3, GLM-5.3, Qwen3.8-Max, Grok 4.6, GPT-5.6-Luna) cost more per request "
        "but score higher. Best “intelligence per dollar” usually sits in the middle (DeepSeek Flash, Qwen3.7-Plus, GLM-5.2, MiniMax M3). "
        "Use the <code>int/$</code> column to pick your tier."
    )
    footer_note = (
        'Full JSON: <a href="ocgo_cost_benefit.json" style="color:#58a6ff">ocgo_cost_benefit.json</a> · '
        'Raw snapshots in <code>docs/data/raw/</code> when run with <code>--fetch</code>. Stdlib only, no API keys. '
        'Re-run: <code>uv run python checkers/opencode_cost_benefit_analyzer.py</code>.'
    )
    return bc.render_analyzer_html_shell(
        title=title,
        subtitle_html=subtitle_html,
        legend_top_html=legend_top,
        th_cols=_HTML_COLS,
        trs=[_render_html_tr(r, pareto_ids, added_ids) for r in rows],
        legend_bot='Click headers to sort. “—” = not benchmarked / free. AA from artificialanalysis.ai; Arena from arena.ai; pricing from opencode.ai/docs/go.',
        removed_html=removed_html,
        role_recs_html=role_recs_html,
        takeaway_html=takeaway,
        footer_note_html=footer_note,
        work_sentence=work_sentence,
        out_href="docs/reports/ocgo_cost_benefit.html",
    )


def _best_go_value_id(rows: list[dict]) -> str | None:
    best, best_ipd = None, -1.0
    for row in rows:
        ipd = row["value"].get("intelligence_per_dollar")
        usage = row["pricing"].get("monthly_usage_limit_usd")
        if usage == 60 and ipd and ipd > best_ipd:
            best, best_ipd = row["model_id"], ipd
    return best


def one_sentence_work(rows: list[dict], usage_percents: dict | None = None) -> str:
    have_int = sum(1 for r in rows if r["benchmarks"]["aa_intelligence"] is not None)
    best = _best_go_value_id(rows)
    flag_row = next((r for r in rows if r["benchmarks"]["aa_intelligence"] and r["benchmarks"]["aa_intelligence"] >= 59), None)
    flagship = flag_row["model_id"] if flag_row else None
    rem = f", {100 - max(usage_percents.values()):.0f}% quota remaining" if usage_percents else ""
    if best and flagship:
        return f"Current work: live cost/benefit of {len(rows)} Go models ({have_int} ranked) — best value {best}, flagship {flagship}{rem}."
    if best:
        return f"Current work: live check of {len(rows)} Go models ({have_int} ranked) — best value {best}{rem}."
    return f"Current work: live check of {len(rows)} Go models ({have_int} ranked){rem}."


def _fetch_ocgo_catalog(do_write: bool, verbose: bool) -> tuple[dict, dict, dict, list[str]]:
    pricing_live, requests_live, tokens_live, api_ids = {}, {}, {}, []
    if (body := bc.fetch_bytes(OCGO_DOCS, verbose=verbose)):
        html_txt = body.decode(errors="ignore")
        if do_write:
            snap = RAW / f"opencode_go_docs_{dt.date.today().isoformat().replace('-', '')}.html"
            bc.atomic_write_text(snap, html_txt)
            print(f"  saved docs snapshot -> {snap.relative_to(ROOT)} ({len(html_txt)} bytes)")
        pricing_live, requests_live, tokens_live = parse_ocgo_docs(html_txt, verbose=verbose)
        print(f"  docs: pricing={len(pricing_live)}, requests={len(requests_live)}, tokens={len(tokens_live)}")
    else:
        print("  WARN docs fetch failed, trying snapshot/fallback", file=sys.stderr)

    if (api_body := bc.fetch_bytes(OCGO_API, verbose=verbose)):
        try:
            payload = json.loads(api_body)
            if do_write:
                snap = RAW / f"opencode_go_models_{dt.date.today().isoformat().replace('-', '')}.json"
                bc.atomic_write_text(snap, json.dumps(payload, indent=2))
                print(f"  saved API snapshot -> {snap.relative_to(ROOT)}")
            api_ids = [m["id"] for m in payload.get("data", []) if m.get("id")]
            print(f"  API models: {len(api_ids)}")
        except Exception as exc:
            print(f"  WARN API parse: {exc}", file=sys.stderr)
    return pricing_live, requests_live, tokens_live, api_ids


def _load_offline_docs(verbose: bool) -> tuple[dict, dict, dict]:
    snap = bc.pick_latest_raw(RAW, "opencode_go_docs")
    if snap is None:
        return {}, {}, {}
    try:
        pl, rl, tl = parse_ocgo_docs(snap.read_text(errors="ignore"), verbose=verbose)
        if pl:
            print(f"  offline docs pricing: {len(pl)} models ({snap.name})")
        return pl, rl, tl
    except Exception as exc:
        print(f"  WARN offline docs parse: {exc}", file=sys.stderr)
        return {}, {}, {}


def _load_offline_api_ids() -> list[str]:
    snap = bc.pick_latest_raw(RAW, "opencode_go_models")
    if snap is None:
        return []
    try:
        ids = [m["id"] for m in json.loads(snap.read_text(errors="ignore")).get("data", []) if m.get("id")]
        if ids:
            print(f"  offline API models: {len(ids)} ({snap.name})")
        return ids
    except Exception as exc:
        print(f"  WARN offline API parse: {exc}", file=sys.stderr)
        return []


def _merge_catalog(pricing_live: dict, tokens_live: dict, api_ids: list[str]) -> tuple[list[str], dict, dict]:
    if not api_ids:
        all_ids = list(FALLBACK_PRICING.keys())
        print(f"  using fallback API ids: {len(all_ids)}")
    else:
        seen = set(api_ids)
        extras = [k for k in list(FALLBACK_PRICING) + list(pricing_live) if k not in seen and not seen.add(k)]
        all_ids = list(api_ids) + extras
    default_pr = {"input": None, "output": None, "cached_read": None, "cached_write": None, "usage": 60}
    merged_pr = {mid: pricing_live.get(mid) or FALLBACK_PRICING.get(mid) or default_pr for mid in all_ids}
    merged_tok = {mid: tokens_live.get(mid) or FALLBACK_TOKENS.get(mid) or (500, 60000, 200) for mid in all_ids}
    return all_ids, merged_pr, merged_tok


def _fetch_and_parse_map(url: str, tag: str, parser, do_write: bool, verbose: bool) -> dict | None:
    body = bc.fetch_bytes(url, verbose=verbose)
    if not body:
        return None
    try:
        raw_txt = body.decode(errors="ignore")
        payload = json.loads(raw_txt) if tag == "openrouter_models" else raw_txt
        parsed = parser(payload, verbose=verbose)
        if do_write:
            ext = "json" if tag == "openrouter_models" else "html"
            snap = RAW / f"{tag}_{dt.date.today().isoformat().replace('-', '')}.{ext}"
            bc.atomic_write_text(snap, json.dumps(payload, indent=2) if ext == "json" else raw_txt)
        return parsed
    except Exception as exc:
        print(f"  WARN {tag} live parse: {exc}", file=sys.stderr)
        return None


def _load_map(url: str, tag: str, parser, do_fetch: bool, do_write: bool, verbose: bool) -> dict:
    if do_fetch and (live := _fetch_and_parse_map(url, tag, parser, do_write, verbose)) is not None:
        return live
    snap = bc.pick_latest_raw(RAW, tag)
    if snap is None:
        return {}
    try:
        raw_txt = snap.read_text(errors="ignore")
        data = parser(json.loads(raw_txt) if snap.suffix == ".json" else raw_txt, verbose=verbose)
        print(f"  offline {tag}: {len(data)} entries ({snap.name})")
        return data
    except Exception as exc:
        print(f"  WARN offline {tag} parse: {exc}", file=sys.stderr)
        return {}


def _load_usage_state(do_fetch: bool, do_write: bool, verbose: bool) -> tuple[dict, dict, str | None, bool, str]:
    percents, resets, err, key_present, note = {}, {}, None, False, ""
    if do_fetch and (key := get_api_key()):
        key_present = True
        usage_raw, err = fetch_usage(key, verbose=verbose)
        percents, resets = extract_usage_windows(usage_raw)
        if percents:
            note = "live (fetched now)"
            if do_write:
                snap = RAW / f"ocgo_usage_{dt.date.today().isoformat().replace('-', '')}.json"
                bc.atomic_write_text(snap, json.dumps({"fetched_at": dt.datetime.now(dt.UTC).isoformat(), "usage": usage_raw}, indent=2))
            return percents, resets, err, key_present, note
        if err:
            print(f"  usage: {err} — trying cached snapshot", file=sys.stderr)

    snap = bc.pick_latest_raw(RAW, "ocgo_usage")
    if snap is not None:
        try:
            raw_j = json.loads(snap.read_text(errors="ignore"))
            percents, resets = extract_usage_windows(raw_j.get("usage", raw_j))
            if percents:
                key_present = True
                note = f"cached {snap.name}{bc.staleness_tag(snap)}"
        except Exception as exc:
            print(f"  WARN usage snapshot parse: {exc}", file=sys.stderr)
    return percents, resets, err, key_present, note


def _or_pair_price(prc: dict) -> tuple[float | None, float | None] | None:
    pin, pout = _sf(prc.get("prompt")), _sf(prc.get("completion"))
    if (pin is not None and pin > 0) or (pout is not None and pout > 0):
        return (pin * 1_000_000 if pin is not None else None), (pout * 1_000_000 if pout is not None else None)
    return None


def _or_fallback_price(mid: str, or_map: dict) -> tuple[float | None, float | None]:
    nmid = bc.norm_id(mid)
    for or_id, or_rec in or_map.items():
        nor = bc.norm_id(or_id)
        if (nmid in nor or nor in nmid) and (pair := _or_pair_price(or_rec.get("pricing") or {})):
            return pair
    return None, None


def _compute_remaining(usage_percents: dict, caps: tuple, cost_req, usage_cap) -> dict:
    rem, rem_req = {}, {}
    if not usage_percents:
        return {"percent": rem, "requests": rem_req, "overall_pct": None, "overall_req": None}
    for win, cap in zip(("rolling", "weekly", "monthly"), caps):
        pct_used = _sf(usage_percents.get(win))
        if pct_used is None:
            continue
        pct_rem = max(0.0, 100.0 - pct_used)
        rem[win] = round(pct_rem, 1)
        if usage_cap is not None and cap is not None and cost_req and cost_req > 0:
            rem_req[win] = _si_round((cap * pct_rem / 100.0) / cost_req)
    return {
        "percent": rem,
        "requests": rem_req,
        "overall_pct": min(rem.values()) if rem else None,
        "overall_req": min(rem_req.values()) if rem_req else None,
    }


def _pick(rec: dict | None, key: str, fn=_sf):
    return fn(rec.get(key)) if rec else None


def _clean_aa_slug(aa_rec: dict | None) -> str | None:
    raw = aa_rec.get("slug") if aa_rec else None
    return str(raw) if raw and not str(raw).startswith("$") else None


def _build_benchmarks(mid: str, aa_map: dict, lm_map: dict, or_map: dict, live_map: dict) -> dict:
    aa_rec = bc.find_aa_for_model(mid, aa_map) if aa_map else None
    lm_rec = bc.find_lm_for_model(mid, lm_map) if lm_map else None
    or_oid, or_rec = bc.find_or_for_model(mid, or_map) if or_map else (None, None)
    live_rec = bc.find_livebench_for_model(mid, live_map) if live_map else None
    or_prompt = _sf((or_rec.get("pricing") or {}).get("prompt")) if or_rec else None
    return {
        "aa_slug": _clean_aa_slug(aa_rec),
        "aa_intelligence": _pick(aa_rec, "intelligenceIndex"),
        "aa_coding": _pick(aa_rec, "codingIndex"),
        "aa_agentic": _pick(aa_rec, "agenticIndex"),
        "aa_median_tps": _pick(aa_rec, "medianOutputTokensPerSecond"),
        "aa_context": _pick(aa_rec, "contextWindowTokens", _si),
        "lmarena_rank": _pick(lm_rec, "rank", _si),
        "lmarena_elo": _pick(lm_rec, "elo"),
        "lmarena_votes": _pick(lm_rec, "votes", _si),
        "livebench": live_rec,
        "openrouter_id": or_oid,
        "openrouter_context": or_rec.get("context_length") if or_rec else None,
        "openrouter_prompt_per_1m": or_prompt * 1_000_000 if or_prompt is not None else None,
    }


def _req_block(caps: tuple, cost_req, usage, docs_req: dict) -> dict:
    cap_5h, cap_wk, cap_mo = caps
    pos = cost_req is not None and cost_req > 0 and usage is not None
    return {
        "per_5h_computed": _si_round(cap_5h / cost_req) if pos else None,
        "per_week_computed": _si_round(cap_wk / cost_req) if pos else None,
        "per_month_computed": _si_round(cap_mo / cost_req) if pos else None,
        "per_5h_docs": docs_req.get("per_5h"),
        "per_week_docs": docs_req.get("per_week"),
        "per_month_docs": docs_req.get("per_month"),
    }


def _val_block(aa_int, cost_req, usage) -> dict:
    pos = cost_req is not None and cost_req > 0
    ipd = (aa_int / cost_req) if (aa_int is not None and pos) else None
    cpi = (cost_req / aa_int) if (aa_int and pos) else None
    return {
        "intelligence_per_dollar": round(ipd, 2) if ipd else None,
        "cost_per_intelligence_pt_usd": round(cpi, 6) if cpi else None,
        "requests_per_dollar": round(1.0 / cost_req, 1) if pos else None,
        "leverage_vs_10usd_sub": round(usage / 10.0, 2) if usage else None,
    }


def _build_model_row(mid: str, pr: dict, toks: tuple, docs_req: dict, usage_percents: dict, maps: tuple[dict, dict, dict, dict]) -> dict:
    or_map, aa_map, lm_map, live_map = maps
    inp, outp, cr, cw, usage = pr.get("input"), pr.get("output"), pr.get("cached_read"), pr.get("cached_write"), pr.get("usage")
    if inp is None and or_map:
        inp, outp = _or_fallback_price(mid, or_map)

    est_in, est_ca, est_out = toks
    cost_req = bc.compute_cost(inp, outp, cr, est_in, est_ca, est_out)
    cap_mo = _sf(usage)
    caps = (cap_mo * 0.20, cap_mo * 0.50, cap_mo) if cap_mo is not None else (None, None, None)
    bm = _build_benchmarks(mid, aa_map, lm_map, or_map, live_map)
    return {
        "model_id": mid,
        "display": mid,
        "is_docs_model": False,
        "pricing": {"input_per_1m": inp, "output_per_1m": outp, "cached_read_per_1m": cr, "cached_write_per_1m": cw, "monthly_usage_limit_usd": usage},
        "caps": {"cap_5h_usd": caps[0], "cap_wk_usd": caps[1], "cap_mo_usd": caps[2]},
        "tokens": {"est_input": est_in, "est_cached": est_ca, "est_output": est_out},
        "cost_per_request_usd": round(cost_req, 6) if cost_req is not None else None,
        "requests": _req_block(caps, cost_req, usage, docs_req),
        "remaining": _compute_remaining(usage_percents, caps, cost_req, usage),
        "benchmarks": bm,
        "value": _val_block(bm["aa_intelligence"], cost_req, usage),
    }


def _eff_cost(row: dict) -> float:
    if row["pricing"].get("monthly_usage_limit_usd") is None or "free" in row["model_id"].lower():
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
    docs_rows: list[dict],
    pareto_ids: set,
    catalog_diff: dict,
    prev_snapshot,
    usage_percents: dict,
    usage_note: str,
    data_label: str,
    role_recs: dict,
    verbose: bool,
) -> None:
    live = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "sources": {
            "opencode_docs": OCGO_DOCS,
            "opencode_api": OCGO_API,
            "openrouter_api": OPENROUTER_API,
            "artificial_analysis": AA_URL,
            "lmarena": LMARENA_URL,
            "usage_limits": f"{OCGO_DOCS}#usage-limits",
            "limit_model": "shared percentage allowance (5h=20%, weekly=50%, monthly=100%); model Monthly limit is drain denominator",
            "usage_source": usage_note or "unavailable",
        },
        "catalog_diff": {
            "added": sorted(catalog_diff["added_ids"]),
            "removed": sorted(catalog_diff["removed_ids"]),
            "total_current": len(docs_rows),
            "total_previous": _prev_docs_count(prev_snapshot, len(docs_rows)),
        },
        "role_recommendations": role_recs,
        "models": rows_sorted,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    out_json = DATA / "ocgo_live.json"
    cb_json = OUT / "ocgo_cost_benefit.json"
    html_path = OUT / "ocgo_cost_benefit.html"
    bc.atomic_write_text(out_json, json.dumps(live, indent=2))
    bc.atomic_write_text(cb_json, json.dumps(rows_sorted, indent=2))
    bc.atomic_write_text(
        html_path,
        render_html(
            docs_rows,
            work_sentence=one_sentence_work(docs_rows, usage_percents),
            pareto_ids=pareto_ids,
            added_ids=catalog_diff["added_ids"],
            removed_models=catalog_diff["removed_models"],
            data_note=data_label,
            usage_note=usage_note,
            role_recs=role_recs,
        ),
    )
    if verbose:
        print(f"wrote {out_json.relative_to(ROOT)}, {cb_json.relative_to(ROOT)}, {html_path.relative_to(ROOT)}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="OpenCode Go catalog checker (offline cache by default; live only with --fetch)")
    ap.add_argument("--fetch", "--refresh", action="store_true", help="Live-fetch Go docs + API + OpenRouter/AA/LMArena snapshots")
    ap.add_argument("--check", action="store_true", help="Print only: writes NOTHING (even with --fetch)")
    ap.add_argument("--limits", action="store_true", help="Show multi-window pooled limits & per-model allowance breakdown")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging")
    ap.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors")
    ap.add_argument("--slim", action="store_true", help="Force compact table layout")
    ap.add_argument("--wide", action="store_true", help="Force full table layout")
    ap.add_argument(
        "--sort",
        choices=["value", "qvi", "avi", "fgi", "bfi", "cap", "quality", "reqmo", "req5h", "cost", "intel"],
        default="value",
        help="Sort order (default: value)",
    )
    return ap.parse_args()


def _gather_inputs(do_fetch: bool, do_write: bool, verbose: bool):
    data_label = "live fetch"
    if not do_fetch:
        note, data_label = bc.offline_snapshot_note(RAW, _SNAP_LABELS)
        print(note)
    pl, rl, tl, api_ids = _fetch_ocgo_catalog(do_write, verbose) if do_fetch else ({}, {}, {}, [])
    if not pl:
        pl, rl_off, tl_off = _load_offline_docs(verbose)
        rl, tl = rl or rl_off, tl or tl_off
    if not api_ids:
        api_ids = _load_offline_api_ids()

    lm_payload = bc.fetch_lmarena_hf_snapshot(RAW, verbose=verbose, do_write=do_write) if do_fetch else None
    lm_map = bc.parse_lmarena_hf(lm_payload, verbose=verbose) if lm_payload else bc.load_lmarena_map(RAW, verbose=verbose)
    or_map = _load_map(OPENROUTER_API, "openrouter_models", bc.parse_openrouter, do_fetch, do_write, verbose)
    aa_map = _load_map(AA_URL, "artificial_analysis", bc.parse_aa, do_fetch, do_write, verbose)
    live_map = bc.load_livebench_snapshots(RAW, verbose=verbose)
    return pl, rl, tl, api_ids, (or_map, aa_map, lm_map, live_map), data_label


def _print_report(args, docs_rows: list[dict], pareto_ids: set, catalog_diff: dict, usage_state: tuple, role_recs: dict) -> None:
    usage_percents, usage_resets, usage_err, usage_key_present, usage_note = usage_state
    use_color = not (args.plain or os.getenv("NO_COLOR"))
    slim_opt = True if args.slim else (False if args.wide else None)
    if args.limits:
        body = render_limits_table(
            docs_rows, usage_percents=usage_percents, usage_resets=usage_resets,
            usage_key_present=usage_key_present, usage_note=usage_note, color=use_color, slim=slim_opt, wide=args.wide,
        )
    else:
        body = render_cli_table(
            docs_rows, usage_percents=usage_percents, usage_err=usage_err, usage_key_present=usage_key_present,
            pareto_ids=pareto_ids, added_ids=catalog_diff["added_ids"], removed_models=catalog_diff["removed_models"],
            color=use_color, slim=slim_opt, wide=args.wide, usage_note=usage_note, role_recs=role_recs,
        )
    print("\n" + body)


def main():
    args = _parse_args()
    do_fetch, do_write = bool(args.fetch), not args.check
    mode_tag = "fetch (network)" if do_fetch else "OFFLINE (cache-only)"
    check_tag = " · check: no writes" if args.check else ""
    print(f"OpenCode Go — catalog check\n  date: {dt.datetime.now(dt.UTC).isoformat()}\n  mode: {mode_tag}{check_tag}")

    pl, rl, tl, api_ids, maps, data_label = _gather_inputs(do_fetch, do_write, args.verbose)
    usage_state = _load_usage_state(do_fetch, do_write, args.verbose)
    all_ids, merged_pr, merged_tok = _merge_catalog(pl, tl, api_ids)
    rows = [_build_model_row(mid, merged_pr[mid], merged_tok[mid], rl.get(mid, {}), usage_state[0], maps) for mid in all_ids]
    bc.score_analyzer_rows(rows)

    rows_sorted = sorted(rows, key=build_sort_key(args.sort, _eff_cost))
    docs_set = set(pl.keys()) | DOCS_IDS | ({"ox-alpha-free"} if "ox-alpha-free" in api_ids else set())
    for row in rows_sorted:
        row["is_docs_model"] = row["model_id"] in docs_set
    docs_rows = [r for r in rows_sorted if r["is_docs_model"]]
    pareto_ids = bc.compute_pareto_ids(rows_sorted, _eff_cost, docs_set)
    prev_snapshot = bc.load_previous_snapshot(DATA / "ocgo_live.json")
    catalog_diff = bc.diff_model_catalog(docs_rows, prev_snapshot)
    docs_rows = catalog_diff["rows"]
    role_recs = bc.compute_role_recommendations(docs_rows, context="ocheck")

    _print_report(args, docs_rows, pareto_ids, catalog_diff, usage_state, role_recs)
    if do_write:
        _write_outputs(rows_sorted, docs_rows, pareto_ids, catalog_diff, prev_snapshot, usage_state[0], usage_state[4], data_label, role_recs, args.verbose)
    else:
        print("\n(check-only, no files written)")


if __name__ == "__main__":
    main()
