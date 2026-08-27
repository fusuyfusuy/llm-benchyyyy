#!/usr/bin/env python3
"""
benchmark_common.py — Shared mathematical scoring, parsers, normalization,
and coherent visual styling for bcheck, ocheck, fcheck, and scheck.

Zero external dependencies (pure Python 3 standard library).
"""
import csv
import datetime as dt
import glob
import html as html_lib
import io
import json
import math
import os
import pathlib
import re
import shutil
import statistics
import sys
import urllib.error
import urllib.request

# ==============================================================================
# 1. ANSI COLOR CODES & THEME CONSTANTS
# ==============================================================================
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_UNDER = "\033[4m"

# Zebra row backgrounds
BG_EVEN = "\033[48;5;233m"  # Deep subtle charcoal
BG_ODD = "\033[48;5;236m"   # Slate dark tint
BG_HEADER = "\033[48;5;235m"

# Palette Colors
C_GOLD = "\033[38;5;220m"
C_SILVER = "\033[38;5;250m"
C_BRONZE = "\033[38;5;208m"
C_CYAN = "\033[38;5;51m"
C_GREEN = "\033[38;5;48m"
C_YELLOW = "\033[38;5;226m"
C_MAGENTA = "\033[38;5;205m"
C_PURPLE = "\033[38;5;141m"
C_WHITE = "\033[38;5;255m"
C_GRAY = "\033[38;5;244m"
C_RED = "\033[38;5;196m"

# Provider / Pool Accents
C_CLAUDE = "\033[38;5;214m"   # Amber / Orange
C_AGY = "\033[38;5;75m"       # Sky Blue
C_OCGO = "\033[38;5;48m"      # Emerald Green
C_FRONTIER = "\033[38;5;141m" # Violet / Purple
C_OPENROUTER = "\033[38;5;51m"# Cyan
C_CLINE = "\033[38;5;39m"     # Dodger Blue / Sky Accent

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ==============================================================================
# 2. STRING NORMALIZATION & SAFE VALUE CONVERSIONS
# ==============================================================================
def norm_id(s: str) -> str:
    """Normalize model identifier to canonical lowercase kebab-case."""
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\.\-_]", "", s)
    return s


def norm_model_slug(s: str) -> str:
    """Normalize model identifier for strict version-safe comparison."""
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"^(claude|anthropic|openai|google|meta|zhipu|z-ai|xiaomi|minimax|xai|moonshot)-", "", s)
    s = s.replace(".", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _safe_float(val, default=None):
    """Safely convert value to float or return default."""
    if val is None or val == "" or val == "—" or val == "-":
        return default
    try:
        if isinstance(val, str):
            val = val.replace(",", "").replace("$", "").replace("%", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=None):
    """Safely convert value to int or return default."""
    if val is None or val == "" or val == "—" or val == "-":
        return default
    try:
        if isinstance(val, str):
            val = val.replace(",", "").replace("$", "").replace("%", "").strip()
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_int_round(val, default=None):
    """Safely round and convert float value to int."""
    if val is None:
        return default
    try:
        return int(round(val))
    except (ValueError, TypeError):
        return default


def parse_price(s: str) -> float | None:
    """Parse currency string into float or None."""
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    if s in ("", "-", "—"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def pick_latest_raw(raw_dir: pathlib.Path, name_part: str) -> pathlib.Path | None:
    """Find newest snapshot in raw_dir whose filename matches name_part."""
    matches = sorted(glob.glob(str(raw_dir / f"*{name_part}*")))
    return pathlib.Path(matches[-1]) if matches else None


# ==============================================================================
# 3. STATISTICAL & COMPOSITE SCORING FORMULAS
# ==============================================================================
def get_z_scores(values: list) -> list[float]:
    """Compute z-scores for a list of values (ignoring None / non-numeric entries)."""
    valid = [v for v in values if isinstance(v, (int, float))]
    if len(valid) < 2:
        return [0.0] * len(values)
    mean_val = statistics.mean(valid)
    std_val = statistics.stdev(valid) if len(valid) > 1 else 1.0
    if std_val == 0.0:
        std_val = 1.0
    return [(v - mean_val) / std_val if isinstance(v, (int, float)) else 0.0 for v in values]


def compute_capability_q(cz: float) -> float:
    """
    Compute Normalized Composite Capability Q ∈ [40.0, 99.9].
    Base centered at 78.0 with 8.5 standard deviation scale factor.
    """
    return round(max(40.0, min(99.9, 78.0 + (cz * 8.5))), 1)


def compute_p_success(q_score: float) -> float:
    """
    Compute task pass probability P_succ(Q) ∈ (0.0, 100.0)% on non-trivial agentic task.
    Sigmoid model centered at Q=72.0 with slope k=0.12, numerically clamped.
    """
    exponent = max(-50.0, min(50.0, -0.12 * (q_score - 72.0)))
    p_succ = 1.0 / (1.0 + math.exp(exponent))
    return round(p_succ * 100.0, 1)


def compute_token_multiplier(p_success_pct: float, alpha: float = 1.2) -> float:
    """
    Compute Token Multiplier T_mult = (1 + α * (1 - P)) / P.
    Accounts for expected retry and debugging token burn on autonomous failures.
    """
    p_succ = max(0.02, min(1.0, p_success_pct / 100.0))
    t_mult = (1.0 + alpha * (1.0 - p_succ)) / p_succ
    return round(t_mult, 2)


def compute_effective_cost(blended_price: float, token_multiplier: float) -> float:
    """Compute effective cost per verified completed task."""
    return round(blended_price * token_multiplier, 2)


def compute_avi(q_score: float, effective_cost: float) -> float:
    """
    Agentic Value Index (AVI): Super-linear capability vs log effective cost ROI.
    Formula: Q^2.2 / (100 * log10(effective_cost + 1.5))
    """
    return round((q_score ** 2.2) / (100.0 * math.log10(max(0.0, effective_cost) + 1.5)), 1)


def compute_fgi(q_score: float, p_success_pct: float) -> float:
    """
    Frontier Gate Index (FGI): High-difficulty architectural gating index.
    Formula: Q * (P_succ ^ 1.5)
    """
    p_succ = max(0.0, min(1.0, p_success_pct / 100.0))
    return round(q_score * (p_succ ** 1.5), 1)


def compute_bfi(q_score: float, speed_tps: float, blended_price: float) -> float:
    """
    Bulk Fill Index (BFI): Throughput and raw cost efficiency on bounded tasks.
    Formula: (Q * speed) / (100 * ((blended_price ^ 0.8) + 0.1))
    """
    return round((q_score * speed_tps) / (100.0 * ((max(0.0, blended_price) ** 0.8) + 0.1)), 1)


def pareto_dominated(a_cost, a_q, candidates, q_tolerance=3.2, cost_tolerance=0.20, cost_epsilon=0.01):
    """
    True if (a_cost, a_q) is dominated by any (cost, q) pair in candidates,
    beyond the given headroom tolerances. Shared dominance-check primitive
    behind each script's own Pareto-frontier sweep (row shapes differ too
    much across bcheck/ocheck to share one end-to-end function).
    """
    for b_cost, b_q in candidates:
        if b_cost <= a_cost and b_q >= a_q:
            cost_diff = (a_cost - b_cost) / max(cost_epsilon, a_cost)
            q_diff = b_q - a_q
            if cost_diff > cost_tolerance or q_diff > q_tolerance:
                return True
    return False


def compute_pareto_frontier(models_list, q_tolerance=3.2, cost_tolerance=0.20):
    """Compute Pareto-optimal frontier models on Effective Cost vs Composite Capability,
    including close-call / near-frontier models with generous headroom tolerances.
    """
    pareto_set = set()
    for a in models_list:
        a_cost = a.get("effective_cost") or (a.get("price_in", 999) + a.get("price_out", 999)) or 999
        a_q = a.get("capability_q", 0)
        candidates = [
            (
                b.get("effective_cost") or (b.get("price_in", 999) + b.get("price_out", 999)) or 999,
                b.get("capability_q", 0),
            )
            for b in models_list
            if b is not a
        ]
        if not pareto_dominated(a_cost, a_q, candidates, q_tolerance, cost_tolerance):
            pareto_set.add(a.get("display"))
            if a.get("aa_slug"):
                pareto_set.add(a.get("aa_slug"))
            if a.get("lm_slug"):
                pareto_set.add(a.get("lm_slug"))
            if a.get("display")[:22]:
                pareto_set.add(a.get("display")[:22])
            if a.get("display")[:20]:
                pareto_set.add(a.get("display")[:20])
    return pareto_set


def compute_meanfill_composite(rows):
    """
    Composite capability_q from the MEAN of whichever z-scored sources
    (AA intelligence, LMArena elo) are available per row, skipping missing
    sources rather than zero-filling them (unlike get_z_scores, which
    zero-fills). Used by fcheck/scheck, whose catalogs have much sparser
    per-source coverage than bcheck/ocheck's curated model lists.
    Mutates each row in place: sets row["composite"] and
    row["benchmarks"]["capability_q"]. Returns (aa_vals, lm_vals, aa_mean,
    aa_std, lm_mean, lm_std) so callers can report coverage/diagnostics
    without rescanning rows.
    """
    aa_vals = [r["benchmarks"]["aa_intelligence"] for r in rows if r["benchmarks"]["aa_intelligence"] is not None]
    lm_vals = [r["benchmarks"]["lmarena_elo"] for r in rows if r["benchmarks"]["lmarena_elo"] is not None]
    aa_mean = statistics.fmean(aa_vals) if aa_vals else None
    aa_std = statistics.pstdev(aa_vals) if len(aa_vals) > 1 else (0.0 if aa_vals else None)
    lm_mean = statistics.fmean(lm_vals) if lm_vals else None
    lm_std = statistics.pstdev(lm_vals) if len(lm_vals) > 1 else (0.0 if lm_vals else None)

    for r in rows:
        b = r["benchmarks"]
        zs = []
        a = b["aa_intelligence"]
        if a is not None and aa_std is not None and aa_std > 0:
            zs.append((a - aa_mean) / aa_std)
        elif a is not None and aa_std == 0.0:
            zs.append(0.0)
        e = b["lmarena_elo"]
        if e is not None and lm_std is not None and lm_std > 0:
            zs.append((e - lm_mean) / lm_std)
        elif e is not None and lm_std == 0.0:
            zs.append(0.0)
        comp_val = round(statistics.fmean(zs), 3) if zs else None
        r["composite"] = comp_val
        b["capability_q"] = compute_capability_q(comp_val) if isinstance(comp_val, (int, float)) else None
    return aa_vals, lm_vals, aa_mean, aa_std, lm_mean, lm_std


def comp_key(r):
    """Sort key: composite desc, then AA, then LMArena, then id. None composites last."""
    c = r.get("composite")
    k_c = -(c) if isinstance(c, (int, float)) else 1e9
    a = r["benchmarks"]["aa_intelligence"]
    k_a = -(a) if isinstance(a, (int, float)) else 1e9
    e = r["benchmarks"]["lmarena_elo"]
    k_e = -(e) if isinstance(e, (int, float)) else 1e9
    return (k_c, k_a, k_e, r["model_id"])


def is_stealth_model(rec):
    """OpenRouter anonymous-model namespace: id starts with 'stealth/'."""
    oid = rec.get("id", "") or ""
    return oid.startswith("stealth/")


def base_id(oid: str) -> str:
    """Strip trailing :free or -free tags, or leading cline-free/ so cross-source matching sees the real slug."""
    s = oid
    if s.startswith("cline-free/"):
        s = s[len("cline-free/"):]
    if s.endswith(":free"):
        s = s[:-5]
    elif s.endswith("-free"):
        s = s[:-5]
    return s


# ==============================================================================
# 4. LEADERBOARD PARSERS
# ==============================================================================
def parse_livebench(csv_text: str, categories_json: str | dict | None = None, verbose: bool = False) -> dict:
    """
    Parse LiveBench leaderboard CSV (https://livebench.ai).
    Extracts decontaminated scores across Reasoning, Coding, Agentic Coding, Math, Data Analysis, and IF.
    """
    cats = {}
    if categories_json:
        if isinstance(categories_json, str):
            try:
                cats = json.loads(categories_json)
            except Exception:
                pass
        elif isinstance(categories_json, dict):
            cats = categories_json

    reader = csv.DictReader(io.StringIO(csv_text))
    out = {}
    for row in reader:
        model = row.get("model")
        if not model:
            continue

        cat_scores = {}
        all_task_scores = []
        for col, val in row.items():
            if col == "model" or col.startswith("nq_") or col.startswith("out_"):
                continue
            fv = _safe_float(val)
            if fv is not None:
                all_task_scores.append(fv)

        overall = sum(all_task_scores) / len(all_task_scores) if all_task_scores else None

        if cats:
            for cat_name, tasks in cats.items():
                t_scores = [_safe_float(row.get(t)) for t in tasks if _safe_float(row.get(t)) is not None]
                if t_scores:
                    cat_scores[cat_name] = round(sum(t_scores) / len(t_scores), 2)

        slug = norm_id(model)
        out[slug] = {
            "model": model,
            "overall": round(overall, 2) if overall is not None else None,
            "coding": cat_scores.get("Coding") or cat_scores.get("coding") or _safe_float(row.get("coding")),
            "agentic_coding": cat_scores.get("Agentic Coding") or cat_scores.get("agentic_coding"),
            "reasoning": cat_scores.get("Reasoning") or cat_scores.get("reasoning") or _safe_float(row.get("reasoning")),
            "math": cat_scores.get("Mathematics") or cat_scores.get("math") or _safe_float(row.get("math")),
            "data_analysis": cat_scores.get("Data Analysis") or cat_scores.get("data_analysis"),
            "language": cat_scores.get("Language") or cat_scores.get("language"),
            "instruction_following": cat_scores.get("IF") or cat_scores.get("instruction_following"),
            "categories": cat_scores,
        }
    if verbose:
        print(f"  LiveBench: parsed {len(out)} entries")
    return out


def parse_lmarena(html_text: str, verbose: bool = False) -> dict:
    """
    Parse Arena.ai / LMSYS Arena HTML leaderboard table.
    Returns: dict[model_slug -> {rank, elo, votes, price_raw, context_raw, score_raw}]
    """
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.S)
    if verbose:
        print(f"  LMArena: found {len(trs)} tr rows")
    out = {}
    for tr in trs[1:]:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(cells) < 7:
            continue
        rank_raw = re.sub(r"<[^>]+>", "", cells[0]).strip()
        m_title = re.search(r'title="([^"]+)"', cells[2]) or re.search(r'title="([^"]+)"', tr)
        if m_title:
            slug = m_title.group(1).strip().lower()
        else:
            href_m = re.search(r'href="[^"]*?/([^"/\?]+)', cells[2])
            slug = href_m.group(1).lower() if href_m else ""
            if not slug or ("." not in slug and "-" not in slug):
                text = re.sub(r"<[^>]+>", " ", cells[2]).strip()
                tokens = re.findall(r"[a-z0-9][a-z0-9\.\-]*", text.lower())
                with_digit = [t for t in tokens if any(ch.isdigit() for ch in t) and ("-" in t or "." in t)]
                if with_digit:
                    slug = with_digit[-1]
                elif tokens:
                    slug = tokens[-1]
        if not slug:
            continue
        slug = slug.strip().lower()
        score_raw = re.sub(r"<[^>]+>", "", cells[3]).strip()
        elo = score_raw.split("±")[0].strip()
        elo_f = _safe_float(elo)
        rank_i = _safe_int(rank_raw)
        votes_raw = re.sub(r"<[^>]+>", "", cells[4]).strip().replace(",", "")
        votes_i = _safe_int(votes_raw)
        price_raw = re.sub(r"<[^>]+>", " ", cells[5]).strip()
        ctx_raw = re.sub(r"<[^>]+>", "", cells[6]).strip()

        out[slug] = {
            "rank": rank_i,
            "elo": elo_f,
            "votes": votes_i,
            "price_raw": price_raw,
            "context_raw": ctx_raw,
            "score_raw": score_raw,
        }
    if verbose:
        print(f"  LMArena: parsed {len(out)} entries")
    return out


def parse_aa(html_text: str, verbose: bool = False) -> dict:
    """
    Parse Artificial Analysis leaderboard from its Next.js App Router RSC-streamed
    page payload (no static __NEXT_DATA__ blob; data ships escaped inside a
    `self.__next_f.push(...)` chunk as a `"models":[...]` array).
    Returns: dict[model_slug -> {slug, name, intelligenceIndex, codingIndex, agenticIndex, medianTps, price_in, price_out}]
    """
    unescaped = html_text.replace('\\"', '"').replace("\\/", "/")
    idxs = []
    pos = 0
    while True:
        idx = unescaped.find('"models":[', pos)
        if idx == -1:
            break
        idxs.append(idx)
        pos = idx + 1
    if not idxs:
        if verbose:
            print("  Artificial Analysis: no models array found", file=sys.stderr)
        return {}

    # Pick the largest "models":[...] array that actually carries score data
    # (the payload repeats a slimmer nav/marketing copy of the array elsewhere).
    best_idx, best_end, best_len = -1, -1, -1
    for idx in idxs:
        if "intelligenceIndex" not in unescaped[idx: idx + 3000]:
            continue
        start = idx + len('"models":[')
        depth, p, in_str, esc = 1, start, False, False
        while p < len(unescaped) and depth > 0:
            c = unescaped[p]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
            p += 1
        if (p - idx) > best_len:
            best_len, best_idx, best_end = (p - idx), idx, p
    if best_idx == -1:
        if verbose:
            print("  Artificial Analysis: no intelligenceIndex array found", file=sys.stderr)
        return {}

    out = {}
    try:
        seg = unescaped[best_idx:best_end]
        models = json.loads("{" + seg + "}")["models"]
        for m in models:
            slug = m.get("slug")
            if not slug:
                continue
            out[slug] = {
                "slug": slug,
                "name": m.get("name") or m.get("shortName") or slug,
                "intelligenceIndex": _safe_float(m.get("intelligenceIndex")),
                "codingIndex": _safe_float(m.get("codingIndex")),
                "agenticIndex": _safe_float(m.get("agenticIndex")),
                "medianTps": _safe_float(m.get("medianOutputTokensPerSecond")),
                "price_in": _safe_float(m.get("price1mInputTokens")),
                "price_out": _safe_float(m.get("price1mOutputTokens")),
            }
    except Exception as e:
        if verbose:
            print(f"  WARN Artificial Analysis parse: {e}", file=sys.stderr)
        return {}
    if verbose:
        print(f"  Artificial Analysis: parsed {len(out)} models")
    return out


def parse_openrouter(data_json: str | dict, verbose: bool = False) -> dict:
    """
    Parse OpenRouter /api/v1/models JSON payload.
    Returns: dict[model_id -> {id, name, context, prompt_price_1m, completion_price_1m, is_free, ...}]
    """
    if isinstance(data_json, str):
        try:
            data = json.loads(data_json)
        except Exception as e:
            if verbose:
                print(f"  WARN OpenRouter JSON parse error: {e}", file=sys.stderr)
            return {}
    else:
        data = data_json

    out = {}
    items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    for rec in items:
        oid = rec.get("id", "")
        if not oid:
            continue
        pricing = rec.get("pricing", {}) or {}
        p_prompt = _safe_float(pricing.get("prompt"))
        p_comp = _safe_float(pricing.get("completion"))
        ctx = _safe_int(rec.get("context_length"))
        is_free = oid.endswith(":free") or (p_prompt == 0.0 and p_comp == 0.0)

        out[oid] = {
            "id": oid,
            "name": rec.get("name") or oid,
            "context": ctx,
            "prompt_price_1m": (p_prompt * 1_000_000.0) if p_prompt is not None else None,
            "completion_price_1m": (p_comp * 1_000_000.0) if p_comp is not None else None,
            "is_free": is_free,
            "is_stealth": oid.startswith("stealth/"),
            "created": rec.get("created"),
        }
    if verbose:
        print(f"  OpenRouter: parsed {len(out)} models")
    return out


# ==============================================================================
# 5. CLI & ANSI DISPLAY FORMATTING UTILITIES
# ==============================================================================
def display_len(text: str) -> int:
    """Return true visible terminal width: strips ANSI escapes, counts wide/emoji glyphs as 2 columns."""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", str(text))
    w = 0
    for ch in clean:
        if ord(ch) in (0x1F947, 0x1F948, 0x1F949, 0x1F3C6, 0x26A1) or (0x1F300 <= ord(ch) <= 0x1FAFF):
            w += 2
        else:
            w += 1
    return w


def color_cell(text, color: str = "", width: int | None = None, align: str = "<", bg: str = "") -> str:
    """Format and align text cell with background/foreground color and exact padding."""
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


def pad_banner(title: str, fill_or_width=None, width: int = 120, fill: str = "=") -> str:
    """
    Render centered banner or padded string with fill characters.
    Supports pad_banner(title, width=120, fill="="), pad_banner(title, "="), or pad_banner(title, 120).
    """
    actual_width = width
    actual_fill = fill
    if isinstance(fill_or_width, int):
        actual_width = fill_or_width
        actual_fill = fill if fill != "=" else " "
    elif isinstance(fill_or_width, str):
        actual_fill = fill_or_width

    dlen = display_len(title)
    if dlen >= actual_width:
        return str(title)
    total_pad = actual_width - dlen
    if actual_fill == " ":
        return str(title) + (" " * total_pad)
    left_pad = total_pad // 2
    right_pad = total_pad - left_pad
    return f"{actual_fill * left_pad}{title}{actual_fill * right_pad}"


def medal_badge(rank_num: int | None, color: bool = True) -> str:
    """Return superscript medal indicator: ¹ (Gold), ² (Silver), ³ (Bronze)."""
    if not rank_num:
        return ""
    char = {1: "¹", 2: "²", 3: "³"}.get(rank_num, "")
    if not color:
        return char
    colr = {1: C_BOLD + C_GOLD, 2: C_BOLD + C_SILVER, 3: C_BOLD + C_BRONZE}.get(rank_num, "")
    return f"{colr}{char}{C_RESET}"


def score_color_q(q_val: float | None) -> str:
    """Return color for Capability Q."""
    if q_val is None:
        return C_DIM
    if q_val >= 85.0:
        return C_BOLD + C_GREEN
    if q_val >= 75.0:
        return C_BOLD + C_CYAN
    if q_val >= 65.0:
        return C_YELLOW
    return C_GRAY


def score_color_p(p_val: float | None) -> str:
    """Return color for Pass Probability P_succ."""
    if p_val is None:
        return C_DIM
    if p_val >= 80.0:
        return C_GREEN
    if p_val >= 60.0:
        return C_CYAN
    if p_val >= 40.0:
        return C_YELLOW
    return C_GRAY


def score_color_avi(avi_val: float | None) -> str:
    """Return color for Agentic Value Index (AVI). Calibrated against AVI's
    real ~100-600 output range (Q^2.2/log(effective_cost) formula)."""
    if avi_val is None:
        return C_DIM
    if avi_val >= 300.0:
        return C_GREEN
    if avi_val >= 200.0:
        return C_CYAN
    if avi_val >= 140.0:
        return C_YELLOW
    return C_WHITE


def score_color_fgi(fgi_val: float | None) -> str:
    """Return color for Frontier Gate Index (FGI)."""
    if fgi_val is None:
        return C_DIM
    if fgi_val >= 70.0:
        return C_BOLD + C_PURPLE
    if fgi_val >= 50.0:
        return C_GREEN
    if fgi_val >= 30.0:
        return C_CYAN
    return C_GRAY


def compute_column_medals(models_list, col_keys, id_key="display"):
    """
    Compute top-3 ranks per column to attach 1st/2nd/3rd (superscript ¹²³ via
    medal_badge) badges to table cells. Generic over any row shape/column set.

    col_keys: dict of col_name -> (value_fn(row), reverse: bool, filter_fn(row)|None).
    id_key: the row dict key that uniquely identifies a row (e.g. "display" for
    bcheck's flat catalog rows, "model_id" for ocheck/fcheck/scheck's rows).
    Returns: dict[row_id -> dict[col_name -> rank(1|2|3)]]
    """
    col_medals = {}
    for col, (fn, rev, filt) in col_keys.items():
        valid = [m for m in models_list if filt(m)] if filt else models_list
        sorted_col = sorted(valid, key=fn, reverse=rev)
        for pos, m in enumerate(sorted_col[:3]):
            mid = m.get(id_key)
            if mid is None:
                continue
            if mid not in col_medals:
                col_medals[mid] = {}
            col_medals[mid][col] = pos + 1
    return col_medals


def _pad_to_width(line, target_w):
    """Truncate-or-left-pad a (possibly ANSI-colored) line to an exact visible width."""
    dlen = display_len(line)
    if dlen > target_w:
        clean = re.sub(r"\x1b\[[0-9;]*m", "", str(line))
        return clean[:target_w]
    return str(line) + (" " * max(0, target_w - dlen))


def render_banner_box(
    title,
    summary_lines=None,
    diff_notices=None,
    inner_w=100,
    color=True,
    plain_title_line=None,
    plain_diff_parts=None,
    box_color=None,
):
    """
    Shared rounded-box (color) / `=`-rule (plain) banner used atop every
    checker's main CLI table. Callers pre-format their own title/summary/diff
    text (business logic stays local); this only handles box-drawing + padding.

    color mode: title on its own row, each entry in summary_lines on its own
    dim row, then an optional diff-notice row — all inside a ╭─╮/╰─╯ box.
    plain mode: a single `plain_title_line` (falls back to `title`), then an
    optional single diff line built from `plain_diff_parts` joined by " | ",
    wrapped in `=` full-width rules.
    """
    box_color = box_color or C_CYAN
    out = []
    if color:
        out.append(f"{box_color}╭{'─' * inner_w}╮{C_RESET}")
        out.append(f"{box_color}│{C_RESET} {C_BOLD}{C_WHITE}{_pad_to_width(title, inner_w - 2)}{C_RESET} {box_color}│{C_RESET}")
        for line in (summary_lines or []):
            out.append(f"{box_color}│{C_RESET}{C_DIM} {_pad_to_width(line, inner_w - 2)} {C_RESET}{box_color}│{C_RESET}")
        if diff_notices:
            diff_line = " │ ".join(diff_notices)
            out.append(f"{box_color}│{C_RESET} {_pad_to_width(diff_line, inner_w - 2)} {C_RESET}{box_color}│{C_RESET}")
        out.append(f"{box_color}╰{'─' * inner_w}╯{C_RESET}")
        out.append("")
    else:
        out.append("=" * (inner_w + 2))
        out.append(plain_title_line if plain_title_line is not None else title)
        if plain_diff_parts:
            out.append(" " + " | ".join(plain_diff_parts))
        out.append("=" * (inner_w + 2))
    return out


def render_metric_guide_cli(title, bullets, color=True):
    """
    Shared "🧭 ... Guide:" footer box. bullets: list of (label, description,
    label_color) tuples; label_color is a C_* constant applied in color mode
    only. Labels are left-padded to align every description at the same column.
    """
    if not bullets:
        return []
    label_w = max(display_len(lbl) for lbl, _, _ in bullets) + 1
    out = []
    if color:
        out.append(f"{C_BOLD}{C_CYAN}🧭 {title}:{C_RESET}")
        for lbl, desc, lbl_color in bullets:
            pad = " " * max(0, label_w - display_len(lbl))
            out.append(f"  • {C_BOLD}{lbl_color}{lbl}{C_RESET}{pad}{C_DIM}{desc}{C_RESET}")
    else:
        out.append(f"{title}:")
        for lbl, desc, _ in bullets:
            out.append(f"  • {lbl:<{label_w}}{desc}")
    return out


def color_ladder(val, checks, default_color=None):
    """
    Shared color-ladder pattern for metrics whose numeric breakpoints are
    script/unit-specific (e.g. ocheck's cost-per-request vs bcheck's
    cost-per-million-tokens) but whose tiered-color logic is the same
    everywhere: try each (predicate, color) in order, first match wins.

    checks: ordered list of (lambda v: bool, color) tuples, best tier first,
    e.g. [(lambda v: v < 0.002, C_GREEN), (lambda v: v < 0.01, C_CYAN), ...].
    """
    if val is None:
        return default_color if default_color is not None else C_DIM
    for pred, col in checks:
        if pred(val):
            return col
    return default_color if default_color is not None else C_DIM


def pool_badge(pool: str, color: bool = True) -> str:
    """Return colored pool tag badge (e.g. [CLD], [AGY], [OCG], [FRT], [OR], [STEALTH])."""
    p = pool.lower().strip()
    tag = pool.upper()[:4]
    if p in ("claude", "cld"):
        col = C_CLAUDE
        tag = "CLD"
    elif p in ("agy", "gemini", "google"):
        col = C_AGY
        tag = "AGY"
    elif p in ("ocgo", "opencode", "oc"):
        col = C_OCGO
        tag = "OCG" if p != "oc" else "OC"
    elif p in ("frontier", "frt"):
        col = C_FRONTIER
        tag = "FRT"
    elif p in ("openrouter", "or"):
        col = C_OPENROUTER
        tag = "OR"
    elif p in ("cline", "cln"):
        col = C_CLINE
        tag = "CLN"
    elif p in ("stealth", "stl"):
        col = C_MAGENTA
        tag = "STL"
    else:
        col = C_WHITE
        tag = tag[:3]

    if not color:
        return f"[{tag}]"
    return f"{C_BOLD}{col}[{tag}]{C_RESET}"


# ==============================================================================
# 6. UNIFIED HTML DASHBOARD TEMPLATE GENERATOR
# ==============================================================================
HTML_CSS_COMMON = """
:root {
  --bg: #0d1117;
  --card: #161b22;
  --card-hover: #1c2128;
  --line: #30363d;
  --txt: #e6edf3;
  --mut: #8b949e;
  --gr: #3fb950;
  --bl: #58a6ff;
  --yl: #d29922;
  --pur: #a371f7;
  --red: #f85149;
  --amber: #f59e0b;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--txt);
  font: 13.5px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  padding: 28px;
}
.wrap { max-width: 1360px; margin: 0 auto; }
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px 18px;
  margin: 16px 0;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
  margin: 10px 0;
}
th, td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: middle;
}
th {
  color: var(--mut);
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  background: rgba(22, 27, 34, 0.95);
}
th:hover { color: var(--bl); }
tr:hover { background: rgba(56, 139, 253, 0.04); }
td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 10.5px;
  letter-spacing: 0.3px;
}
.badge-gold { background: rgba(210,153,34,0.18); color: #d29922; border: 1px solid #d29922; }
.badge-new { background: rgba(63,185,80,0.2); color: #3fb950; border: 1px solid #3fb950; }
.badge-removed { background: rgba(248,81,73,0.2); color: #f85149; border: 1px solid #f85149; }
.badge-cld { background: rgba(217,119,6,0.15); color: #d97706; }
.badge-agy { background: rgba(59,130,246,0.15); color: #3b82f6; }
.badge-ocg { background: rgba(16,185,129,0.15); color: #10b981; }
.badge-frt { background: rgba(139,92,246,0.15); color: #8b5cf6; }
.badge-or { background: rgba(6,182,212,0.15); color: #06b6d4; }
.badge-cln { background: rgba(14,165,233,0.15); color: #0ea5e9; }
.badge-stl { background: rgba(244,63,94,0.18); color: #f43f5e; border: 1px solid #f43f5e; }
tr.added { background: rgba(63, 185, 80, 0.08) !important; }
tr.added td.m, tr.added td:first-child { color: #3fb950 !important; font-weight: 700; }
.removed-section { background: rgba(248,81,73,0.06); border: 1px solid rgba(248,81,73,0.25); border-radius: 8px; padding: 14px 16px; margin: 16px 0; }
.removed-title { color: #f85149; font-weight: 700; font-size: 13.5px; margin-bottom: 6px; }
.removed-tag { display: inline-block; background: rgba(248,81,73,0.12); color: #ff7b72; border: 1px solid rgba(248,81,73,0.25); border-radius: 4px; padding: 3px 8px; font-family: monospace; font-size: 11.5px; margin: 3px 6px 3px 0; }
.legend { color: var(--mut); font-size: 11px; margin-top: 10px; }
.footer {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 18px;
  border-top: 1px solid var(--line);
  padding-top: 12px;
}
.footer .path { color: var(--mut); font-size: 12px; }
.footer .work { color: var(--txt); font-size: 12px; font-style: italic; }
tr.pareto { background: rgba(210,153,34,0.18); border-left: 3px solid #d29922; }
tr.flagship { background: rgba(63,185,80,0.07); }
tr.value { background: rgba(88,166,255,0.07); }
tr.free { opacity: 0.6; }
.sub { color: var(--mut); margin: 0 0 14px; font-size: 13px; }
.m { font-weight: 600; }
.mid { display: block; color: var(--mut); font-size: 10px; font-weight: 400; white-space: nowrap; }
.call { background: var(--card); border: 1px solid var(--line); border-left: 3px solid var(--yl); border-radius: 8px; padding: 12px 16px; margin: 14px 0; }
.call b { color: var(--yl); }
.note { color: var(--mut); font-size: 12px; margin-top: 14px; border-top: 1px solid var(--line); padding-top: 10px; }
"""

HTML_SORT_SCRIPT = """
<script>
(function(){
  var tbl = document.getElementById('tbl');
  if(!tbl) return;
  function getVal(tr, i){
    var td = tr.children[i];
    if(!td) return '';
    var t = (td.innerText || '').replace(/[^0-9.\\-]/g, '').trim();
    var n = parseFloat(t);
    return isNaN(n) ? (td.innerText || '').toLowerCase() : n;
  }
  tbl.querySelectorAll('th').forEach(function(th, i){
    th.addEventListener('click', function(){
      var tbody = tbl.tBodies[0];
      var rows = [].slice.call(tbody.rows);
      var asc = th.asc = !th.asc;
      rows.sort(function(a, b){
        var av = getVal(a, i), bv = getVal(b, i);
        if(typeof av === 'number' && typeof bv === 'number') return asc ? av - bv : bv - av;
        return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      });
      rows.forEach(function(r){ tbody.appendChild(r); });
    });
  });
})();
</script>
"""


# ==============================================================================
# 7. DYNAMIC ROLE & FUNCTION RECOMMENDATIONS (SOFTWARE ENGINEERING)
# ==============================================================================
def _extract_model_role_features(m: dict, context: str = "bcheck") -> dict:
    """Standardize model metrics for role scoring across bcheck and ocheck."""
    raw_name = m.get("display") or m.get("model_id") or "Unknown"
    name = re.sub(r"\s*\([^)]*\)", "", raw_name).strip()
    
    # Pool / Limit badge
    if context == "ocheck":
        usage = m.get("pricing", {}).get("monthly_usage_limit_usd")
        if usage == 60:
            pool_str = "$60/m"
        elif usage == 30:
            pool_str = "$30/m"
        elif usage == 15:
            pool_str = "$15/m"
        elif usage is None:
            pool_str = "Free"
        else:
            pool_str = f"${usage}/m"
    else:
        p = (m.get("pool") or "").upper()
        pool_str = {"CLAUDE": "[CLD]", "AGY": "[AGY]", "OCGO": "[OCG]", "FRONTIER": "[FRT]"}.get(p, f"[{p[:3]}]" if p else "[API]")

    q = _safe_float(m.get("capability_q") or m.get("benchmarks", {}).get("capability_q") or m.get("composite_score"), default=70.0)
    fgi = _safe_float(m.get("fgi_score") or m.get("value", {}).get("fgi_score") or m.get("benchmarks", {}).get("fgi_score"), default=30.0)
    avi = _safe_float(m.get("avi_score") or m.get("value", {}).get("avi_score") or m.get("benchmarks", {}).get("avi_score"), default=150.0)
    bfi = _safe_float(m.get("bfi_score") or m.get("value", {}).get("bfi_score") or m.get("benchmarks", {}).get("bfi_score"), default=150.0)
    psucc = _safe_float(m.get("p_success") or m.get("benchmarks", {}).get("p_success"), default=50.0)
    
    eff_cost = _safe_float(m.get("effective_cost") or m.get("value", {}).get("effective_cost_per_request") or m.get("cost_per_request_usd"), default=10.0)
    if eff_cost is None or eff_cost <= 0.0:
        eff_cost = 0.0001
        
    coding = _safe_float(
        m.get("base_metrics", {}).get("lm_coding")
        or m.get("benchmarks", {}).get("aa_coding")
        or (m.get("livebench", {}).get("coding") if isinstance(m.get("livebench"), dict) else None)
        or (m.get("benchmarks", {}).get("livebench", {}).get("coding") if isinstance(m.get("benchmarks", {}).get("livebench"), dict) else None),
        default=None,
    )
    
    reasoning = _safe_float(
        m.get("arc_agi")
        or m.get("benchmarks", {}).get("aa_intelligence")
        or m.get("base_metrics", {}).get("aa_reasoning")
        or (m.get("livebench", {}).get("reasoning") if isinstance(m.get("livebench"), dict) else None),
        default=None,
    )
    
    req_cnt = (m.get("requests", {}).get("per_5h_docs") or m.get("requests", {}).get("per_5h_computed") or 0) if m.get("requests") else 0
    speed = _safe_float(
        m.get("base_metrics", {}).get("speed_tps")
        or m.get("benchmarks", {}).get("aa_median_tps")
        or (req_cnt / 100.0 if req_cnt else None),
        default=60.0,
    )

    return {
        "raw": m,
        "name": name,
        "pool_str": pool_str,
        "q": q,
        "fgi": fgi,
        "avi": avi,
        "bfi": bfi,
        "psucc": psucc,
        "eff_cost": eff_cost,
        "coding": coding,
        "reasoning": reasoning,
        "speed": speed,
    }


def compute_role_recommendations(models_list: list[dict], context: str = "bcheck") -> dict[str, dict]:
    """
    Compute dynamic role & function recommendations via weighted multi-metric Z-scores.
    
    Roles:
      1. architecture: System Architecture & Complex Design (Spec Lock / Deep Logic)
      2. pair_programming: Pair Programming & Code Editing (Interactive Refactoring & Diffs)
      3. daily_driver: Daily Driver / Value Workhorse (Highest Agentic ROI)
      4. boilerplate: Fast Boilerplate & Scaffolding (Mechanical Code Gen)
    """
    if not models_list:
        return {}

    feats = [_extract_model_role_features(m, context=context) for m in models_list]
    
    # Calculate baseline Z-scores
    z_q = get_z_scores([f["q"] for f in feats])
    z_fgi = get_z_scores([f["fgi"] for f in feats])
    z_avi = get_z_scores([f["avi"] for f in feats])
    z_bfi = get_z_scores([f["bfi"] for f in feats])
    z_psucc = get_z_scores([f["psucc"] for f in feats])
    z_speed = get_z_scores([f["speed"] for f in feats])
    
    # Invert log cost so lower cost gives higher score
    inv_log_costs = [-math.log10(max(0.00001, f["eff_cost"])) for f in feats]
    z_cost = get_z_scores(inv_log_costs)
    
    # Fill missing coding / reasoning with z_q
    cod_vals = [f["coding"] if f["coding"] is not None else f["q"] for f in feats]
    z_coding = get_z_scores(cod_vals)
    
    reas_vals = [f["reasoning"] if f["reasoning"] is not None else f["q"] for f in feats]
    z_reasoning = get_z_scores(reas_vals)

    scored_arch = []
    scored_pair = []
    scored_driver = []
    scored_boiler = []

    for i, f in enumerate(feats):
        # 1. Architecture: High FGI + Q + Reasoning
        s_arch_raw = (0.40 * z_fgi[i]) + (0.30 * z_q[i]) + (0.30 * z_reasoning[i])
        s_arch = round(max(50.0, min(99.9, 80.0 + (s_arch_raw * 7.0))), 1)
        scored_arch.append((s_arch, f))

        # 2. Pair Programming: Coding performance + Q + AVI + P_succ
        s_pair_raw = (0.35 * z_coding[i]) + (0.30 * z_q[i]) + (0.20 * z_avi[i]) + (0.15 * z_psucc[i])
        s_pair = round(max(50.0, min(99.9, 80.0 + (s_pair_raw * 7.0))), 1)
        scored_pair.append((s_pair, f))

        # 3. Daily Driver Workhorse: High AVI ROI + Q + Cost Efficiency
        s_driver_raw = (0.50 * z_avi[i]) + (0.30 * z_q[i]) + (0.20 * z_cost[i])
        s_driver = round(max(50.0, min(99.9, 80.0 + (s_driver_raw * 7.0))), 1)
        scored_driver.append((s_driver, f))

        # 4. Boilerplate & Fast Fill: BFI + Speed + Cost (gated to Q >= 64 to avoid corrupt code)
        if f["q"] >= 64.0:
            s_boiler_raw = (0.45 * z_bfi[i]) + (0.30 * z_speed[i]) + (0.25 * z_cost[i])
            s_boiler = round(max(50.0, min(99.9, 80.0 + (s_boiler_raw * 7.0))), 1)
        else:
            s_boiler = 45.0
        scored_boiler.append((s_boiler, f))

    scored_arch.sort(key=lambda x: x[0], reverse=True)
    scored_pair.sort(key=lambda x: x[0], reverse=True)
    scored_driver.sort(key=lambda x: x[0], reverse=True)
    scored_boiler.sort(key=lambda x: x[0], reverse=True)

    def _pack_role(scored_list, title, label_short, icon, desc, desc_short):
        w_score, w_f = scored_list[0] if scored_list else (0.0, {})
        r_score, r_f = scored_list[1] if len(scored_list) > 1 else (0.0, {})
        return {
            "title": title,
            "label_short": label_short,
            "icon": icon,
            "desc": desc,
            "desc_short": desc_short,
            "winner": {
                "name": w_f.get("name", "—"),
                "pool_str": w_f.get("pool_str", ""),
                "score": w_score,
                "q": w_f.get("q", 0.0),
                "fgi": w_f.get("fgi", 0.0),
                "avi": w_f.get("avi", 0.0),
            },
            "runner_up": {
                "name": r_f.get("name", "—"),
                "pool_str": r_f.get("pool_str", ""),
                "score": r_score,
                "q": r_f.get("q", 0.0),
                "fgi": r_f.get("fgi", 0.0),
                "avi": r_f.get("avi", 0.0),
            },
        }

    return {
        "architecture": _pack_role(
            scored_arch,
            "System Architecture & Complex Design",
            "Architecture",
            "🏗️",
            "Deep reasoning & high FGI gates. Use for contracts, spec lock, and hard debugging.",
            "High FGI & reasoning gates. Use for spec lock and deep debugging.",
        ),
        "pair_programming": _pack_role(
            scored_pair,
            "Pair Programming & Code Editing",
            "Pair Coder",
            "💻",
            "Surgical diffs, coding Elo & multi-turn alignment without drift.",
            "Surgical diffs, coding Elo & alignment without drift.",
        ),
        "daily_driver": _pack_role(
            scored_driver,
            "Daily Driver (High ROI Workhorse)",
            "Daily Driver",
            "🔄",
            "Top AVI & cost-efficiency. Autonomous loops without token explosion.",
            "Top AVI & cost-efficiency. Loops without token runaway.",
        ),
        "boilerplate": _pack_role(
            scored_boiler,
            "Fast Boilerplate & Mechanical Fill",
            "Boilerplate",
            "⚡",
            "High throughput (TPS/BFI) for mechanical generation and test scaffolding.",
            "High TPS & low cost for mechanical fill & scaffolding.",
        ),
    }


def render_role_recommendations_cli(role_recs: dict[str, dict], color: bool = True, is_slim: bool = False, width: int = 100) -> list[str]:
    """Render ANSI-formatted CLI role recommendations box."""
    if not role_recs:
        return []

    out = []
    title_text = "🎯 ROLE & FUNCTION RECOMMENDATIONS (Weighted Multi-Metric Selection):" if not is_slim else "🎯 ROLE RECOMMENDATIONS (Weighted Selection):"
    
    if color:
        out.append(f"{C_BOLD}{C_GOLD}{title_text}{C_RESET}")
    else:
        out.append(title_text)

    for role_key, r in role_recs.items():
        w = r["winner"]
        ru = r["runner_up"]
        label = r["title"] if not is_slim else r["label_short"]
        desc = r["desc"] if not is_slim else r["desc_short"]
        icon = r["icon"]

        w_name = w["name"][:24] if not is_slim else w["name"][:18]
        ru_name = ru["name"][:24] if not is_slim else ru["name"][:17]
        lbl_w = 34 if not is_slim else 14
        lbl_pad = f"{label:<{lbl_w}}"

        if color:
            c_icon = C_BOLD + C_WHITE
            c_label = C_BOLD + C_CYAN
            c_win = C_BOLD + C_GREEN
            c_ru = C_SILVER
            c_desc = C_DIM
            c_score = C_YELLOW
            
            line1 = f"  • {icon} {c_label}{lbl_pad}{C_RESET}: {c_win}{w_name}{C_RESET} {w['pool_str']} ({c_score}{w['score']:.1f}{C_RESET}) · {C_DIM}Runner-up:{C_RESET} {c_ru}{ru_name}{C_RESET} {ru['pool_str']} ({ru['score']:.1f})"
            line2 = f"       {C_DIM}↳ {desc}{C_RESET}"
        else:
            line1 = f"  • {icon} {lbl_pad}: {w_name} {w['pool_str']} ({w['score']:.1f}) · Runner-up: {ru_name} {ru['pool_str']} ({ru['score']:.1f})"
            line2 = f"       ↳ {desc}"

        out.append(line1)
        out.append(line2)

    return out


def render_role_recommendations_md(role_recs: dict[str, dict]) -> str:
    """Render markdown table of role recommendations."""
    if not role_recs:
        return ""

    lines = [
        "### Dynamic Function & Role Recommendations (Weighted Scoring)",
        "",
        "| Function / Role | 🥇 Recommended Winner | 🥈 Runner-Up | Tactical Guidance |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for role_key, r in role_recs.items():
        w = r["winner"]
        ru = r["runner_up"]
        win_str = f"**{w['name']}** `{w['pool_str']}` *(Score: {w['score']:.1f})*"
        ru_str = f"**{ru['name']}** `{ru['pool_str']}` *({ru['score']:.1f})*"
        lines.append(f"| {r['icon']} **{r['title']}** | {win_str} | {ru_str} | {r['desc']} |")

    return "\n".join(lines)


def render_role_recommendations_html(role_recs: dict[str, dict]) -> str:
    """Render HTML cards/table of role recommendations."""
    if not role_recs:
        return ""

    rows = []
    for role_key, r in role_recs.items():
        w = r["winner"]
        ru = r["runner_up"]
        rows.append(f"""
        <tr>
            <td style="font-weight:600; color:#38bdf8;">{r['icon']} {html_lib.escape(r['title'])}</td>
            <td><b>{html_lib.escape(w['name'])}</b> <span class="badge badge-gold">{html_lib.escape(w['pool_str'])}</span> <span style="color:#10b981; font-weight:700;">({w['score']:.1f})</span></td>
            <td><b>{html_lib.escape(ru['name'])}</b> <span class="badge">{html_lib.escape(ru['pool_str'])}</span> <span style="color:#94a3b8;">({ru['score']:.1f})</span></td>
            <td style="color:#94a3b8; font-size:12px;">{html_lib.escape(r['desc'])}</td>
        </tr>
        """)

    return f"""
    <div class="card">
        <h3 style="margin-top:0; color:#38bdf8; font-size:15px;">🎯 Dynamic Function & Role Recommendations (Weighted Multi-Metric Selection)</h3>
        <table>
            <thead>
                <tr>
                    <th>Function / Role</th>
                    <th>🥇 Recommended Winner</th>
                    <th>🥈 Runner-Up</th>
                    <th>Tactical Guidance</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """


# ==============================================================================
# 8. CATALOG DIFFING & BASELINE SNAPSHOT MANAGEMENT (GREEN ADD / RED REMOVAL)
# ==============================================================================

def load_previous_snapshot(json_path: pathlib.Path | str) -> list[dict] | dict | None:
    """Load previously saved live snapshot JSON file if it exists."""
    target = pathlib.Path(json_path)
    if target.is_file():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def parse_timestamp(val) -> dt.datetime | None:
    """Parse ISO 8601 string, numeric epoch (seconds/ms), or string timestamp to timezone-aware UTC datetime."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            if val > 1e11:  # Epoch milliseconds
                val = val / 1000.0
            return dt.datetime.fromtimestamp(val, tz=dt.timezone.utc)
        except Exception:
            return None
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        # Try ISO 8601 string
        try:
            iso_str = val.replace("Z", "+00:00")
            parsed = dt.datetime.fromisoformat(iso_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        except Exception:
            pass
        # Try numeric string
        try:
            num = float(val)
            if num > 1e11:
                num = num / 1000.0
            return dt.datetime.fromtimestamp(num, tz=dt.timezone.utc)
        except Exception:
            pass
    return None


def diff_model_catalog(
    current_rows: list[dict],
    prev_snapshot: list[dict] | dict | None,
    id_key: str = "model_id",
    window_days: float = 7.0,
    now: dt.datetime | None = None
) -> dict:
    """Compute added (green) and removed (red) models comparing current rows to previous baseline snapshot.

    Persists and propagates 'first_seen' timestamps across runs so that newly added models
    remain highlighted in green for up to `window_days` (default 7 days).
    """
    now_dt = now or dt.datetime.now(dt.timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=dt.timezone.utc)

    def _extract_id(r: dict) -> str | None:
        if not isinstance(r, dict):
            return None
        return r.get(id_key) or r.get("model_id") or r.get("display") or r.get("or_slug") or r.get("id")

    prev_models_map = {}
    has_prev_snapshot = False

    if isinstance(prev_snapshot, dict):
        has_prev_snapshot = True
        prev_models_list = prev_snapshot.get("models", [])
        has_catalog_diff = "catalog_diff" in prev_snapshot
    elif isinstance(prev_snapshot, list):
        has_prev_snapshot = True
        prev_models_list = prev_snapshot
        has_catalog_diff = False
    else:
        prev_models_list = []
        has_catalog_diff = False

    for m in prev_models_list:
        if isinstance(m, dict):
            mid = _extract_id(m)
            if mid:
                # In ocheck snapshots, filter to docs-backed models when is_docs_model tag is used
                if id_key == "model_id" and has_catalog_diff and not m.get("is_docs_model"):
                    continue
                prev_models_map[mid] = m

    current_ids = set()
    added_ids = set()

    for r in current_rows:
        if not isinstance(r, dict):
            continue
        mid = _extract_id(r)
        if not mid:
            continue
        current_ids.add(mid)

        # 1. Resolve first_seen timestamp
        first_seen_str = r.get("first_seen")
        prev_m = prev_models_map.get(mid)

        if not first_seen_str and prev_m:
            first_seen_str = prev_m.get("first_seen")

        # Check API creation date (e.g. OpenRouter "created" integer or string)
        created_val = r.get("created") or r.get("created_date")
        if not first_seen_str and created_val is not None:
            created_dt = parse_timestamp(created_val)
            if created_dt:
                first_seen_str = created_dt.isoformat()

        # If brand new model unseen in previous snapshot
        is_brand_new = has_prev_snapshot and (mid not in prev_models_map)
        if not first_seen_str:
            if is_brand_new:
                first_seen_str = now_dt.isoformat()
            elif not has_prev_snapshot:
                # Cold start: initialize timestamp, but don't mark as green unless explicit created date
                first_seen_str = now_dt.isoformat()

        if first_seen_str:
            r["first_seen"] = first_seen_str

        # 2. Check if within freshness window (<= window_days)
        is_fresh = False
        parsed_first_seen = parse_timestamp(first_seen_str)
        if parsed_first_seen:
            age_days = (now_dt - parsed_first_seen).total_seconds() / 86400.0
            if 0 <= age_days <= window_days:
                # If cold start without prior snapshot, only mark green if it has explicit created date
                if has_prev_snapshot or created_val is not None:
                    is_fresh = True

        if is_fresh or is_brand_new:
            added_ids.add(mid)
            r["is_new"] = True
        else:
            r["is_new"] = False

    removed_ids = set(prev_models_map.keys()) - current_ids if has_prev_snapshot else set()
    removed_models = [prev_models_map[mid] for mid in sorted(removed_ids) if mid in prev_models_map]

    return {
        "added_ids": added_ids,
        "removed_ids": removed_ids,
        "removed_models": removed_models,
    }


def render_removed_models_cli(removed_models: list[dict], color: bool = True, is_slim: bool = False, id_key: str = "model_id") -> list[str]:
    """Format removed/deprecated models list as a red CLI section."""
    if not removed_models:
        return []

    lines = []
    if color:
        lines.append(f"{C_BOLD}{C_RED}🔻 REMOVED / DEPRECATED MODELS ({len(removed_models)}):{C_RESET}")
        for rm in removed_models:
            mid = rm.get(id_key) or rm.get("model_id") or rm.get("display") or rm.get("or_slug") or rm.get("id") or "unknown"
            details = []
            if "pricing" in rm and isinstance(rm["pricing"], dict):
                pr_lim = rm["pricing"].get("monthly_usage_limit_usd")
                lim_s = f"${pr_lim:.0f}/m" if pr_lim is not None else "Free"
                details.append(f"Prior Limit: {lim_s}")
            elif "pool" in rm:
                details.append(f"Pool: {rm.get('pool', '').upper()}")
            elif "provider" in rm:
                details.append(f"Prov: {rm.get('provider')}")

            fgi = rm.get("value", {}).get("fgi_score") if isinstance(rm.get("value"), dict) else None
            if fgi is None:
                fgi = rm.get("benchmarks", {}).get("fgi_score") if isinstance(rm.get("benchmarks"), dict) else rm.get("fgi_score")
            if fgi is not None and isinstance(fgi, (int, float)):
                details.append(f"FGI {fgi:.1f}")

            avi = rm.get("value", {}).get("avi_score") if isinstance(rm.get("value"), dict) else None
            if avi is None:
                avi = rm.get("benchmarks", {}).get("avi_score") if isinstance(rm.get("benchmarks"), dict) else rm.get("avi_score")
            if avi is not None and isinstance(avi, (int, float)):
                details.append(f"AVI {avi:.1f}")

            q_val = rm.get("benchmarks", {}).get("capability_q") if isinstance(rm.get("benchmarks"), dict) else rm.get("capability_q")
            if q_val is not None and isinstance(q_val, (int, float)) and fgi is None:
                details.append(f"Q {q_val:.1f}")

            detail_str = f" ({', '.join(details)})" if details else ""
            lines.append(f"  {C_RED}❌ {C_BOLD}{mid:<22}{C_RESET}{C_DIM}{detail_str}{C_RESET}")
    else:
        lines.append(f"REMOVED / DEPRECATED MODELS ({len(removed_models)}):")
        for rm in removed_models:
            mid = rm.get(id_key) or rm.get("model_id") or rm.get("display") or rm.get("or_slug") or rm.get("id") or "unknown"
            details = []
            if "pricing" in rm and isinstance(rm["pricing"], dict):
                pr_lim = rm["pricing"].get("monthly_usage_limit_usd")
                lim_s = f"${pr_lim:.0f}/m" if pr_lim is not None else "Free"
                details.append(f"Prior Limit: {lim_s}")
            elif "pool" in rm:
                details.append(f"Pool: {rm.get('pool', '').upper()}")
            elif "provider" in rm:
                details.append(f"Prov: {rm.get('provider')}")

            fgi = rm.get("value", {}).get("fgi_score") if isinstance(rm.get("value"), dict) else None
            if fgi is None:
                fgi = rm.get("benchmarks", {}).get("fgi_score") if isinstance(rm.get("benchmarks"), dict) else rm.get("fgi_score")
            if fgi is not None and isinstance(fgi, (int, float)):
                details.append(f"FGI {fgi:.1f}")

            avi = rm.get("value", {}).get("avi_score") if isinstance(rm.get("value"), dict) else None
            if avi is None:
                avi = rm.get("benchmarks", {}).get("avi_score") if isinstance(rm.get("benchmarks"), dict) else rm.get("avi_score")
            if avi is not None and isinstance(avi, (int, float)):
                details.append(f"AVI {avi:.1f}")

            detail_str = f" ({', '.join(details)})" if details else ""
            lines.append(f"  [-] {mid:<22}{detail_str}")

    return lines

