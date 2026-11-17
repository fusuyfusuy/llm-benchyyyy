#!/usr/bin/env python3
"""
benchmark_common.py — Shared mathematical scoring, parsers, normalization,
and coherent visual styling for bcheck, ocheck, fcheck, and scheck.

Zero external dependencies (pure Python 3 standard library).
"""
import contextlib
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
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

# ==============================================================================
# 1. ANSI COLOR CODES & THEME CONSTANTS
# ==============================================================================
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"

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
C_HETZNER = "\033[38;5;203m"   # Hetzner Red / Coral
C_NVIDIA = "\033[38;5;118m"    # NVIDIA Lime Green

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def fetch_url(url: str, timeout: int = 15) -> str | None:
    """Fetch URL with standard user agent header. Returns decoded UTF-8 string or None on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

# ==============================================================================
# 2. STRING NORMALIZATION & SAFE VALUE CONVERSIONS
# ==============================================================================
def norm_id(s: str) -> str:
    """Normalize model identifier to canonical lowercase kebab-case."""
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", "-", s)
    return re.sub(r"[^a-z0-9\.\-_]", "", s)


def norm_model_slug(s: str) -> str:
    """Normalize model identifier for strict version-safe comparison.

    Strips provider namespace (`vendor/model` or `vendor-model`) and folds
    whitespace into dashes before punctuation stripping so cross-source slugs
    (`anthropic/claude-opus-4.6` vs `Claude Opus 4.6`) align cleanly.
    """
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"^(?:[a-z0-9_.-]+/)+", "", s)
    s = re.sub(r"^(claude|anthropic|openai|google|meta|zhipu|z-ai|xiaomi|minimax|xai|moonshot|tencent)-", "", s)
    s = re.sub(r"^qwen-(\d)", r"qwen\1", s)
    s = s.replace(".", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def arena_base_key(s: str) -> str:
    """Loose Arena key: parenthetical qualifiers dropped, then tier tokens stripped.

    Arena names the same model by its sampling config (`Claude Opus 4.6 (High)`,
    `GPT-5.6 Sol (xHigh, Codex Harness)`) while the catalog names it by role
    (`Claude Opus 4.6 (Thinking)`), so the parenthetical carries no shared
    vocabulary. Used only as the last matching rung — digit tokens still
    separate versions (`qwen3-8-max` vs `qwen3-8-max-0902`).
    """
    if not s:
        return ""
    return strip_tier_tokens(re.sub(r"\([^)]*\)", " ", s))


def arena_token_key(s: str) -> str:
    """Order-insensitive Arena key: same tokens, any order.

    Arena reorders date/size qualifiers (`Claude Opus 4.5 (High, 32K, 20251101)`)
    where the catalog keeps them glued (`Claude Opus-4-5-20251101-high-32k`), so
    ordered comparison misses the row and spawns a duplicate. Sorted token
    multiset still separates versions and sizes (digits stay).
    """
    if not s:
        return ""
    s_norm = norm_model_slug(s)
    return "-".join(sorted(t for t in s_norm.split("-") if t and t not in TIER_TOKENS))


TIER_TOKENS = frozenset({
    "effort", "max", "xhigh", "high", "medium", "low", "minimal",
    "nothinking", "thinking", "non", "reasoning", "preview", "auto", "base",
    "none", "standard", "default", "next",
})

VARIANT_TOKENS = frozenset({
    "pro", "max", "ultra", "mini", "micro", "nano", "tiny", "small", "lite", "next",
    "omni", "exp", "experimental", "thinking", "high", "xhigh", "medium", "low", "minimal",
    "preview", "contributor", "coder", "codex", "instruct", "turbo", "flash", "nitro",
    "speed", "smart", "free", "fast", "r1", "r2", "plus", "heavy", "light", "air",
    "vision", "vl", "audio", "voice", "live", "non", "reasoning", "effort", "base",
})


def strip_tier_tokens(s: str) -> str:
    """Strip trailing effort/tier tokens from a normalized slug."""
    s_norm = norm_model_slug(s) or ""
    # Split 1.2-style digit+suffix glued tokens without catastrophic backtracking:
    # "model1.2xhigh" -> "model1.2-xhigh" via a single linear scan, no (\d+)(alt)$ regex.
    m = re.match(r"^(.*\d)[-_ ]?(xhigh|high|medium|low|minimal|max)$", s_norm)
    if m:
        s_norm = f"{m.group(1)}-{m.group(2)}"
    toks = s_norm.split("-")
    while toks and toks[-1] in TIER_TOKENS:
        toks.pop()
    return "-".join(toks)


def _id_tokens(norm: str) -> list[str]:
    """Tokenize a normalized model id; separators are [-_ ./ ], stray punctuation
    (e.g. the parens in 'model-1.2 (xhigh)') also splits, so variant tokens are
    detected regardless of the caller's normalizer."""
    return [t for t in re.split(r"[^a-z0-9]+", (norm or "").lower()) if t]


def variant_conflict(a_norm: str, b_norm: str) -> bool:
    """True when two normalized ids must NOT be treated as the same model.

    S1-C1/C2/C3 + S2-C2: a fuzzy fallback may only link ids when the shorter
    token list is a prefix run of the longer one and every surplus token on the
    longer side is neither a variant/tier token (pro, max, xhigh, codex, ...)
    nor a digit token (versions are load-bearing: qwen3-5 != qwen3-7).
    Any mid-list token divergence is a conflict.
    """
    ta, tb = _id_tokens(a_norm), _id_tokens(b_norm)
    if not ta or not tb:
        return True
    if ta == tb:
        return False
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if long[: len(short)] == short:
        return any(t in VARIANT_TOKENS or t.isdigit() for t in long[len(short):])
    return True


def atomic_write_text(path, text: str) -> None:
    """Write text to path atomically (tmp sibling + fsync + os.replace) — no torn tracked outputs or concurrent collisions."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()


_NA_STRINGS = frozenset({"", "nan", "none", "null", "undefined", "—", "-", "n/a"})


def _safe_float(val, default=None, strip_currency: bool = True):
    """Safely convert value to float or return default (bool/NaN/Inf-safe)."""
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        f = float(val)
        return f if math.isfinite(f) else default
    s = str(val).strip().replace(",", "").replace("%", "")
    if strip_currency:
        s = s.replace("$", "")
    elif "$" in s:
        return default
    if s.lower() in _NA_STRINGS:
        return default
    try:
        f = float(s)
    except (ValueError, TypeError):
        return default
    return f if math.isfinite(f) else default


def _safe_int(val, default=None, strip_currency: bool = True):
    """Safely convert value to rounded int or return default."""
    f = _safe_float(val, default=None, strip_currency=strip_currency)
    return int(round(f)) if f is not None else default


def _first_num(*vals):
    """Return the first value convertible to a finite float (preserving 0.0)."""
    for v in vals:
        f = _safe_float(v)
        if f is not None:
            return f
    return None


def compute_cost(input_per_1m, output_per_1m, cached_per_1m, est_input, est_cached, est_output, cached_write_per_1m=0.0, est_cached_write=0):
    """Request cost in dollars from per-1M rates and estimated token counts. Shared by ocheck/ccheck."""
    if None in (input_per_1m, output_per_1m, cached_per_1m) or None in (est_input, est_cached, est_output):
        return None
    c_write = (cached_write_per_1m or 0.0) * (est_cached_write or 0) / 1_000_000
    if est_input == 0 and est_cached == 0 and est_output == 0 and (est_cached_write or 0) == 0:
        return 0.0
    return (input_per_1m * est_input / 1_000_000) + (cached_per_1m * est_cached / 1_000_000) + (output_per_1m * est_output / 1_000_000) + c_write


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


CACHE_TTL_H = 24  # response-cache freshness window for default offline runs (rule 7)

_SNAP_DATE_RE = re.compile(r"_(\d{8})(?:\.[A-Za-z0-9]+)?$")


def snapshot_date_str(path) -> str | None:
    """YYYYMMDD embedded at the end of a raw-snapshot filename, or None.
    The filename date is the authoritative cache age — a git checkout/clone
    rewrites mtimes to "now" and would mask weeks-old data (S2-M2)."""
    m = _SNAP_DATE_RE.search(pathlib.Path(path).name)
    if not m:
        return None
    try:
        dt.datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        return None
    return m.group(1)


def snapshot_age_hours(path, now: dt.datetime | None = None) -> float:
    """Age of a raw snapshot in hours from its filename date when present,
    falling back to mtime for date-less files (S2-M2)."""
    p = pathlib.Path(path)
    now = now or dt.datetime.now(dt.UTC)
    ds = snapshot_date_str(p)
    if ds:
        d = dt.datetime.strptime(ds, "%Y%m%d").replace(tzinfo=dt.UTC)
        return max(0.0, (now - d).total_seconds() / 3600.0)
    return max(0.0, (now.timestamp() - p.stat().st_mtime) / 3600.0)


def staleness_tag(path) -> str:
    """Banner fragment for cache-only loaders: ' (Nd old — run with --fetch)'
    once past CACHE_TTL_H; stale data is still used, never re-fetched (rule 7)."""
    age = snapshot_age_hours(path)
    if age > CACHE_TTL_H:
        return f" ({age / 24:.0f}d old — run with --fetch)"
    return ""


def pick_latest_raw(raw_dir: pathlib.Path, name_part: str) -> pathlib.Path | None:
    """Newest snapshot in raw_dir whose filename matches name_part — ordered by
    the filename-embedded UTC date when present, else mtime (S2-M2)."""
    matches = glob.glob(str(raw_dir / f"*{name_part}*"))
    if not matches:
        return None

    def _rank(p):
        ds = snapshot_date_str(p)
        if ds:
            return dt.datetime.strptime(ds, "%Y%m%d").replace(tzinfo=dt.UTC).timestamp()
        return pathlib.Path(p).stat().st_mtime

    return pathlib.Path(max(matches, key=_rank))

def _is_num(v) -> bool:
    """Real number for scoring: int/float, not bool, finite (no NaN/Inf)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def get_z_scores(values: list) -> list[float]:
    """Compute z-scores for a list of values (ignoring None / non-numeric entries).

    Uses population standard deviation (pstdev): z-scoring a complete cohort
    (the full model list) treats the values as the population, matching
    compute_meanfill_composite and the aggregator's z-scores. Constant or
    single-value cohorts fall back to zero z-scores.
    """
    valid = [v for v in values if _is_num(v)]
    if len(valid) < 2:
        return [0.0] * len(values)
    mean_val = statistics.mean(valid)
    std_val = statistics.pstdev(valid) if len(valid) > 1 else 1.0
    if std_val == 0.0:
        std_val = 1.0
    return [(v - mean_val) / std_val if _is_num(v) else 0.0 for v in values]


def z_scores_none(values: list) -> list[float | None]:
    """Z-scores with None passthrough: missing stays None (never cohort-mean 0.0).

    Aggregator-canonical semantics for role-style weighted sums: callers skip
    None legs and renormalize over present signals. get_z_scores zero-fills
    (legacy ocheck/ccheck contract) — use this for any new weighted-sum path.
    """
    valid = [v for v in values if _is_num(v)]
    if len(valid) < 2:
        return [0.0 if _is_num(v) else None for v in values]
    mean_val = statistics.mean(valid)
    std_val = statistics.pstdev(valid) if len(valid) > 1 else 1.0
    if std_val == 0.0:
        std_val = 1.0
    return [(v - mean_val) / std_val if _is_num(v) else None for v in values]


def compute_capability_q(cz: float | None) -> float:
    """
    Compute Normalized Composite Capability Q ∈ [40.0, 99.9].
    Base centered at 78.0 with 8.5 standard deviation scale factor.
    """
    if not _is_num(cz):
        return 78.0
    return round(max(40.0, min(99.9, 78.0 + (float(cz) * 8.5))), 1)


def compute_p_success(q_score: float | None) -> float:
    """
    Compute task pass probability P_succ(Q) ∈ (0.0, 100.0)% on non-trivial agentic task.
    Sigmoid model centered at Q=72.0 with slope k=0.12, numerically clamped.
    """
    if not _is_num(q_score):
        return 0.0
    exponent = max(-50.0, min(50.0, -0.12 * (float(q_score) - 72.0)))
    p_succ = 1.0 / (1.0 + math.exp(exponent))
    return round(p_succ * 100.0, 1)


def compute_token_multiplier(p_success_pct: float | None, alpha: float = 1.2) -> float:
    """
    Compute Token Multiplier T_mult = (1 + α * (1 - P)) / P.
    Accounts for expected retry and debugging token burn on autonomous failures.
    """
    if not _is_num(p_success_pct) or not _is_num(alpha) or alpha <= 0:
        return 100.0
    if p_success_pct <= 0.0:
        return 100.0
    p_succ = max(0.02, min(1.0, float(p_success_pct) / 100.0))
    t_mult = (1.0 + alpha * (1.0 - p_succ)) / p_succ
    return round(t_mult, 2)


def compute_effective_cost(blended_price: float | None, token_multiplier: float | None) -> float | None:
    """Compute effective cost per verified completed task."""
    if not _is_num(blended_price) or not _is_num(token_multiplier):
        return None
    return round(float(blended_price) * float(token_multiplier), 2)


def compute_avi(q_score: float | None, effective_cost: float | None) -> float:
    """
    Agentic Value Index (AVI): Super-linear capability vs log effective cost ROI.
    Formula: Q^2.2 / (100 * log10(effective_cost + 1.5))

    Cost basis: effective $ per 1M tokens — bcheck feeds the 80/20 fresh-input
    blended price; ocheck/ccheck feed the cache-aware per-1M price of the model's
    own request mix so AVI agrees with their Eff c/r column. Free (0.0) and
    unknown costs are excluded by callers: the log10(+1.5) floor would otherwise
    pin every free model at ~Q^2.2/17.6 regardless of quality.
    """
    if not _is_num(q_score) or not _is_num(effective_cost):
        return 0.0
    return round((float(q_score) ** 2.2) / (100.0 * math.log10(max(0.0, float(effective_cost)) + 1.5)), 1)
def compute_fgi(q_score: float | None, p_success_pct: float | None) -> float:
    """
    Frontier Gate Index (FGI): High-difficulty architectural gating index.
    Formula: Q * (P_succ ^ 1.5)
    """
    if not _is_num(q_score) or not _is_num(p_success_pct):
        return 0.0
    p_succ = max(0.0, min(1.0, float(p_success_pct) / 100.0))
    return round(float(q_score) * (p_succ ** 1.5), 1)


def compute_bfi(q_score: float | None, speed_tps: float | None, blended_price: float | None) -> float:
    """
    Bulk Fill Index (BFI): Throughput and raw cost efficiency on bounded tasks.
    Formula: (Q * speed) / (100 * ((blended_price ^ 0.8) + 0.1))
    """
    if not _is_num(q_score) or not _is_num(speed_tps) or not _is_num(blended_price):
        return 0.0
    return round((float(q_score) * float(speed_tps)) / (100.0 * ((max(0.0, float(blended_price)) ** 0.8) + 0.1)), 1)


def compute_qvi(q_score: float | None, n_eff_tasks: float | None) -> float:
    """
    Quota Value Index (QVI): Total delivered utility under allowed plan quota headroom.
    Formula: log10(N_eff + 1) * (Q / 70.0)^2.4 * 100
    """
    if not _is_num(q_score) or not _is_num(n_eff_tasks) or n_eff_tasks <= 0:
        return 0.0
    quality_mult = (max(0.0, float(q_score)) / 70.0) ** 2.4
    task_log = math.log10(max(0.0, float(n_eff_tasks)) + 1.0)
    return round(task_log * quality_mult * 100.0, 1)


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

    Returns stable model IDs only (display/aa_slug/lm_slug/model_id/or_slug/id) —
    no truncated prefixes (display[:22]/[:20] collided on shared prefixes).
    """
    def _row_cost(a):
        # S2-M1: effective_cost 0.0 is a REAL cost (free tiers dominate the
        # frontier); only None falls through to the price sum, and only a
        # fully-unknown cost gets the 999 sentinel. Missing/None price parts
        # are skipped instead of TypeError-ing on None + float.
        c = a.get("effective_cost")
        if _is_num(c):
            return c
        parts = [p for p in (a.get("price_in"), a.get("price_out")) if _is_num(p)]
        return sum(parts) if parts else 999

    def _row_ids(a):
        ids = set()
        for key in ("display", "aa_slug", "lm_slug", "model_id", "or_slug", "id"):
            v = a.get(key)
            if v:
                ids.add(v)
        return ids

    costs = [_row_cost(a) for a in models_list]
    quals = [a.get("capability_q") if _is_num(a.get("capability_q")) else 0.0 for a in models_list]
    pareto_set = set()
    for i, a in enumerate(models_list):
        a_cost = costs[i]
        a_q = quals[i]
        candidates = [(costs[j], quals[j]) for j in range(len(models_list)) if j != i]
        if not pareto_dominated(a_cost, a_q, candidates, q_tolerance, cost_tolerance):
            pareto_set.update(_row_ids(a))
    return pareto_set


def compute_priced_pareto_frontier(models_list, q_tolerance=3.2, cost_tolerance=0.20):
    """Pareto frontier over PRICED rows only (effective_cost is not None).

    Unpriced high-Q rows enter compute_pareto_frontier via the 999 sentinel
    and render "—" in every cost cell — a "cheapest at quality X" claim on a
    row with no price is noise. Free (0.0) stays eligible: real free tiers
    dominate the frontier (S2-M1). Returns the same stable-ID set shape.
    """
    priced = [a for a in (models_list or []) if a.get("effective_cost") is not None]
    if not priced:
        return set()
    return compute_pareto_frontier(priced, q_tolerance=q_tolerance, cost_tolerance=cost_tolerance)


def _cohort_stats(vals: list[float]) -> tuple[float | None, float | None]:
    """Return (mean, pstdev) for a non-empty numeric cohort, else (None, None)."""
    if not vals:
        return None, None
    return statistics.fmean(vals), (statistics.pstdev(vals) if len(vals) > 1 else 0.0)


def _z_val(val: float | None, mean: float | None, std: float | None) -> float | None:
    """Single scalar z-score relative to cohort (None if missing, 0.0 if flat)."""
    if not _is_num(val) or mean is None or std is None:
        return None
    return (val - mean) / std if std > 0 else 0.0


def compute_meanfill_composite(rows):
    """
    Composite capability_q from the MEAN of whichever z-scored sources
    (AA intelligence, LMArena elo) are available per row, skipping missing
    sources rather than zero-filling them. Mutates row["composite"] and
    row["benchmarks"]["capability_q"] in place.
    """
    aa_vals = [r["benchmarks"]["aa_intelligence"] for r in rows if r["benchmarks"]["aa_intelligence"] is not None]
    lm_vals = [r["benchmarks"]["lmarena_elo"] for r in rows if r["benchmarks"]["lmarena_elo"] is not None]
    aa_mean, aa_std = _cohort_stats(aa_vals)
    lm_mean, lm_std = _cohort_stats(lm_vals)

    for r in rows:
        b = r["benchmarks"]
        zs = [z for z in (_z_val(b["aa_intelligence"], aa_mean, aa_std), _z_val(b["lmarena_elo"], lm_mean, lm_std)) if z is not None]
        comp_val = round(statistics.fmean(zs), 3) if zs else None
        r["composite"] = comp_val
        b["capability_q"] = compute_capability_q(comp_val) if _is_num(comp_val) else None
    return aa_vals, lm_vals, aa_mean, aa_std, lm_mean, lm_std


def comp_key(r):
    """Sort key: composite desc, then AA, then LMArena, then id. None composites last."""
    c = r.get("composite")
    k_c = -c if _is_num(c) else 1e9
    a = r["benchmarks"]["aa_intelligence"]
    k_a = -a if _is_num(a) else 1e9
    e = r["benchmarks"]["lmarena_elo"]
    k_e = -e if _is_num(e) else 1e9
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
    if s.endswith((":free", "-free")):
        s = s[:-5]
    return s


# ==============================================================================
# 4. LEADERBOARD PARSERS
# ==============================================================================
def _parse_livebench_cats(categories_json: str | dict | None) -> dict:
    """Decode LiveBench categories JSON/dict mapping safely."""
    if isinstance(categories_json, dict):
        return categories_json
    if isinstance(categories_json, str):
        with contextlib.suppress(Exception):
            parsed = json.loads(categories_json)
            if isinstance(parsed, dict):
                return parsed
    return {}


def _parse_livebench_row(row: dict, cats: dict) -> tuple[str, dict] | None:
    """Extract normalized LiveBench record from a single CSV row."""
    model = row.get("model")
    if not model:
        return None
    all_scores = [
        fv for col, val in row.items()
        if col != "model" and not col.startswith(("nq_", "out_"))
        if (fv := _safe_float(val)) is not None
    ]
    overall = sum(all_scores) / len(all_scores) if all_scores else None
    cat_scores = {}
    for cat_name, tasks in cats.items():
        t_scores = [s for s in (_safe_float(row.get(t)) for t in tasks) if s is not None]
        if t_scores:
            cat_scores[cat_name] = round(sum(t_scores) / len(t_scores), 2)
    return norm_id(model), {
        "model": model,
        "overall": round(overall, 2) if overall is not None else None,
        "coding": _first_num(cat_scores.get("Coding"), cat_scores.get("coding"), row.get("coding")),
        "agentic_coding": _first_num(cat_scores.get("Agentic Coding"), cat_scores.get("agentic_coding")),
        "reasoning": _first_num(cat_scores.get("Reasoning"), cat_scores.get("reasoning"), row.get("reasoning")),
        "math": _first_num(cat_scores.get("Mathematics"), cat_scores.get("math"), row.get("math")),
        "data_analysis": _first_num(cat_scores.get("Data Analysis"), cat_scores.get("data_analysis")),
        "language": _first_num(cat_scores.get("Language"), cat_scores.get("language")),
        "instruction_following": _first_num(cat_scores.get("IF"), cat_scores.get("instruction_following")),
        "categories": cat_scores,
    }


def parse_livebench(csv_text: str, categories_json: str | dict | None = None, verbose: bool = False) -> dict:
    """
    Parse LiveBench leaderboard CSV (https://livebench.ai).
    Extracts decontaminated scores across Reasoning, Coding, Agentic Coding, Math, Data Analysis, and IF.
    """
    cats = _parse_livebench_cats(categories_json)
    out = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        parsed = _parse_livebench_row(row, cats)
        if parsed:
            slug, rec = parsed
            out[slug] = rec
    if verbose:
        print(f"  LiveBench: parsed {len(out)} entries")
    return out


def _lmarena_rsc_entry(e: dict) -> tuple[str, dict] | None:
    """Convert one LMArena Next.js RSC entry dict to (slug, record)."""
    if not isinstance(e, dict):
        return None
    name = e.get("modelDisplayName") or e.get("modelKey")
    if not name:
        return None
    elo = _safe_float(e.get("rating"))
    elo = round(elo, 0) if elo is not None else None
    p_in = e.get("inputPricePerMillion")
    p_out = e.get("outputPricePerMillion")
    ctx = _safe_int(e.get("contextLength"))
    return name.strip().lower(), {
        "rank": _safe_int(e.get("rank")),
        "elo": elo,
        "votes": _safe_int(e.get("votes")),
        "price_raw": f"${p_in} / ${p_out}" if p_in is not None else "",
        "context_raw": f"{ctx // 1000}k" if ctx else "",
        "score_raw": str(int(elo)) if elo else "",
    }


def _parse_lmarena_rsc(html_text: str) -> dict:
    """Extract LMArena entries from Next.js App Router streamed JSON payloads."""
    out = {}
    unescaped = html_text.replace('\\"', '"').replace("\\/", "/")
    decoder = json.JSONDecoder()
    pos = 0
    while (idx := unescaped.find('"entries":[{', pos)) != -1:
        arr_start = idx + len('"entries":')
        try:
            entries, offset = decoder.raw_decode(unescaped[arr_start:])
        except Exception:
            pos = arr_start + 1
            continue
        pos = arr_start + offset
        if not isinstance(entries, list):
            continue
        for e in entries:
            parsed = _lmarena_rsc_entry(e)
            if parsed and parsed[0] not in out:
                out[parsed[0]] = parsed[1]
    return out


def _has_ver_token(tok: str) -> bool:
    """True when slug token carries a version dash/dot and digit."""
    return ("-" in tok or "." in tok) and any(c.isdigit() for c in tok)


def _extract_tr_slug(cell_html: str, tr_html: str) -> str:
    """Extract lowercase slug from a legacy LMArena HTML table row cell."""
    if m := (re.search(r'title="([^"]+)"', cell_html) or re.search(r'title="([^"]+)"', tr_html)):
        return m.group(1).strip().lower()
    if href_m := re.search(r'href="[^"]*?/([^"/\?]+)', cell_html):
        slug = href_m.group(1).lower().strip()
        if "." in slug or "-" in slug:
            return slug
    tokens = re.findall(r"[a-z0-9][a-z0-9\.\-]*", re.sub(r"<[^>]+>", " ", cell_html).lower())
    return next((t for t in reversed(tokens) if _has_ver_token(t)), tokens[-1] if tokens else "")


def _parse_lmarena_legacy_tr(html_text: str, verbose: bool = False) -> dict:
    """Fallback HTML <tr> parser for pre-RSC LMArena snapshots."""
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.S)
    if verbose:
        print(f"  LMArena: found {len(trs)} tr rows")
    out = {}
    for tr in trs[1:]:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(cells) < 7:
            continue
        slug = _extract_tr_slug(cells[2], tr)
        if not slug:
            continue
        score_raw = re.sub(r"<[^>]+>", "", cells[3]).strip()
        elo = re.split(r"[±+]", score_raw)[0].strip()
        votes_raw = re.sub(r"<[^>]+>", "", cells[4]).strip().replace(",", "")
        out[slug] = {
            "rank": _safe_int(re.sub(r"<[^>]+>", "", cells[0]).strip()),
            "elo": _safe_float(elo),
            "votes": _safe_int(votes_raw),
            "price_raw": re.sub(r"<[^>]+>", " ", cells[5]).strip(),
            "context_raw": re.sub(r"<[^>]+>", "", cells[6]).strip(),
            "score_raw": score_raw,
        }
    return out


def parse_lmarena(html_text: str, verbose: bool = False) -> dict:
    """
    Parse Arena.ai / LMSYS Arena HTML leaderboard.
    Supports Next.js App Router RSC streamed JSON arrays ('"entries":[{...}]')
    with automatic fallback to static HTML table parsing.
    """
    if not html_text or not isinstance(html_text, str):
        return {}
    out = _parse_lmarena_rsc(html_text) or _parse_lmarena_legacy_tr(html_text, verbose=verbose)
    if verbose:
        print(f"  LMArena: parsed {len(out)} entries")
    return out


# Arena's own leaderboard dataset (cc-by-4.0). arena.ai serves 403 to scrapers,
# so this is the fetch path; parse_lmarena's HTML reader stays for legacy
# snapshots only.
LMARENA_HF_DATASET = "lmarena-ai/leaderboard-dataset"
LMARENA_HF_ROWS_API = "https://datasets-server.huggingface.co/rows"
LMARENA_HF_CONFIG = "webdev"
LMARENA_HF_ELO_CATEGORY = "webdev"        # same board the retired HTML scrape read
LMARENA_HF_CODING_CATEGORY = "webdev-react"  # second Arena coding board → lm_coding leg


def _index_hf_rows(row_list: list) -> dict[str, dict]:
    """Index HF Arena rows by lowercase model_name, keeping highest rating on duplicates."""
    by_slug: dict[str, dict] = {}
    for r in row_list:
        key = (r.get("model_name") or "").strip().lower()
        if not key:
            continue
        cur = _safe_float(r.get("rating"))
        prev = _safe_float(by_slug[key].get("rating")) if key in by_slug else None
        if prev is None or (cur is not None and cur > prev):
            by_slug[key] = r
    return by_slug


def _hf_record(r: dict, c: dict | None) -> dict:
    """Assemble normalized LMArena record from HF primary and coding rows."""
    elo = _safe_float(r.get("rating"))
    elo = round(elo, 0) if elo is not None else None
    c_elo = _safe_float(c.get("rating")) if c else None
    return {
        "rank": _safe_int(r.get("rank")),
        "elo": elo,
        "votes": _safe_int(r.get("vote_count")),
        "coding": round(c_elo, 0) if c_elo is not None else None,
        "coding_rank": _safe_int(c.get("rank")) if c else None,
        "price_raw": "",
        "context_raw": "",
        "score_raw": str(int(elo)) if elo is not None else "",
        "org": r.get("organization"),
        "publish_date": r.get("leaderboard_publish_date"),
    }


def _unwrap_hf_rows(payload) -> dict[str | None, list]:
    """Extract HF rows grouped by category."""
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {}
    by_cat: dict[str | None, list] = {}
    for item in rows:
        r = item.get("row", item) if isinstance(item, dict) else None
        if isinstance(r, dict):
            by_cat.setdefault(r.get("category"), []).append(r)
    return by_cat


def parse_lmarena_hf(payload, verbose: bool = False) -> dict:
    """Build the same map as parse_lmarena from the Arena leaderboard dataset."""
    by_cat = _unwrap_hf_rows(payload)
    primary = _index_hf_rows(by_cat.get(LMARENA_HF_ELO_CATEGORY) or by_cat.get("overall") or [])
    coding = _index_hf_rows(by_cat.get(LMARENA_HF_CODING_CATEGORY) or by_cat.get("webdev-html") or [])
    out = {slug: _hf_record(r, coding.get(slug)) for slug, r in primary.items()}
    if verbose:
        n_cod = sum(1 for v in out.values() if v["coding"] is not None)
        print(f"  LMArena HF: parsed {len(out)} models ({n_cod} with coding Elo)")
    return out


def _fetch_url_retry(url: str, timeout: int = 30, retries: int = 3) -> str | None:
    """Fetch URL with linear backoff retries."""
    for attempt in range(retries):
        txt = fetch_url(url, timeout=timeout)
        if txt:
            return txt
        time.sleep(2 * (attempt + 1))
    return None


def fetch_lmarena_hf_rows(config: str = LMARENA_HF_CONFIG, timeout: int = 30, per_page: int = 100) -> list:
    """Page the HF datasets-server rows API for one Arena config."""
    rows, offset, total = [], 0, None
    while total is None or offset < total:
        q = urllib.parse.urlencode({
            "dataset": LMARENA_HF_DATASET, "config": config, "split": "latest",
            "offset": offset, "length": per_page,
        })
        txt = _fetch_url_retry(f"{LMARENA_HF_ROWS_API}?{q}", timeout=timeout)
        if not txt:
            return []
        try:
            page = json.loads(txt)
        except ValueError:
            return []
        total = page.get("num_rows_total", 0)
        batch = [x.get("row", x) for x in page.get("rows", [])]
        if not batch:
            break
        rows.extend(batch)
        offset += per_page
    cats = {r.get("category") for r in rows}
    if LMARENA_HF_ELO_CATEGORY not in cats or LMARENA_HF_CODING_CATEGORY not in cats:
        return []
    return rows


def load_lmarena_map(raw_dir, verbose: bool = False) -> dict:
    """Offline Arena map: newest HF dataset snapshot, else newest legacy HTML."""
    raw = pathlib.Path(raw_dir)
    hf = sorted(glob.glob(str(raw / "*lmarena_hf*20*.json")))
    if hf:
        try:
            payload = json.loads(pathlib.Path(hf[-1]).read_text(encoding="utf-8"))
            m = parse_lmarena_hf(payload, verbose=verbose)
            if m:
                return m
        except Exception as exc:
            if verbose:
                print(f"  WARN LMArena HF cache read failed ({hf[-1]}): {exc}", file=sys.stderr)
    html = sorted(glob.glob(str(raw / "*lmarena*20*.html")))
    if not html:
        return {}
    try:
        return parse_lmarena(pathlib.Path(html[-1]).read_text(encoding="utf-8", errors="ignore"), verbose=verbose)
    except Exception as exc:
        if verbose:
            print(f"  WARN LMArena HTML cache read failed ({html[-1]}): {exc}", file=sys.stderr)
        return {}


def _read_cached_hf_snapshot(path: pathlib.Path, verbose: bool = False) -> dict | None:
    """Read cached HF Arena JSON snapshot if readable and non-empty."""
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(cached, dict) and cached.get("rows"):
            return cached
    except Exception as exc:
        if verbose:
            print(f"  WARN cached LMArena HF unreadable ({path}): {exc}", file=sys.stderr)
    return None


def fetch_lmarena_hf_snapshot(
    raw_dir,
    verbose: bool = False,
    do_write: bool = True,
    force: bool = False,
) -> dict | None:
    """Fetch the Arena HF board and persist it as `lmarena_hf_YYYYMMDD.json` (UTC date)."""
    raw = pathlib.Path(raw_dir)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    path = raw / f"lmarena_hf_{stamp}.json"
    if not force and path.exists():
        cached = _read_cached_hf_snapshot(path, verbose=verbose)
        if cached:
            return cached
    rows = fetch_lmarena_hf_rows()
    if not rows:
        return None
    payload = {"rows": rows}
    if do_write and (force or not path.exists()):
        try:
            atomic_write_text(path, json.dumps(payload, indent=1))
            if verbose:
                print(f"  saved LMArena HF -> {path} ({len(rows)} rows)")
        except Exception as exc:
            print(f"  WARN failed to save LMArena HF snapshot ({path}): {exc}", file=sys.stderr)
    return payload


def _extract_aa_array(unescaped: str, decoder: json.JSONDecoder) -> list:
    """Find and decode the largest score-bearing models array from AA Next.js payload."""
    best: list = []
    for key_name in ("models", "initialModels"):
        key = f'"{key_name}":['
        pos = 0
        while (idx := unescaped.find(key, pos)) != -1:
            arr_start = idx + len(key) - 1
            pos = arr_start + 1
            try:
                parsed, offset = decoder.raw_decode(unescaped[arr_start:])
            except Exception:
                continue
            pos = arr_start + offset
            if isinstance(parsed, list) and len(parsed) > len(best) and any(
                isinstance(m, dict) and "intelligenceIndex" in m for m in parsed
            ):
                best = parsed
    return best


def _aa_variant_suffix(m: dict) -> str:
    label = str(m.get("shortName") or m.get("name") or "")
    par = re.search(r"\(([^)]+)\)\s*$", label)
    return re.sub(r"[^a-z0-9]+", "-", par.group(1).lower()).strip("-") if par else ""


def _aa_slugs(m: dict) -> tuple[str, str] | None:
    """Derive (variant_slug, release_slug) across AA v4 top-level slug and v5 release.slug."""
    rel = m.get("release")
    rslug = str(rel.get("slug") or "") if isinstance(rel, dict) else ""
    top_slug = str(m.get("slug") or "")
    if top_slug:
        return top_slug, (rslug or top_slug)
    if not rslug:
        return None
    tok = _aa_variant_suffix(m)
    return (f"{rslug}-{tok}" if tok and not rslug.endswith(f"-{tok}") else rslug), rslug


def _aa_pct(scores: dict, *keys: str, fallback=None) -> float | None:
    """Read AA sub-benchmark score, normalizing [0, 1] ratios to 0..100 percentages."""
    for k in keys:
        v = _safe_float(scores.get(k))
        if v is not None:
            return round(v * 100.0, 2) if 0.0 <= v <= 1.0 else round(v, 2)
    return _safe_float(fallback)


_AA_SCORE_SPECS: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    ("terminalbench4", ("terminalbench-4-0",), None),
    ("terminalbenchHard", ("terminalbench-hard",), "terminalbenchHard"),
    ("frontiercode2", ("frontiercode-2-0", "frontiercode"), None),
    ("livecodebench", ("livecodebench",), None),
    ("itbenchSre", ("itbench-aa",), "itbenchSre"),
    ("tau2", ("tau2-bench",), "tau2"),
    ("automationbench", ("automationbench-aa",), None),
    ("ifbench", ("ifbench",), "ifbench"),
    ("gpqa", ("gpqa-diamond",), "gpqa"),
    ("hle", ("hle-diamond", "humanitys-last-exam"), "hle"),
    ("critptHard", ("critpt-v2-hard", "critpt"), None),
    ("scicode", ("scicode",), "scicode"),
    ("longContextReasoning", ("artificial-analysis-long-context-reasoning",), None),
    ("omniscienceAccuracy", ("omniscience-accuracy",), "omniscienceAccuracy"),
    ("omniscienceNonHallucination", ("omniscience-non-hallucination",), None),
)


def _aa_record(m: dict) -> tuple[dict, str] | None:
    """Convert raw AA model object (v4 or v5.0.1) to (canonical_dict, release_slug)."""
    slugs = _aa_slugs(m)
    if not slugs:
        return None
    vslug, rslug = slugs
    raw_sc = m.get("scores")
    sc = raw_sc if isinstance(raw_sc, dict) else {}
    tps = _first_num(m.get("outputSpeed"), m.get("medianOutputTokensPerSecond"))
    rec = {
        "slug": vslug, "release_slug": rslug, "name": m.get("name") or m.get("shortName") or vslug,
        "intelligenceIndex": _safe_float(m.get("intelligenceIndex")),
        "codingIndex": _safe_float(m.get("codingIndex")), "agenticIndex": _safe_float(m.get("agenticIndex")),
        "medianTps": tps, "medianOutputTokensPerSecond": tps,
        "ttft": _first_num(m.get("timeToFirstAnswerToken"), m.get("timeToFirstToken")),
        "costPerTask": _safe_float(m.get("intelligenceIndexCostPerTask")),
        "contextWindowTokens": _safe_int(m.get("contextWindowTokens")),
        "price_in": _safe_float(m.get("price1mInputTokens")), "price_out": _safe_float(m.get("price1mOutputTokens")),
        **{dst: _aa_pct(sc, *src_keys, fallback=m.get(fb) if fb else None) for dst, src_keys, fb in _AA_SCORE_SPECS},
    }
    return rec, rslug


def _aa_rank_key(rec: dict) -> tuple[bool, float]:
    val = rec.get("intelligenceIndex")
    return (val is not None, float(val) if val is not None else -1e9)


def parse_aa(html_text: str, verbose: bool = False) -> dict:
    """Parse Artificial Analysis leaderboard from its Next.js App Router RSC payload."""
    unescaped = html_text.replace('\\"', '"').replace("\\/", "/")
    models = _extract_aa_array(unescaped, json.JSONDecoder())
    if not models:
        if verbose:
            print("  Artificial Analysis: no intelligenceIndex array found", file=sys.stderr)
        return {}
    out: dict[str, dict] = {}
    for m in models:
        if not isinstance(m, dict):
            continue
        item = _aa_record(m)
        if not item:
            continue
        rec, rslug = item
        out[rec["slug"]] = rec
        if rslug not in out or _aa_rank_key(rec) > _aa_rank_key(out[rslug]):
            out[rslug] = rec
    if verbose:
        print(f"  Artificial Analysis: parsed {len(out)} model keys")
    return out


def _openrouter_record(rec: dict) -> dict | None:
    """Normalize one OpenRouter model entry."""
    oid = rec.get("id", "")
    if not oid:
        return None
    pricing = rec.get("pricing", {}) or {}
    p_prompt = _safe_float(pricing.get("prompt"))
    p_comp = _safe_float(pricing.get("completion"))
    ctx = _safe_int(rec.get("context_length"))
    return {
        "id": oid,
        "name": rec.get("name") or oid,
        "description": rec.get("description"),
        "context": ctx,
        "context_length": ctx,
        "pricing": pricing,
        "architecture": rec.get("architecture") or {},
        "prompt_price_1m": (p_prompt * 1_000_000.0) if p_prompt is not None else None,
        "completion_price_1m": (p_comp * 1_000_000.0) if p_comp is not None else None,
        "is_free": oid.endswith(":free") or (p_prompt == 0.0 and p_comp == 0.0),
        "is_stealth": oid.startswith("stealth/"),
        "created": rec.get("created"),
    }


def parse_openrouter(data_json: str | dict, verbose: bool = False) -> dict:
    """Parse OpenRouter /api/v1/models JSON payload."""
    data = data_json
    if isinstance(data_json, str):
        try:
            data = json.loads(data_json)
        except Exception as e:
            if verbose:
                print(f"  WARN OpenRouter JSON parse error: {e}", file=sys.stderr)
            return {}
    items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    out = {}
    for rec in items:
        parsed = _openrouter_record(rec)
        if parsed:
            out[parsed["id"]] = parsed
    if verbose:
        print(f"  OpenRouter: parsed {len(out)} models")
    return out


def _is_devalue_tag(x) -> bool:
    """True when `x` looks like an Astro devalue `[tag, value]` tuple."""
    return isinstance(x, list) and len(x) == 2 and type(x[0]) is int and 0 <= x[0] <= 11


def _unwrap_devalue_tag(tag: int, val):
    """Decode a single tagged Astro devalue container."""
    if tag == 0 and isinstance(val, dict):
        return {k: unwrap_astro_devalue(v) for k, v in val.items()}
    if tag == 1 and isinstance(val, list):
        return [unwrap_astro_devalue(item) for item in val]
    return val


def unwrap_astro_devalue(x):
    """Recursively decode Astro island serialized devalue structures ([tag, payload])."""
    if _is_devalue_tag(x):
        return _unwrap_devalue_tag(x[0], x[1])
    if isinstance(x, dict):
        return {k: unwrap_astro_devalue(v) for k, v in x.items()}
    return [unwrap_astro_devalue(item) for item in x] if isinstance(x, list) else x


_VALS_TASK_FIELDS = {
    "vals_coding": "vibe_code_bench",
    "vals_terminal": "terminal_bench_4",
    "vals_emb": "emb",
    "vals_finance": "finance_agent",
    "vals_legal": "legal_research",
    "vals_hlab": "legal_agent_benchmark",
    "vals_tax": "tax_agent_bench",
    "vals_migration": "code_migration",
}


def _vals_record(model_slug: str, stats: dict, tasks: dict) -> dict:
    """Build normalized Vals Index record across all task legs for one model."""
    bare_slug = model_slug.split("/", 1)[-1]
    norm_bare = norm_model_slug(bare_slug)
    rec = {
        "model_slug": model_slug,
        "bare_slug": bare_slug,
        "norm_slug": norm_bare,
        "vals_overall": _safe_float(stats.get("accuracy")),
        "vals_cost_per_test": _safe_float(stats.get("cost_per_test")),
        "vals_latency": _safe_float(stats.get("latency")),
    }
    for field, task_key in _VALS_TASK_FIELDS.items():
        rec[field] = _safe_float((tasks.get(task_key) or {}).get(model_slug, {}).get("accuracy"))
    code_terms = [v for v in (rec["vals_coding"], rec["vals_terminal"]) if v is not None]
    rec["vals_coding_blend"] = (sum(code_terms) / len(code_terms)) if code_terms else None
    return rec


def _extract_vals_props(html_text: str, verbose: bool) -> dict | None:
    """Locate and decode the Vals Index Astro island JSON payload."""
    for comp in ("ValsIndexHeatmap", "ValsIndexBarGraph", "ScatterGraph"):
        m = re.search(rf'<astro-island[^>]+component-url="[^"]*{comp}[^"]*"[^>]*props="([^"]+)"', html_text)
        if not m:
            continue
        try:
            return unwrap_astro_devalue(json.loads(html_lib.unescape(m.group(1))))
        except Exception as e:
            if verbose:
                print(f"  WARN Vals Index JSON/devalue decode error: {e}", file=sys.stderr)
            return None
    if verbose:
        print("  WARN Vals Index: no Astro island props found", file=sys.stderr)
    return None


def _collect_vals_models(overall: dict, tasks: dict) -> dict:
    """Build slug-indexed Vals Index dictionary for all rows in `overall`."""
    out: dict[str, dict] = {}
    for model_slug, stats in overall.items():
        if not isinstance(stats, dict):
            continue
        rec = _vals_record(model_slug, stats, tasks)
        out[model_slug] = rec
        if rec["norm_slug"] and rec["norm_slug"] not in out:
            out[rec["norm_slug"]] = rec
    return out


def parse_vals_index(html_text: str, verbose: bool = False) -> dict:
    """Parse Vals Index Astro island SSR props (ValsIndexHeatmap / ValsIndexBarGraph / ScatterGraph)."""
    if not html_text or not (data := _extract_vals_props(html_text, verbose)):
        return {}
    tasks = (data.get("benchmarkView") or {}).get("tasks") or {}
    overall = tasks.get("overall") or {}
    if not overall:
        return {}
    out = _collect_vals_models(overall, tasks)
    if verbose:
        print(f"  Vals Index: parsed {len(overall)} models across {len(tasks)} tasks")
    return out


# Canonical API / Scrape Endpoints
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
LMARENA_URL = "https://arena.ai/leaderboard/code/webdev"
VALS_INDEX_URL = "https://www.vals.ai/benchmarks/vals_index"
OPENROUTER_API = "https://openrouter.ai/api/v1/models"
OPENCODE_ZEN_API = "https://opencode.ai/zen/v1/models"
OPENCODE_GO_API = "https://opencode.ai/zen/go/v1/models"
CLINE_RECOMMENDED_MODELS_API = "https://api.cline.bot/api/v1/ai/cline/recommended-models"
OCGO_DOCS = "https://opencode.ai/v2/docs/console/go/"


def _vals_candidate_names(model_entry: dict | str) -> list[str]:
    """Collect ordered candidate identifier strings for Vals Index lookup."""
    if not isinstance(model_entry, dict):
        return [str(model_entry)]
    names = [v for k in ("model_id", "display", "or_slug", "aa_slug", "lm_slug") if (v := model_entry.get(k))]
    for key in ("live_aliases", "lm_aliases", "aa_aliases"):
        names.extend(a for a in model_entry.get(key, ()) if a)
    return names


def find_vals_for_model(model_entry: dict | str, vals_map: dict) -> dict | None:
    """Find matching Vals Index record for a model catalog entry or identifier."""
    if not vals_map or not model_entry:
        return None
    for name in _vals_candidate_names(model_entry):
        for cand in (name, name.replace(" ", "-"), name.replace("_", "-")):
            sn = norm_model_slug(cand)
            if sn in vals_map:
                return vals_map[sn]
            st = strip_tier_tokens(sn)
            if st in vals_map:
                return vals_map[st]
    return None


def _pick_best_score(records: list[dict], score_key: str) -> dict | None:
    """Pick highest-scoring record by `score_key`."""
    return max(records, key=lambda r: float(r.get(score_key) or 0.0)) if records else None


def _find_best_ranked(
    model_id: str,
    record_map: dict,
    score_key: str,
    extra_rungs: tuple = (),
) -> dict | None:
    """Shared ranked lookup across AA, Arena, and LiveBench maps.

    Rungs: exact slug -> symmetric tier-stripped slug -> caller extra rungs ->
    guarded non-conflicting fallback picking highest `score_key`.
    """
    if not record_map or not model_id:
        return None
    sn = norm_model_slug(model_id)
    if not sn:
        return None
    ssn = strip_tier_tokens(model_id)
    scored = [(slug, rec) for slug, rec in record_map.items() if rec.get(score_key) is not None]

    for pred in (
        lambda slug: norm_model_slug(slug) == sn,
        lambda slug: bool(ssn) and strip_tier_tokens(slug) == ssn,
        *extra_rungs,
        lambda slug: not variant_conflict(sn, norm_model_slug(slug)),
    ):
        if hits := [rec for slug, rec in scored if pred(slug)]:
            return _pick_best_score(hits, score_key)
    return None


def find_aa_for_model(model_id: str, aa_map: dict) -> dict | None:
    """Find best Artificial Analysis record for a model ID."""
    return _find_best_ranked(model_id, aa_map, "intelligenceIndex")


def find_lm_for_model(model_id: str, lm_map: dict) -> dict | None:
    """Find best LMArena record for a model ID (with parenthetical + token-bag rungs)."""
    base = arena_base_key(model_id or "")
    tkey = arena_token_key(model_id or "")
    rungs = []
    if base:
        rungs.append(lambda slug: arena_base_key(slug) == base)
    if tkey:
        rungs.append(lambda slug: arena_token_key(slug) == tkey)
    return _find_best_ranked(model_id, lm_map, "elo", extra_rungs=tuple(rungs))


def find_or_for_model(model_id: str, or_map: dict) -> tuple[str | None, dict | None]:
    """Find best OpenRouter record for a model ID with variant conflict safety."""
    if not or_map or not model_id:
        return None, None
    sn = norm_model_slug(model_id)
    if not sn:
        return None, None
    for oid, rec in or_map.items():
        suffix = oid.split("/")[-1]
        if norm_model_slug(suffix) == sn or norm_model_slug(oid) == sn:
            return oid, rec
    for oid, rec in or_map.items():
        suffix = oid.split("/")[-1]
        if not variant_conflict(sn, norm_model_slug(suffix)) or not variant_conflict(sn, norm_model_slug(oid)):
            return oid, rec
    return None, None


def find_livebench_for_model(model_id: str, live_map: dict) -> dict | None:
    """Find best LiveBench record for a model ID."""
    return _find_best_ranked(model_id, live_map, "overall")


# ==============================================================================
# 5. CLI & ANSI DISPLAY FORMATTING UTILITIES
# ==============================================================================
def display_len(text: str) -> int:
    """Return true visible terminal width: strips ANSI escapes, counts wide/emoji glyphs as 2 columns."""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", str(text))
    w = 0
    for ch in clean:
        code = ord(ch)
        if code in (0xFE0F, 0x200D, 0x200B):  # Variation selector, ZWJ, zero-width space
            continue
        if (
            unicodedata.east_asian_width(ch) in ("W", "F")
            or (0x1F300 <= code <= 0x1FAFF)
            or code in (0x1F947, 0x1F948, 0x1F949, 0x1F3C6, 0x26A1, 0x2B50)
        ):
            w += 2
        else:
            w += 1
    return w


_ANSI_TOKEN_RE = re.compile(r"\x1b\[[0-9;]*m")


def _truncate_display(text: str, width: int) -> str:
    """Truncate text to <= `width` display columns while preserving ANSI SGR escapes."""
    out: list[str] = []
    cur_w, pos, has_ansi = 0, 0, False
    for m in _ANSI_TOKEN_RE.finditer(text):
        for ch in text[pos:m.start()]:
            cw = display_len(ch)
            if cur_w + cw > width:
                res = "".join(out) + (" " * max(0, width - cur_w))
                return (res + C_RESET) if has_ansi else res
            out.append(ch)
            cur_w += cw
        out.append(m.group(0))
        has_ansi = True
        pos = m.end()
    for ch in text[pos:]:
        cw = display_len(ch)
        if cur_w + cw > width:
            break
        out.append(ch)
        cur_w += cw
    res = "".join(out) + (" " * max(0, width - cur_w))
    return (res + C_RESET) if has_ansi else res


def pad_display(text: str, width: int, align: str = "<") -> str:
    """Pad string to exact display width using display_len, ANSI- and wide-glyph-safe."""
    s = str(text)
    dlen = display_len(s)
    if dlen > width:
        return _truncate_display(s, width)
    pad_needed = max(0, width - dlen)
    if align == ">":
        return (" " * pad_needed) + s
    if align == "^":
        left_pad = pad_needed // 2
        return (" " * left_pad) + s + (" " * (pad_needed - left_pad))
    return s + (" " * pad_needed)


def color_cell(text, color: str = "", width: int | None = None, align: str = "<", bg: str = "") -> str:
    """Format and align text cell with background/foreground color and exact padding."""
    padded = pad_display(str(text), width, align) if width is not None else str(text)
    return f"{bg}{color} {padded} {C_RESET}"





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
    """Return color for Agentic Value Index (AVI). Bands follow the merged
    ~50-1050 output range across tools (bcheck blended $/M basis; ocheck/ccheck
    cache-aware mix $/M basis — 2026-09 quantiles: p20~200 p40~290 p60~370 p80~540)."""
    if avi_val is None:
        return C_DIM
    if avi_val >= 540.0:
        return C_BOLD + C_GREEN
    if avi_val >= 370.0:
        return C_GREEN
    if avi_val >= 290.0:
        return C_CYAN
    if avi_val >= 200.0:
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


def score_color_qvi(qvi_val: float | None) -> str:
    """Return color for Quota Value Index (QVI)."""
    if qvi_val is None:
        return C_DIM
    if qvi_val >= 500.0:
        return C_BOLD + C_GREEN
    if qvi_val >= 350.0:
        return C_GREEN
    if qvi_val >= 200.0:
        return C_CYAN
    if qvi_val >= 100.0:
        return C_YELLOW
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
    """Shared rounded-box (color) / `=`-rule (plain) banner atop CLI tables."""
    box_color = box_color or C_CYAN
    out = []
    if color:
        out.append(f"{box_color}╭{'─' * inner_w}╮{C_RESET}")
        out.append(f"{box_color}│{C_RESET} {C_BOLD}{C_WHITE}{pad_display(title, inner_w - 2)}{C_RESET} {box_color}│{C_RESET}")
        for line in (summary_lines or []):
            out.append(f"{box_color}│{C_RESET}{C_DIM} {pad_display(line, inner_w - 2)} {C_RESET}{box_color}│{C_RESET}")
        if diff_notices:
            diff_line = " │ ".join(diff_notices)
            out.append(f"{box_color}│{C_RESET} {pad_display(diff_line, inner_w - 2)} {C_RESET}{box_color}│{C_RESET}")
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


_POOL_STYLE = {
    "claude": ("CLD", C_CLAUDE), "cld": ("CLD", C_CLAUDE),
    "agy": ("AGY", C_AGY), "gemini": ("AGY", C_AGY), "google": ("AGY", C_AGY),
    "ocgo": ("OCG", C_OCGO), "opencode": ("OCG", C_OCGO), "oc": ("OC", C_OCGO),
    "frontier": ("FRT", C_FRONTIER), "frt": ("FRT", C_FRONTIER),
    "openrouter": ("OR", C_OPENROUTER), "or": ("OR", C_OPENROUTER),
    "cline": ("CLN", C_CLINE), "cln": ("CLN", C_CLINE),
    "api": ("API", C_CYAN), "upstream": ("API", C_CYAN), "ext": ("API", C_CYAN),
    "hetzner": ("HTZ", C_HETZNER), "htz": ("HTZ", C_HETZNER),
    "nvidia": ("NVD", C_NVIDIA), "nvd": ("NVD", C_NVIDIA),
    "stealth": ("STL", C_MAGENTA), "stl": ("STL", C_MAGENTA),
}


def pool_badge(pool: str, color: bool = True) -> str:
    """Return colored pool tag badge (e.g. [CLD], [AGY], [OCG], [FRT], [OR], [STL])."""
    p = pool.lower().strip()
    tag, col = _POOL_STYLE.get(p, (pool.upper()[:3], C_WHITE))
    return f"{C_BOLD}{col}[{tag}]{C_RESET}" if color else f"[{tag}]"


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
.badge-htz { background: rgba(213,12,45,0.15); color: #ef4444; }
.badge-nvd { background: rgba(118,185,0,0.18); color: #76b900; }
.badge-stl { background: rgba(244,63,94,0.18); color: #f43f5e; border: 1px solid #f43f5e; }
tr.added { background: rgba(63, 185, 80, 0.08) !important; }
tr.added td.m, tr.added td:first-child { color: #3fb950 !important; font-weight: 700; }
tr.top-row { background: rgba(210,153,34,0.08); font-weight: 600; }
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
def _role_pool_label(m: dict, name: str, context: str) -> str:
    """Format pool/limit badge for role recommendations by checker context."""
    pricing = m.get("pricing") or {}
    if context in ("ccheck", "ocheck"):
        limit = pricing.get("monthly_credits") if context == "ccheck" else None
        if limit is None:
            limit = pricing.get("monthly_usage_limit_usd")
        if limit is not None:
            return f"${limit:.0f}/m"
        mid = m.get("model_id", "").lower()
        return "Free" if ("free" in mid or "free" in name.lower()) else "—"
    return pool_badge(m.get("pool") or "api", color=False)


def _extract_model_role_features(m: dict, context: str = "bcheck") -> dict:
    """Standardize model metrics into homogeneous source legs for role scoring."""
    raw_name = m.get("display") or m.get("model_id") or "Unknown"
    name = clean_display_name(raw_name)
    val, bms, bm = m.get("value") or {}, m.get("benchmarks") or {}, m.get("base_metrics") or {}

    eff_cost = _first_num(
        m.get("empirical_cost"), m.get("effective_cost"),
        val.get("effective_cost_per_request"), m.get("cost_per_request_usd"),
    )
    if eff_cost == 0.0:
        eff_cost = 0.0001

    return {
        "raw": m,
        "name": name,
        "pool_str": _role_pool_label(m, name, context),
        "q": _first_num(m.get("capability_q"), bms.get("capability_q"), m.get("composite_score")),
        "roles": m.get("roles") if isinstance(m.get("roles"), dict) else None,
        "eff_cost": eff_cost,
        "ctx": _first_num(m.get("context_length"), bms.get("openrouter_context"), bms.get("aa_context")),
        "vals_coding": _first_num(m.get("vals_coding_blend"), m.get("vals_coding")),
        "aa_coding": _first_num(bm.get("aa_tb4"), bm.get("aa_coding"), bms.get("aa_coding"), m.get("aa_live_coding")),
        "lm_coding": _first_num(bm.get("lm_coding"), bms.get("lmarena_coding")),
        "vals_overall": _first_num(m.get("vals_overall")),
        "aa_reasoning": _first_num(bms.get("aa_intelligence"), bm.get("aa_quality"), m.get("aa_live_quality")),
        "lm_elo": _first_num(bm.get("lm_elo"), bms.get("lmarena_elo")),
        "speed": _first_num(bm.get("speed_tps"), bms.get("aa_median_tps")),
    }


SHRINKAGE_LAMBDA = 0.20


def shrunk_weighted_z(pairs: list[tuple[float, float | None]], lam: float = SHRINKAGE_LAMBDA) -> float | None:
    """Empirical Bayes shrunk weighted z-score; returns None when all legs are missing."""
    present = [(w, z) for w, z in pairs if z is not None]
    if not present:
        return None
    return sum(w * z for w, z in present) / (sum(w for w, _ in present) + lam)


def scale_axis_score(z_val: float | None) -> float | None:
    """Map shrunk z-score onto bounded [40.0, 99.9] capability scale."""
    return round(max(40.0, min(99.9, 78.0 + (9.0 * z_val))), 1) if z_val is not None else None


def _pack_role_winner(scored_list: list[tuple[float, dict]], meta: tuple[str, str, str, str, str]) -> dict:
    """Pack winner + runner-up payload for one role recommendation."""
    title, label_short, icon, desc, desc_short = meta
    w_score, w_f = scored_list[0] if scored_list else (0.0, {})
    r_score, r_f = scored_list[1] if len(scored_list) > 1 else (0.0, {})
    return {
        "title": title,
        "label_short": label_short,
        "icon": icon,
        "desc": desc,
        "desc_short": desc_short,
        "winner": {"name": w_f.get("name", "—"), "pool_str": w_f.get("pool_str", ""), "score": w_score, "q": w_f.get("q", 0.0)},
        "runner_up": {"name": r_f.get("name", "—"), "pool_str": r_f.get("pool_str", ""), "score": r_score, "q": r_f.get("q", 0.0)},
    }


ROLE_META: dict[str, tuple[str, str, str, str, str]] = {
    "architecture": (
        "System Architecture & Spec Lock", "Architect", "🏗️",
        "HLE, CritPt, LiveBench & non-hallucination. Use for contracts, invariants, and hard debugging.",
        "Deep reasoning & spec lock for contracts and root-cause debugging.",
    ),
    "software_dev": (
        "Agentic Software Development", "Soft Dev", "💻",
        "CursorBench, FrontierCode 2.0, FrontierSWE, TerminalBench-4 & $/task ROI.",
        "Multi-file repo coding, CLI execution & empirical $/task efficiency.",
    ),
    "design": (
        "UI / UX & Frontend Design", "Design", "🎨",
        "Arena webdev-react, webdev Elo & IFBench constraint adherence.",
        "React/CSS layout craft, interactive UX & strict instruction fidelity.",
    ),
    "research": (
        "Academic Research & Synthesis", "Research", "🔬",
        "Omniscience non-hallucination, Long-Context, FrontierSWE Research, SciCode & GPQA (>=200k ctx).",
        "High epistemic honesty, long-context synthesis & scientific rigor.",
    ),
}
_ROLE_META = ROLE_META
ROLE_BADGE_LABELS = {k: f"{v[2]} {v[1]}" for k, v in ROLE_META.items()}


def _score_fallback_row(f: dict, zs: dict[str, list[float | None]], i: int) -> list[tuple[str, float]]:
    s_arc = scale_axis_score(shrunk_weighted_z([(0.50, zs["rsn"][i]), (0.30, zs["cod"][i]), (0.20, zs["q"][i])]))
    s_dev = scale_axis_score(shrunk_weighted_z([(0.45, zs["cod"][i]), (0.25, zs["q"][i]), (0.20, zs["cst"][i]), (0.10, zs["spd"][i])]))
    s_des = scale_axis_score(shrunk_weighted_z([(0.65, zs["des"][i]), (0.20, zs["cod"][i]), (0.15, zs["cst"][i])]))
    s_res = scale_axis_score(shrunk_weighted_z([(0.55, zs["rsn"][i]), (0.30, zs["q"][i]), (0.15, zs["cod"][i])]))
    if s_res is not None and f["ctx"] is not None and f["ctx"] < 200_000:
        s_res = round(max(40.0, s_res - 10.0), 1)
    pairs = (("architecture", s_arc), ("software_dev", s_dev), ("design", s_des), ("research", s_res))
    return [(rk, sv) for rk, sv in pairs if sv is not None]


def _fallback_z_series(feats: list[dict]) -> dict[str, list[float | None]]:
    return {
        "q": z_scores_none([f["q"] for f in feats]),
        "spd": z_scores_none([_pos_log10(f["speed"]) for f in feats]),
        "cst": z_scores_none([_neg_log10(f["eff_cost"]) for f in feats]),
        "cod": z_scores_none([_first_num(f["aa_coding"], f["vals_coding"]) for f in feats]),
        "des": z_scores_none([_first_num(f["lm_coding"], f["lm_elo"]) for f in feats]),
        "rsn": z_scores_none([_first_num(f["aa_reasoning"], f["vals_overall"]) for f in feats]),
    }


def _fallback_analyzer_role_buckets(feats: list[dict]) -> dict[str, list[tuple[float, dict]]]:
    """Fallback role scoring for legacy analyzer rows (ocheck/ccheck) lacking 5-axis fields."""
    zs = _fallback_z_series(feats)
    buckets: dict[str, list[tuple[float, dict]]] = {k: [] for k in ROLE_META}
    for i, f in enumerate(feats):
        for rk, sv in _score_fallback_row(f, zs, i):
            buckets[rk].append((sv, f))
    return buckets


def _precomputed_role_buckets(feats: list[dict]) -> dict[str, list[tuple[float, dict]]]:
    buckets: dict[str, list[tuple[float, dict]]] = {k: [] for k in ROLE_META}
    for f in feats:
        rmap = f["roles"] or {}
        for rk, sv in rmap.items():
            num = _safe_float(sv)
            if rk in buckets and num is not None:
                buckets[rk].append((num, f))
    return buckets


def compute_role_recommendations(models_list: list[dict], context: str = "bcheck") -> dict[str, dict]:
    """Compute top winner & runner-up across Architecture, Software Dev, Design, and Research."""
    clean = [m for m in (models_list or []) if not m.get("signal_mirror_of")]
    feats = [f for f in (_extract_model_role_features(m, context=context) for m in clean) if f["q"] is not None]
    if len(feats) < 2:
        return {}
    buckets = _precomputed_role_buckets(feats) if any(f["roles"] for f in feats) else _fallback_analyzer_role_buckets(feats)
    return {
        rk: _pack_role_winner(sorted(buckets[rk], key=lambda x: x[0], reverse=True), meta)
        for rk, meta in ROLE_META.items()
        if buckets[rk]
    }


def _role_palette(color: bool) -> tuple[str, str, str, str, str, str]:
    """Return ANSI tuple (label, winner, runner_up, score, dim, reset) or empty strings."""
    return (C_BOLD + C_CYAN, C_BOLD + C_GREEN, C_SILVER, C_YELLOW, C_DIM, C_RESET) if color else ("", "", "", "", "", "")


def render_role_recommendations_cli(role_recs: dict[str, dict], color: bool = True, is_slim: bool = False, width: int = 100) -> list[str]:
    """Render ANSI-formatted CLI role recommendations box."""
    if not role_recs:
        return []
    title = "🎯 ROLE RECOMMENDATIONS (Weighted Selection):" if is_slim else "🎯 ROLE & FUNCTION RECOMMENDATIONS (Weighted Multi-Metric Selection):"
    out = [f"{C_BOLD}{C_GOLD}{title}{C_RESET}" if color else title]
    c_lbl, c_win, c_ru, c_scr, c_dim, c_rst = _role_palette(color)
    n_lim, ru_lim, lbl_w = (26, 26, 14) if is_slim else (28, 28, 34)
    for r in role_recs.values():
        w, ru = r["winner"], r["runner_up"]
        label = (r["label_short"] if is_slim else r["title"]).ljust(lbl_w)
        desc = r["desc_short"] if is_slim else r["desc"]
        out.append(
            f"  • {r['icon']} {c_lbl}{label}{c_rst}: {c_win}{w['name'][:n_lim]}{c_rst} {w['pool_str']} "
            f"({c_scr}{w['score']:.1f}{c_rst}) · {c_dim}Runner-up:{c_rst} {c_ru}{ru['name'][:ru_lim]}{c_rst} {ru['pool_str']} ({ru['score']:.1f})"
        )
        out.append(f"       {c_dim}↳ {desc}{c_rst}")
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
    """Load previously saved live snapshot JSON file if it exists.

    A present-but-corrupt baseline is a loud WARN (S1-M2): the caller silently
    cold-starts either way, but operators must be able to tell the difference.
    """
    target = pathlib.Path(json_path)
    if target.is_file():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  WARN baseline snapshot CORRUPT (not cold start): {target}: {e}", file=sys.stderr)
            return None
    return None


def _epoch_to_utc(num: float) -> dt.datetime | None:
    """Convert Unix seconds or milliseconds scalar into aware UTC datetime."""
    try:
        secs = num / 1000.0 if num > 1e11 else num
        return dt.datetime.fromtimestamp(secs, tz=dt.UTC)
    except Exception:
        return None


def _parse_str_timestamp(s: str) -> dt.datetime | None:
    """Parse ISO 8601 or numeric string timestamp into aware UTC datetime."""
    with contextlib.suppress(Exception):
        parsed = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=dt.UTC) if parsed.tzinfo is None else parsed
    with contextlib.suppress(Exception):
        num = float(s)
        return _epoch_to_utc(num) if math.isfinite(num) else None
    return None


def parse_timestamp(val) -> dt.datetime | None:
    """Parse ISO 8601 string or numeric epoch (seconds/ms) into aware UTC datetime."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return _epoch_to_utc(val) if math.isfinite(val) else None
    if isinstance(val, str) and (s := val.strip()):
        return _parse_str_timestamp(s)
    return None


def _catalog_entry_id(r: dict, id_key: str) -> str | None:
    """Return canonical row ID checking `id_key` and concrete IDs before aliases."""
    if not isinstance(r, dict):
        return None
    for k in (id_key, "model_id", "or_slug", "aa_slug", "lm_slug", "display", "id"):
        if v := r.get(k):
            return v
    for ak in ("aa_aliases", "lm_aliases", "live_aliases"):
        aliases = r.get(ak)
        if aliases and aliases[0]:
            return aliases[0]
    return None


def _index_baseline_catalog(
    prev_snapshot: list[dict] | dict | None,
    id_key: str,
    require_docs_tag: bool,
) -> tuple[str, dict[str, dict], dict[str, dict]]:
    """Return (baseline_mode ['empty'|'catalog'], display_map, seen_map)."""
    if isinstance(prev_snapshot, dict):
        mode = "catalog"
        rows = prev_snapshot.get("models", [])
        docs_only = require_docs_tag and id_key == "model_id" and ("catalog_diff" in prev_snapshot)
    elif isinstance(prev_snapshot, list):
        mode, rows, docs_only = "catalog", prev_snapshot, False
    else:
        return "empty", {}, {}

    display_map: dict[str, dict] = {}
    seen_map: dict[str, dict] = {}
    for m in rows:
        if mid := _catalog_entry_id(m, id_key):
            seen_map[mid] = m
            if not docs_only or m.get("is_docs_model"):
                display_map[mid] = m
    return mode, display_map, seen_map


def _resolve_first_seen(nr: dict, prev_m: dict | None, created_val, brand_new: bool, now_dt: dt.datetime) -> str | None:
    """Resolve earliest known timestamp across row, baseline, creation date, or now."""
    if first_seen := (nr.get("first_seen") or (prev_m.get("first_seen") if prev_m else None)):
        return first_seen
    if created_val is not None and (created_dt := parse_timestamp(created_val)):
        return created_dt.isoformat()
    return now_dt.isoformat() if brand_new else None


def _classify_catalog_row(
    r: dict,
    seen_map: dict[str, dict],
    baseline_mode: str,
    id_key: str,
    window_days: float,
    now_dt: dt.datetime,
) -> tuple[str, dict, bool] | None:
    """Resolve `first_seen` and freshness status for one current catalog row."""
    if not (mid := _catalog_entry_id(r, id_key)):
        return None
    nr = dict(r)
    created_val = nr.get("created") or nr.get("created_date")
    brand_new = baseline_mode == "catalog" and mid not in seen_map
    first_seen = _resolve_first_seen(nr, seen_map.get(mid), created_val, brand_new, now_dt)
    if first_seen:
        nr["first_seen"] = first_seen

    parsed_fs = parse_timestamp(first_seen)
    age_days = (now_dt - parsed_fs).total_seconds() / 86400.0 if parsed_fs else -1.0
    in_window = 0 <= age_days <= window_days and (baseline_mode == "catalog" or created_val is not None)
    nr["is_new"] = in_window or brand_new
    return mid, nr, nr["is_new"]


def diff_model_catalog(
    current_rows: list[dict],
    prev_snapshot: list[dict] | dict | None,
    id_key: str = "model_id",
    window_days: float = 7.0,
    now: dt.datetime | None = None,
    require_docs_tag: bool = True,
) -> dict:
    """Compute added (green) and removed (red) models against previous baseline snapshot."""
    now_dt = now or dt.datetime.now(dt.UTC)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=dt.UTC)

    baseline_mode, prev_models_map, prev_seen_map = _index_baseline_catalog(prev_snapshot, id_key, require_docs_tag)
    current_ids, added_ids, out_rows = set(), set(), []
    for r in current_rows:
        classified = _classify_catalog_row(r, prev_seen_map, baseline_mode, id_key, window_days, now_dt)
        if not classified:
            continue
        mid, nr, is_new = classified
        current_ids.add(mid)
        if is_new:
            added_ids.add(mid)
        out_rows.append(nr)

    removed_ids = (set(prev_models_map) - current_ids) if baseline_mode == "catalog" else set()
    removed_models = [prev_models_map[mid] for mid in sorted(removed_ids)]
    return {
        "added_ids": added_ids,
        "removed_ids": removed_ids,
        "removed_models": removed_models,
        "rows": out_rows,
    }


def _nested_num(rm: dict, key: str, parents: tuple[str, ...]) -> float | None:
    """Extract first finite numeric score checking sub-dicts before top-level."""
    for p in parents:
        sub = rm.get(p)
        if isinstance(sub, dict) and _is_num(v := sub.get(key)):
            return float(v)
    return float(v) if _is_num(v := rm.get(key)) else None


def _removed_scope_badge(rm: dict, mid: str) -> str | None:
    """Format pricing limit, pool, or provider tag for a removed catalog entry."""
    if isinstance(pr := rm.get("pricing"), dict):
        lim = pr.get("monthly_credits") if pr.get("monthly_credits") is not None else pr.get("monthly_usage_limit_usd")
        if lim is not None:
            return f"Prior Limit: ${lim:.0f}/m"
        return "Prior Limit: Free" if "free" in mid.lower() else None
    if "pool" in rm:
        return f"Pool: {str(rm.get('pool', '')).upper()}"
    return f"Prov: {rm['provider']}" if "provider" in rm else None


def _removed_model_details(rm: dict, mid: str) -> list[str]:
    """Build detail tokens for one removed/deprecated model row."""
    details = [b] if (b := _removed_scope_badge(rm, mid)) else []
    fgi = _nested_num(rm, "fgi_score", ("value", "benchmarks"))
    avi = _nested_num(rm, "avi_score", ("value", "benchmarks"))
    q_val = _nested_num(rm, "capability_q", ("benchmarks",))
    for label, val in (("FGI", fgi), ("AVI", avi)):
        if val is not None:
            details.append(f"{label} {val:.1f}")
    if q_val is not None and fgi is None:
        details.append(f"Q {q_val:.1f}")
    return details


def render_removed_models_cli(removed_models: list[dict], color: bool = True, is_slim: bool = False, id_key: str = "model_id") -> list[str]:
    """Format removed/deprecated models list uniformly across color and plain modes."""
    if not removed_models:
        return []
    header = f"🔻 REMOVED / DEPRECATED MODELS ({len(removed_models)}):"
    lines = [f"{C_BOLD}{C_RED}{header}{C_RESET}" if color else f"REMOVED / DEPRECATED MODELS ({len(removed_models)}):"]
    prefix = f"  {C_RED}❌ {C_BOLD}" if color else "  [-] "
    mid_end = C_RESET if color else ""
    det_start, det_end = (C_DIM, C_RESET) if color else ("", "")
    id_keys = (id_key, "model_id", "display", "or_slug", "id")
    for rm in removed_models:
        mid = next((str(v) for k in id_keys if (v := rm.get(k))), "unknown")
        details = _removed_model_details(rm, mid)
        detail_str = f" ({', '.join(details)})" if details else ""
        lines.append(f"{prefix}{mid:<22}{mid_end}{det_start}{detail_str}{det_end}")
    return lines


def format_context_window(tokens: int | float | None) -> str:
    """Format token count into compact human-readable string (e.g. 1.0M, 200k, 128k, 64k, —)."""
    if not _is_num(tokens) or tokens <= 0:
        return "—"
    t = int(tokens)
    if t >= 1_000_000:
        val = t / 1_000_000
        return f"{val:.1f}M" if (val % 1 != 0) else f"{int(val)}M"
    if t >= 1000:
        return f"{t // 1000}k"
    return str(t)


def _best_role_from_map(roles: dict | None, q_val: float | None, coverage_count: int) -> str:
    if q_val is None or coverage_count == 0:
        return "—"
    if isinstance(roles, dict):
        scored = [(v, k) for k, v in roles.items() if _is_num(v) and k in ROLE_BADGE_LABELS]
        if scored:
            return ROLE_BADGE_LABELS[max(scored)[1]]
    return "🏗️ Architect" if q_val >= 88.0 else ("💻 Soft Dev" if q_val >= 72.0 else "🎨 Design")


_AA_AUTH_KEYS = ("aa_quality", "aa_hle", "aa_critpt", "aa_tb4", "aa_ifbench", "aa_gpqa", "aa_scicode", "aa_lcr", "aa_non_halluc")


def _authority_flags(m: dict, bm: dict, lb: dict) -> dict[str, bool]:
    return {
        "has_arena": any(bm.get(k) is not None for k in ("lm_elo", "lm_coding", "lm_webdev_elo")),
        "has_aa": (m.get("aa_live_quality") is not None) or any(bm.get(k) is not None for k in _AA_AUTH_KEYS),
        "has_vals": (m.get("vals_overall") is not None) or (m.get("vals_metrics") is not None),
        "has_live": lb.get("overall") is not None,
        "has_fc2": bm.get("fc2_score") is not None,
        "has_fswe": bm.get("fswe_overall") is not None,
        "has_cursor": bm.get("cursor_score") is not None,
    }


def _as_dict(val) -> dict:
    return val if isinstance(val, dict) else {}


def extract_capability_pillars(m: dict) -> dict:
    """Extract normalized capability dimensions and 7-authority coverage."""
    bm = _as_dict(m.get("base_metrics"))
    lb = _as_dict(m.get("livebench"))
    axes = _as_dict(m.get("axes"))

    reason = _first_num(axes.get("reasoning"), bm.get("aa_quality"), m.get("aa_live_quality"), lb.get("reasoning"))
    coding = _first_num(axes.get("coding"), bm.get("cursor_score"), bm.get("fc2_score"), bm.get("aa_tb4"), lb.get("coding"))
    coding_elo = _first_num(bm.get("lm_coding"))
    speed = _first_num(bm.get("speed_tps"))
    ctx = _first_num(m.get("context_length"), bm.get("context_length"))

    flags = _authority_flags(m, bm, lb)
    coverage_count = sum(flags.values())
    q_val = _first_num(m.get("capability_q"), m.get("composite_score"))
    best_role = m.get("best_role") or _best_role_from_map(m.get("roles"), q_val, coverage_count)

    return {
        "reasoning": reason,
        "coding": coding,
        "design": _first_num(axes.get("design")),
        "research": _first_num(axes.get("research")),
        "economics": _first_num(axes.get("economics")),
        "coding_elo": _safe_int(coding_elo),
        "speed": speed,
        "context_length": _safe_int(ctx),
        "coverage_count": coverage_count,
        "authority_total": 7,
        **flags,
        "vals_overall": _safe_float(m.get("vals_overall")),
        "vals_coding": _safe_float(m.get("vals_coding")),
        "best_role": best_role,
    }


# ==============================================================================
# 9. QUOTA MONITOR & COST-BENEFIT ANALYZER SHARED CORE
# ==============================================================================
OCGO_DOCS = "https://opencode.ai/v2/docs/console/go/"


def parse_iso_utc(iso_str: str | None) -> dt.datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime (or None)."""
    if not iso_str:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=dt.UTC) if parsed.tzinfo is None else parsed
    except Exception:
        return None


def format_relative_seconds(total_seconds: int) -> str:
    """Format a countdown delta in seconds as '2d 3h', '4h 12m', '15m', or 'now'."""
    if total_seconds <= 0:
        return "now"
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h" if hours > 0 else f"{days}d"
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    return f"{minutes}m"


def format_relative_time(target: dt.datetime | None, now: dt.datetime | None = None) -> str:
    """Format target - now countdown robustly across naive/aware datetimes."""
    if not target:
        return "unknown"
    t_utc = target.replace(tzinfo=dt.UTC) if target.tzinfo is None else target
    n_utc = dt.datetime.now(dt.UTC) if now is None else (now.replace(tzinfo=dt.UTC) if now.tzinfo is None else now)
    return format_relative_seconds(int((t_utc - n_utc).total_seconds()))


def format_relative_epoch_ms(epoch_ms: int | float | None, now_ms: float | None = None) -> str:
    """Format an epoch-millisecond deadline relative to now."""
    if not epoch_ms:
        return "unknown"
    if now_ms is None:
        now_ms = dt.datetime.now(dt.UTC).timestamp() * 1000.0
    return format_relative_seconds(int((epoch_ms - now_ms) / 1000.0))


def get_percent_color(percent: float) -> str:
    """Color band for quota usage percentage [0..100]."""
    return color_ladder(
        percent,
        [(lambda v: v >= 90.0, C_BOLD + C_RED), (lambda v: v >= 70.0, C_YELLOW), (lambda v: v >= 40.0, C_CYAN)],
        default_color=C_GREEN,
    )


def format_bar(percent: float, width: int = 20, colorize: bool = True) -> str:
    """Render a fixed-width quota bar with [0, 100] clamping."""
    clamped = max(0.0, min(100.0, float(percent)))
    filled = int(round((clamped / 100.0) * width))
    bar = ("█" * filled) + ("░" * (width - filled))
    if not colorize:
        return f"[{bar}]"
    return f"{get_percent_color(clamped)}[{bar}]{C_RESET}"


def quota_box_chrome(title: str, subtitle_lines: list[str], box_w: int, color: bool) -> tuple[list[str], str, str]:
    """Build Unicode/plain quota dashboard header lines using true display_len()."""
    c_b, c_d, c_c, c_r = (C_BOLD, C_DIM, C_CYAN, C_RESET) if color else ("", "", "", "")
    top = f"{c_d}┌" + ("─" * (box_w - 2)) + f"┐{c_r}" if color else "-" * box_w
    mid = f"{c_d}├" + ("─" * (box_w - 2)) + f"┤{c_r}" if color else "-" * box_w
    bot = f"{c_d}└" + ("─" * (box_w - 2)) + f"┘{c_r}" if color else "-" * box_w
    inner = box_w - 2
    t_pad = max(0, inner - display_len(f" {title}"))
    lines = [top, f"{c_d}│{c_r} {c_b}{c_c}{title}{c_r}{' ' * t_pad}{c_d}│{c_r}" if color else f"| {title}"]
    for raw_sub in subtitle_lines:
        sub = raw_sub
        if display_len(sub) > inner - 2:
            sub = _truncate_display(sub, inner - 2)
        s_pad = max(0, inner - display_len(sub))
        lines.append(f"{c_d}│{c_r}{c_d}{sub}{c_r}{' ' * s_pad}{c_d}│{c_r}" if color else f"|{sub}")
    lines.append(mid)
    return lines, mid, bot


def format_compact_num(v) -> str:
    """Format request counts compactly (e.g. 1.2M, 14.5k, 320); NaN/None -> '—'."""
    if not _is_num(v):
        return "—"
    n = float(v)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{int(n) // 1000}k" if (n % 1000 == 0) else f"{n / 1_000:.1f}k"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{n:.0f}"


def offline_snapshot_note(raw_dir: pathlib.Path, labels: tuple[tuple[str, str], ...]) -> tuple[str, str]:
    """Summarize raw snapshot dates and >24h staleness warnings for an analyzer run."""
    dates, stale = [], []
    for name, part in labels:
        snap = pick_latest_raw(raw_dir, part)
        if snap is None:
            stale.append(f"{name} missing")
            continue
        ds = snapshot_date_str(snap)
        if ds:
            dates.append(ds)
        age_h = snapshot_age_hours(snap)
        if age_h > CACHE_TTL_H:
            stale.append(f"{name} {age_h / 24:.0f}d old")
    span = f"{min(dates)}..{max(dates)}" if dates else "none"
    label = f"OFFLINE (data: {span})"
    line = f"  {label}"
    if stale:
        line += "\n  WARN cached responses >24h — run with --fetch: " + ", ".join(stale)
    return line, label


def fetch_bytes(url: str, timeout: int = 20, verbose: bool = False) -> bytes | None:
    """Fetch raw bytes from URL with explicit timeout and stderr warning on failure."""
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


def _read_livebench_csv(raw_dir: pathlib.Path, p: pathlib.Path) -> dict | None:
    try:
        m_date = re.search(r"(\d{8})", p.stem)
        cat_json = None
        if m_date:
            cat_p = raw_dir / f"livebench_categories_{m_date.group(1)}.json"
            if cat_p.exists():
                cat_json = cat_p.read_text(encoding="utf-8", errors="ignore")
        return parse_livebench(p.read_text(encoding="utf-8", errors="ignore"), categories_json=cat_json)
    except Exception as e:  # noqa: BLE001 — logged skip
        print(f"  WARN LiveBench snapshot skipped ({p}): {e}", file=sys.stderr)
        return None


def load_livebench_snapshots(raw_dir: pathlib.Path, verbose: bool = False) -> dict:
    """Load LiveBench CSV + paired category JSON snapshots newest-first."""
    live_map: dict = {}
    csv_matches = [p for p in sorted(glob.glob(str(raw_dir / "*livebench*20*.csv"))) if "cost" not in p]
    for p_csv in reversed(csv_matches):
        p = pathlib.Path(p_csv)
        data = _read_livebench_csv(raw_dir, p)
        if not data:
            continue
        filled = sum(1 for k in data if k not in live_map)
        for k, v in data.items():
            live_map.setdefault(k, v)
        if verbose:
            print(f"  LiveBench {p.name}: {len(data)} rows, {filled} new keys")
    return live_map


def extract_balanced_tag(text: str, start_idx: int, tag: str = "div") -> str | None:
    """Extract balanced `<tag>...</tag>` substring starting at `start_idx`."""
    pat = re.compile(rf"<(/?){tag}\b[^>]*>", re.IGNORECASE)
    depth = 0
    for m in pat.finditer(text, start_idx):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return text[start_idx : m.end()]
    return None


def extract_panels_by_plan(html_text: str, plan: str) -> list[str]:
    """Extract matching `role='tabpanel'` / `data-plan-panel` HTML blocks."""
    pat = re.compile(rf'<div\b[^>]*role=["\']tabpanel["\'][^>]*data-plan-panel=["\']{re.escape(plan)}["\'][^>]*>', re.I)
    panels = []
    for m in pat.finditer(html_text):
        blk = extract_balanced_tag(html_text, m.start(), "div")
        if blk:
            panels.append(blk)
    return panels


def _num_or(v, fallback: float = -1.0) -> float:
    return float(v) if _is_num(v) else fallback


def _req_doc_or_comp(r: dict, doc_key: str, comp_key: str) -> float:
    reqs = r.get("requests") or {}
    val = reqs.get(doc_key)
    if val is None:
        val = reqs.get(comp_key)
    return float(val) if _is_num(val) else -1.0


_SORT_FIELD_MAP = {
    "value": (("value", "qvi_score"), ("benchmarks", "capability_q")),
    "qvi": (("value", "qvi_score"), ("benchmarks", "capability_q")),
    "avi": (("value", "avi_score"), ("benchmarks", "capability_q")),
    "fgi": (("value", "fgi_score"), ("benchmarks", "capability_q")),
    "bfi": (("value", "bfi_score"), ("benchmarks", "capability_q")),
    "cap": (("benchmarks", "capability_q"), ("value", "avi_score")),
    "quality": (("benchmarks", "aa_intelligence"), ("benchmarks", "capability_q")),
    "intel": (("value", "intelligence_per_dollar"), ("benchmarks", "capability_q")),
    "intel-cc": (("benchmarks", "cc_intelligence"), ("benchmarks", "capability_q")),
}


_REQ_SORT_FIELDS = {
    "reqmo": ("per_month_docs", "per_month_computed"),
    "req5h": ("per_5h_docs", "per_5h_computed"),
}


def build_analyzer_sort_key(sort_mode: str, eff_cost_fn):
    """Build a sort key callable for analyzer CLI tables without branching bloat."""
    if sort_mode in _REQ_SORT_FIELDS:
        doc_k, comp_k = _REQ_SORT_FIELDS[sort_mode]
        return lambda r: (-_req_doc_or_comp(r, doc_k, comp_k), -_num_or(r["value"].get("avi_score")), r["model_id"])
    spec = _SORT_FIELD_MAP.get(sort_mode)
    if spec is not None:
        (s1, k1), (s2, k2) = spec
        return lambda r: (-_num_or(r[s1].get(k1)), -_num_or(r[s2].get(k2)), r["model_id"])
    if sort_mode != "cost":
        raise ValueError(f"unknown sort mode: {sort_mode}")
    return lambda r: (eff_cost_fn(r), -_num_or(r["benchmarks"].get("capability_q")), r["model_id"])


def _clear_unscored_analyzer_row(b: dict, v: dict) -> None:
    for bk in ("composite_score", "capability_q", "p_success", "token_multiplier", "qvi_score", "avi_score", "fgi_score", "bfi_score"):
        b[bk] = None
    for vk in ("effective_cost_per_request", "effective_requests_per_5h", "effective_requests_per_month", "qvi_score", "value_score", "avi_score", "fgi_score", "bfi_score"):
        v[vk] = None


def _eff_req_count(r: dict, doc_k: str, comp_k: str, t_mult: float) -> int | None:
    raw = _req_doc_or_comp(r, doc_k, comp_k)
    if raw < 0:
        return None
    return 0 if raw == 0 else _safe_int(round(raw / t_mult), strip_currency=False)


def _apply_analyzer_prices(b: dict, v: dict, p: dict, t_mult: float) -> None:
    pin = _safe_float(p.get("input_per_1m"), strip_currency=False)
    pout = _safe_float(p.get("output_per_1m"), strip_currency=False)
    if pin is None or pout is None:
        b["blended_price"] = b["effective_cost"] = v["effective_blended_price"] = None
        return
    blended = (0.80 * pin) + (0.20 * pout)
    eff_blended = compute_effective_cost(blended, t_mult)
    b["blended_price"] = round(blended, 2)
    b["effective_cost"] = v["effective_blended_price"] = eff_blended


def _apply_analyzer_economics(r: dict, q_score: float, p_succ: float, t_mult: float) -> None:
    b, v, p = r["benchmarks"], r["value"], r["pricing"]
    _apply_analyzer_prices(b, v, p, t_mult)
    c_req = r.get("cost_per_request_usd")
    eff_c_req = (c_req * t_mult) if c_req is not None else None
    v["effective_cost_per_request"] = round(eff_c_req, 6) if eff_c_req is not None else None

    eff_5h = _eff_req_count(r, "per_5h_docs", "per_5h_computed", t_mult)
    eff_mo = _eff_req_count(r, "per_month_docs", "per_month_computed", t_mult)
    v["effective_requests_per_5h"] = eff_5h
    v["effective_requests_per_month"] = eff_mo
    qvi = compute_qvi(q_score, eff_5h)
    b["qvi_score"] = v["qvi_score"] = v["value_score"] = qvi

    toks = sum(r.get("tokens", {}).get(tk, 0) or 0 for tk in ("est_input", "est_cached", "est_output"))
    has_pos_cost = eff_c_req is not None and eff_c_req > 0 and toks > 0
    avi = compute_avi(q_score, eff_c_req * 1_000_000.0 / toks) if has_pos_cost else None
    fgi = compute_fgi(q_score, p_succ)
    speed = _safe_float(b.get("aa_median_tps"), default=60.0, strip_currency=False) or 60.0
    bl = b.get("blended_price")
    bfi = compute_bfi(q_score, speed, bl) if bl is not None else None
    b["avi_score"] = v["avi_score"] = avi
    b["fgi_score"] = v["fgi_score"] = fgi
    b["bfi_score"] = v["bfi_score"] = bfi


def _analyzer_z_vecs(rows: list[dict]) -> tuple:
    lb_vals = [
        r["benchmarks"]["livebench"].get("overall") if isinstance(r["benchmarks"].get("livebench"), dict) else None
        for r in rows
    ]
    return (
        ("aa_intelligence", 0.30, get_z_scores([r["benchmarks"]["aa_intelligence"] for r in rows])),
        ("aa_coding", 0.21, get_z_scores([r["benchmarks"]["aa_coding"] for r in rows])),
        ("aa_agentic", 0.17, get_z_scores([r["benchmarks"]["aa_agentic"] for r in rows])),
        ("lmarena_elo", 0.17, get_z_scores([r["benchmarks"]["lmarena_elo"] for r in rows])),
        ("livebench", 0.15, get_z_scores(lb_vals)),
    )


def score_analyzer_rows(rows: list[dict]) -> None:
    """Compute composite Q, P_succ, T_mult, QVI, AVI, FGI, and BFI across analyzer rows."""
    vecs = _analyzer_z_vecs(rows)
    for i, r in enumerate(rows):
        b, v = r["benchmarks"], r["value"]
        cov = [lbl for key, lbl in (("aa_intelligence", "AA"), ("lmarena_elo", "LM"), ("livebench", "LB")) if b[key] is not None]
        r["coverage"] = cov or ["—"]
        present = [(w, zs[i]) for fk, w, zs in vecs if b[fk] is not None]
        if not present:
            _clear_unscored_analyzer_row(b, v)
            continue
        cz = sum(w * z for w, z in present) / sum(w for w, _ in present)
        q_score = compute_capability_q(cz)
        p_succ = compute_p_success(q_score)
        t_mult = compute_token_multiplier(p_succ)
        b["composite_score"] = b["capability_q"] = q_score
        b["p_success"] = p_succ
        b["token_multiplier"] = t_mult
        _apply_analyzer_economics(r, q_score, p_succ, t_mult)


def compute_pareto_ids(rows: list[dict], eff_cost_fn, allowed_ids: set | None = None) -> set:
    """Return undefeated capability-vs-cost model_ids."""
    cand = [
        r for r in rows
        if (allowed_ids is None or r["model_id"] in allowed_ids) and r["benchmarks"].get("capability_q") is not None
    ]
    out = set()
    for a in cand:
        a_cost, a_q = eff_cost_fn(a), a["benchmarks"]["capability_q"]
        peers = [(eff_cost_fn(b), b["benchmarks"]["capability_q"]) for b in cand if b is not a]
        if not pareto_dominated(a_cost, a_q, peers, cost_epsilon=0.0001):
            out.add(a["model_id"])
    return out


def render_removed_html_section(removed_models: list[dict], limit_fn, subtitle: str) -> str:
    """Shared HTML block listing removed/deprecated models for analyzer dashboards."""
    if not removed_models:
        return ""
    tags = []
    for rm in removed_models:
        rm_id = html_lib.escape(rm.get("model_id", "unknown"))
        fgi = _nested_num(rm, "fgi_score", ("value", "benchmarks"))
        avi = _nested_num(rm, "avi_score", ("value", "benchmarks"))
        fgi_s = f"FGI {fgi:.1f}" if fgi is not None else "FGI —"
        avi_s = f"AVI {avi:.1f}" if avi is not None else "AVI —"
        tags.append(f'<span class="removed-tag">❌ <b>{rm_id}</b> <span class="mid">(Prior: {limit_fn(rm)}, {fgi_s}, {avi_s})</span></span>')
    return (
        f'<div class="removed-section">\n'
        f'  <div class="removed-title">🔻 Removed / Deprecated Models ({len(removed_models)})</div>\n'
        f'  <div class="sub" style="margin-bottom:8px;">{html_lib.escape(subtitle)}</div>\n'
        f'  <div>{"".join(tags)}</div>\n</div>'
    )


def render_analyzer_html_shell(
    title: str,
    subtitle_html: str,
    legend_top_html: str,
    th_cols: list[str],
    trs: list[str],
    legend_bot: str,
    removed_html: str,
    role_recs_html: str,
    takeaway_html: str,
    footer_note_html: str,
    work_sentence: str = "",
    out_href: str = "",
) -> str:
    """Shared standalone HTML document wrapper for ocheck/ccheck dashboards."""
    ths = "".join(f"<th>{html_lib.escape(h)}</th>" for h in th_cols)
    footer = f'<div class="footer"><span class="path">path: {html_lib.escape(out_href)}</span><span class="work">{html_lib.escape(work_sentence)}</span></div>' if (out_href or work_sentence) else ""
    body = (
        f'<h1>{html_lib.escape(title)}</h1>\n<p class="sub">{subtitle_html}</p>\n'
        f'<div class="card">{legend_top_html}</div>\n'
        f'<div class="card"><table id="tbl"><thead><tr>{ths}</tr></thead>\n<tbody>{"".join(trs)}</tbody></table>\n'
        f'<div class="legend">{html_lib.escape(legend_bot)}</div></div>\n'
        f'{removed_html}\n{role_recs_html}\n'
        f'<div class="call">{takeaway_html}</div>\n<p class="note">{footer_note_html}</p>\n{footer}'
    )
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html_lib.escape(title)}</title><style>{HTML_CSS_COMMON}</style></head>'
        f'<body><div class="wrap">{body}</div>{HTML_SORT_SCRIPT}</body></html>\n'
    )


# ==============================================================================
# 10. SHARED SNAPSHOT LOADERS & STYLED CLI TABLE ENGINE (fcheck / scheck)
# ==============================================================================

_RANK_BADGE_MAP = {1: "🥇#1", 2: "🥈#2", 3: "🥉#3"}
_RANK_COLOR_MAP = {1: C_BOLD + C_GOLD, 2: C_BOLD + C_SILVER, 3: C_BOLD + C_BRONZE}


def rank_label_and_color(rank_num: int) -> tuple[str, str]:
    """Return 1-based podium badge and bold ANSI foreground color."""
    return _RANK_BADGE_MAP.get(rank_num, f" #{rank_num}"), _RANK_COLOR_MAP.get(rank_num, C_BOLD + C_WHITE)


def _decode_body(body: str | bytes, errors: str = "ignore") -> str:
    return body if isinstance(body, str) else body.decode("utf-8", errors=errors)


def _fetch_live_json(raw_dir: pathlib.Path, root_dir: pathlib.Path, api_url: str, prefix: str, write: bool):
    body = fetch_url(api_url, timeout=20)
    if not body:
        print(f"  WARN {api_url} fetch failed, falling back to cached snapshot", file=sys.stderr)
        return None
    try:
        data = json.loads(_decode_body(body))
    except Exception as exc:
        print(f"  WARN {prefix} json parse: {exc}", file=sys.stderr)
        return None
    if write:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
        target = raw_dir / f"{prefix}_{stamp}.json"
        atomic_write_text(target, json.dumps(data, indent=2))
        print(f"  saved {prefix} -> {target.relative_to(root_dir)} ({len(body)} bytes)")
    return data


def fetch_or_load_json_snapshot(
    raw_dir: pathlib.Path,
    root_dir: pathlib.Path,
    api_url: str,
    prefix: str,
    fetch: bool = False,
    write: bool = True,
    verbose: bool = False,
):
    """Load newest JSON snapshot from raw_dir, or fetch live and validate JSON before writing."""
    if fetch:
        live = _fetch_live_json(raw_dir, root_dir, api_url, prefix, write)
        if live is not None:
            return live

    snap = pick_latest_raw(raw_dir, prefix)
    if not snap:
        print(f"  WARN no cached snapshot found for {prefix} — run with --fetch once to populate", file=sys.stderr)
        return None
    try:
        data = json.loads(snap.read_text(encoding="utf-8", errors="replace"))
        print(f"  cached {prefix}: {snap.name}{staleness_tag(snap)}")
        return data
    except Exception as exc:
        print(f"  WARN {prefix} cached snapshot bad: {exc}", file=sys.stderr)
        return None


def _read_aa_snapshot(raw_dir: pathlib.Path, verbose: bool) -> dict:
    snaps = sorted(raw_dir.glob("artificial_analysis*.html"), reverse=True)
    if not snaps:
        print("  AA: no cached snapshot available — run with --fetch once to populate")
        return {}
    for snap in snaps:
        try:
            aa_map = parse_aa(snap.read_text(encoding="utf-8", errors="ignore"), verbose=verbose)
        except Exception as exc:
            print(f"  WARN AA offline parse ({snap.name}): {exc}", file=sys.stderr)
            continue
        if aa_map:
            print(f"  AA: {len(aa_map)} entries ({snap.name}{staleness_tag(snap)})")
            return aa_map
        print(f"  WARN AA snapshot parsed 0 entries: {snap.name}", file=sys.stderr)
    return {}


def fetch_or_load_aa(
    raw_dir: pathlib.Path,
    root_dir: pathlib.Path,
    fetch: bool = False,
    write: bool = True,
    verbose: bool = False,
) -> dict:
    """Fetch Artificial Analysis leaderboard and validate non-empty parse before caching."""
    if not fetch:
        return _read_aa_snapshot(raw_dir, verbose)
    body = fetch_url(AA_URL, timeout=20)
    if not body:
        print("  WARN AA fetch failed, falling back to cached snapshot", file=sys.stderr)
        return _read_aa_snapshot(raw_dir, verbose)
    html_txt = _decode_body(body)
    aa_map = parse_aa(html_txt, verbose=verbose)
    if not aa_map:
        print("  WARN AA fetch parsed 0 models, keeping cached snapshot", file=sys.stderr)
        return _read_aa_snapshot(raw_dir, verbose)
    if write:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
        target = raw_dir / f"artificial_analysis_{stamp}.html"
        atomic_write_text(target, html_txt)
        print(f"  saved AA -> {target.relative_to(root_dir)} ({len(html_txt)} bytes)")
    print(f"  AA: {len(aa_map)} models")
    return aa_map


def fetch_or_load_lmarena(
    raw_dir: pathlib.Path,
    fetch: bool = False,
    write: bool = True,
    verbose: bool = False,
) -> dict:
    """Load cached LMArena snapshot or fetch HF board live (honoring write=False on --check)."""
    if not fetch:
        lm_map = load_lmarena_map(raw_dir, verbose=verbose)
        msg = f"  LMArena: {len(lm_map)} models (HF/HTML snapshot)" if lm_map else "  LMArena: no cached snapshot available — run with --fetch once to populate"
        print(msg)
        return lm_map
    payload = fetch_lmarena_hf_snapshot(raw_dir, verbose=verbose, do_write=write, force=True)
    lm_map = parse_lmarena_hf(payload, verbose=verbose) if payload else load_lmarena_map(raw_dir, verbose=verbose)
    if lm_map:
        print(f"  LMArena: {len(lm_map)} models")
    else:
        print("  WARN LMArena fetch failed", file=sys.stderr)
    return lm_map


def _render_ansi_table(headers: list[tuple[str, int, str]], styled_rows: list[list[tuple[str, str, int, str]]]) -> list[str]:
    sep = f"{C_DIM}│{C_RESET}"
    widths = [w + 2 for _, w, _ in headers]
    hdr_cells = [color_cell(h, C_BOLD + C_WHITE, width=w, align=a, bg=BG_HEADER) for h, w, a in headers]
    out = [
        f"{C_DIM}┌{'┬'.join('─' * n for n in widths)}┐{C_RESET}",
        f"{BG_HEADER}{sep}" + f"{BG_HEADER}{sep}".join(hdr_cells) + f"{BG_HEADER}{sep}",
        f"{C_DIM}├{'┼'.join('─' * n for n in widths)}┤{C_RESET}",
    ]
    for idx, cells in enumerate(styled_rows):
        bg = BG_ODD if idx % 2 else BG_EVEN
        row_sep = f"{bg}{sep}"
        rendered = [color_cell(txt, col, width=w, align=al, bg=bg) for txt, col, w, al in cells]
        out.append(f"{row_sep}{row_sep.join(rendered)}{row_sep}")
    out.append(f"{C_DIM}└{'┴'.join('─' * n for n in widths)}┘{C_RESET}")
    return out


def render_styled_cli_table(
    headers: list[tuple[str, int, str]],
    styled_rows: list[list[tuple[str, str, int, str]]],
    color: bool = True,
) -> list[str]:
    """Render ANSI-boxed or plain space-aligned CLI table from pre-styled cell tuples."""
    if color:
        return _render_ansi_table(headers, styled_rows)
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    out = [" ".join(pad_display(h, w, a) for h, w, a in headers), "-" * (inner_w + 2)]
    out.extend(" ".join(pad_display(txt, w, al) for txt, _, w, al in cells) for cells in styled_rows)
    out.append("-" * (inner_w + 2))
    return out


# ==============================================================================
# 11. EFFORT DISAGGREGATION, FRONTIER AGENT EVALS & 5-AXIS ROLE SCORING
# ==============================================================================
FRONTIERCODE_URL = "https://cognition.com/data/frontier-code-2.0/data.json"
FRONTIERSWE_URL = "https://www.frontierswe.com/"
CURSOR_EVALS_URL = "https://cursor.com/evals"

_EFFORT_ALIASES: dict[str, str] = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "med": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "x-high": "xhigh",
    "extra-high": "xhigh",
    "extra high": "xhigh",
    "max": "max",
    "maximum": "max",
    "none": "non-reasoning",
    "non-reasoning": "non-reasoning",
    "non reasoning": "non-reasoning",
    "instant": "non-reasoning",
}
EFFORT_DISPLAY: dict[str, str] = {
    "minimal": "Minimal",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Xhigh",
    "max": "Max",
    "non-reasoning": "Non-reasoning",
}
_EFFORT_SUFFIX_RE = re.compile(
    r"[-_\s]+(extra[-_\s]+high|x-?high|max|maximum|high|medium|med|low|minimal|non[-_\s]+reasoning)(?:[-_\s]+effort)?$",
    flags=re.I,
)
_CURSOR_SLUG_MAP: dict[str, str] = {
    "fable52": "claude-fable-5-2",
    "fable51": "claude-fable-5-1",
    "opus55": "claude-opus-5-5",
    "opus5": "claude-opus-5",
    "sonnet55": "claude-sonnet-5-5",
    "sonnet5": "claude-sonnet-5",
    "haiku55": "claude-haiku-5-5",
    "grok47": "grok-4-7",
    "grok": "grok-4-6",
    "sol": "gpt-5-6-sol",
    "terra": "gpt-5-6-terra",
    "luna": "gpt-5-6-luna",
    "muse-spark": "muse-spark-1-3",
}


def normalize_effort(val: str | None) -> str | None:
    """Normalize thinking/effort token onto canonical tier or None."""
    if not val:
        return None
    key = re.sub(r"\s+", " ", str(val).strip().lower()).removesuffix("-effort").removesuffix(" effort").strip()
    return _EFFORT_ALIASES.get(key)


_SIZE_TIER_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("max", ("qwen",)),
    ("medium", ("mistral", "devstral", "magistral", "ministral", "pixtral", "voxtral")),
)


def _is_model_size_suffix(stem: str, eff: str | None) -> bool:
    low = stem.lower()
    return any(eff == tier and low.startswith(prefixes) for tier, prefixes in _SIZE_TIER_PREFIXES)


def extract_effort_from_label(text: str | None) -> str | None:
    """Extract canonical thinking/effort tier from parenthetical or slug suffix."""
    if not text:
        return None
    s = str(text).strip()
    for grp in reversed(re.findall(r"\(([^)]+)\)", s)):
        for part in grp.split(","):
            eff = normalize_effort(part)
            if eff:
                return eff
    bare = re.sub(r"\s*\([^)]*\)", "", s).strip()
    m = _EFFORT_SUFFIX_RE.search(bare)
    if not m:
        return None
    eff = normalize_effort(m.group(1))
    return None if _is_model_size_suffix(bare[: m.start()], eff) else eff


def clean_display_name(raw_name: str) -> str:
    """Keep explicit thinking tier in display names while stripping Default Fallback noise."""
    cleaned = re.sub(r",\s*Default Fallback", "", str(raw_name or ""), flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip()


def _fc2_entry(model_name: str, eff: str, main: dict) -> tuple[str, str, dict] | None:
    score = _safe_float(main.get("new_score"))
    if score is None:
        return None
    base_slug = norm_model_slug(model_name)
    canon_eff = normalize_effort(eff)
    vslug = f"{base_slug}-{canon_eff}" if canon_eff else base_slug
    disp_eff = f" ({EFFORT_DISPLAY[canon_eff]})" if canon_eff else ""
    correct = _safe_float(main.get("correct"))
    rec = {
        "slug": vslug,
        "base_slug": base_slug,
        "name": f"{model_name}{disp_eff}",
        "effort": canon_eff,
        "is_fallback": False,
        "fc2_score": round(score * 100.0, 2) if score <= 1.0 else round(score, 2),
        "fc2_correct": round(correct * 100.0, 2) if (correct is not None and correct <= 1.0) else correct,
        "fc2_cost": _safe_float(main.get("cost")),
        "fc2_tokens": _safe_int(main.get("tokens")),
    }
    return vslug, base_slug, rec


def _store_with_base_fallback(out: dict[str, dict], vslug: str, base_slug: str, rec: dict, metric_key: str) -> None:
    out[vslug] = rec
    cur = out.get(base_slug)
    if cur is None or (cur.get("is_fallback") and (rec.get(metric_key) or -1.0) > (cur.get(metric_key) or -1.0)):
        fb = dict(rec)
        fb["is_fallback"] = vslug != base_slug
        out[base_slug] = fb


def _decode_json_dict(payload) -> dict:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            obj = json.loads(payload)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _ingest_fc2_model(out: dict[str, dict], model_name: str, effs: list, m_data: dict) -> None:
    for eff in effs:
        main = _as_dict(_as_dict(m_data.get(eff)).get("main"))
        built = _fc2_entry(model_name, eff, main)
        if built:
            _store_with_base_fallback(out, built[0], built[1], built[2], "fc2_score")


def parse_frontiercode(payload, verbose: bool = False) -> dict[str, dict]:
    """Parse Cognition FrontierCode 2.0 JSON with explicit effort levels."""
    data = _decode_json_dict(payload)
    efforts_map = _as_dict(data.get("efforts"))
    scores_data = _as_dict(data.get("data"))
    out: dict[str, dict] = {}
    for model_name in data.get("models") or []:
        _ingest_fc2_model(out, model_name, efforts_map.get(model_name) or [], _as_dict(scores_data.get(model_name)))
    if verbose:
        print(f"  FrontierCode 2.0: parsed {len(out)} model/effort keys")
    return out


def _fswe_record(r: dict) -> tuple[str, dict] | None:
    name = str(r.get("model") or "").strip()
    overall = _safe_float(r.get("overall"))
    if not name or overall is None:
        return None
    slug = norm_model_slug(name)
    impl = _safe_float(r.get("implementation"))
    perf = _safe_float(r.get("performance"))
    res = _safe_float(r.get("research"))
    cost = _safe_float(r.get("avgCostUsd"))
    return slug, {
        "slug": slug,
        "base_slug": slug,
        "name": name,
        "effort": extract_effort_from_label(name),
        "fswe_overall": round(overall, 2),
        "fswe_impl": round(impl, 2) if impl is not None else None,
        "fswe_perf": round(perf, 2) if perf is not None else None,
        "fswe_research": round(res, 2) if res is not None else None,
        "fswe_cost": round(cost, 2) if cost is not None else None,
    }


def parse_frontierswe(html_text: str, verbose: bool = False) -> dict[str, dict]:
    """Parse FrontierSWE leaderboard mean table from Next.js RSC HTML."""
    unesc = html_text.replace('\\"', '"').replace("\\/", "/")
    marker = '"mean":[{"model":'
    idx = unesc.find(marker)
    if idx == -1:
        return {}
    try:
        rows, _ = json.JSONDecoder().raw_decode(unesc[idx + len('"mean":'):])
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for r in rows if isinstance(rows, list) else []:
        built = _fswe_record(r) if isinstance(r, dict) else None
        if built:
            out[built[0]] = built[1]
    if verbose:
        print(f"  FrontierSWE: parsed {len(out)} models")
    return out


def _extract_cursor_js_entries(js_text: str) -> list[dict]:
    """Extract {key, label, runs} records from Cursor's immutable evals bundle."""
    entries: list[dict] = []
    pat = re.compile(r'\{key:"([^"]+)",[^{]*?label:"([^"]+)"[^{]*?runs:\[([^\]]+)\]')
    run_pat = re.compile(
        r'\{(?:effort:"([^"]+)",)?(?:isDefaultEffort:(!0|true),)?score:([0-9.]+),avgCost:([0-9.]+)'
        r'(?:,outputTokens:([0-9.]+))?(?:,avgSteps:([0-9.]+))?'
    )
    for m in pat.finditer(js_text):
        key, label, runs_blob = m.group(1), m.group(2), m.group(3)
        runs = [
            {
                "effort": rm.group(1) or None,
                "is_default": bool(rm.group(2)),
                "score": float(rm.group(3)),
                "cost": float(rm.group(4)),
                "tokens": int(float(rm.group(5))) if rm.group(5) else None,
                "steps": float(rm.group(6)) if rm.group(6) else None,
            }
            for rm in run_pat.finditer(runs_blob)
        ]
        if runs:
            entries.append({"key": key, "label": label, "runs": runs})
    return entries


def _extract_cursor_aria_entries(html_text: str) -> list[dict]:
    """Fallback extractor parsing CursorBench aria-label points directly from HTML."""
    seen: set[str] = set()
    by_base: dict[str, dict] = {}
    pat = re.compile(r'aria-label="([^":]+):\s*([0-9.]+)%,\s*\$([0-9.]+)\s*avg cost per task"')
    for m in pat.finditer(html_text):
        raw_lbl, scr, cst = m.group(1).strip(), float(m.group(2)), float(m.group(3))
        if raw_lbl in seen:
            continue
        seen.add(raw_lbl)
        eff = extract_effort_from_label(raw_lbl)
        base_lbl = _EFFORT_SUFFIX_RE.sub("", raw_lbl).strip() if eff else raw_lbl
        slug = _CURSOR_SLUG_MAP.get(norm_model_slug(base_lbl), norm_model_slug(base_lbl))
        slot = by_base.setdefault(slug, {"key": slug, "label": base_lbl, "runs": []})
        slot["runs"].append({"effort": eff, "is_default": False, "score": scr, "cost": cst, "tokens": None, "steps": None})
    return list(by_base.values())


def fetch_cursor_evals_json(timeout: int = 20) -> str | None:
    """Fetch CursorBench 4.0 HTML + immutable JS dataset and return normalized JSON string."""
    body = fetch_url(CURSOR_EVALS_URL, timeout=timeout)
    if not body:
        return None
    html_txt = _decode_body(body)
    entries: list[dict] = []
    for ch in dict.fromkeys(re.findall(r"/marketing-static/_next/static/immutable/chunks/[^\"']+\.js", html_txt)):
        js_body = fetch_url("https://cursor.com" + ch, timeout=timeout)
        if not js_body:
            continue
        js_txt = _decode_body(js_body)
        if "gemini-4-carbon" in js_txt or "avgSteps:" in js_txt:
            entries = _extract_cursor_js_entries(js_txt)
            if entries:
                break
    if not entries:
        entries = _extract_cursor_aria_entries(html_txt)
    return json.dumps({"source": "cursorbench-4.0", "entries": entries}, indent=2) if entries else None


def _cursor_full_label(base_slug: str, label: str) -> str:
    if base_slug.startswith("claude-") and not label.lower().startswith("claude"):
        return f"Claude {label}"
    return label


def _cursor_run_record(base_slug: str, label: str, run: dict) -> tuple[str, dict] | None:
    score = _safe_float(run.get("score"))
    if score is None:
        return None
    eff = normalize_effort(run.get("effort"))
    vslug = f"{base_slug}-{eff}" if eff else base_slug
    disp_base = _cursor_full_label(base_slug, label)
    disp_eff = f" ({EFFORT_DISPLAY[eff]})" if eff else ""
    return vslug, {
        "slug": vslug,
        "base_slug": base_slug,
        "name": f"{disp_base}{disp_eff}",
        "effort": eff,
        "is_default_effort": bool(run.get("is_default")),
        "is_fallback": False,
        "cursor_score": round(score, 2),
        "cursor_cost": _safe_float(run.get("cost")),
        "cursor_tokens": _safe_int(run.get("tokens")),
        "cursor_steps": _safe_float(run.get("steps")),
    }


def _cursor_entries_from_payload(payload) -> list[dict]:
    if isinstance(payload, dict):
        return payload.get("entries") or []
    if not isinstance(payload, str):
        return []
    txt = payload.strip()
    return (_decode_json_dict(txt).get("entries") or []) if txt.startswith("{") else _extract_cursor_aria_entries(txt)


def _ingest_cursor_item(out: dict[str, dict], item: dict) -> None:
    raw_k = str(item.get("key") or "")
    base_slug = _CURSOR_SLUG_MAP.get(raw_k, norm_model_slug(raw_k))
    label = str(item.get("label") or base_slug)
    for run in item.get("runs") or []:
        built = _cursor_run_record(base_slug, label, run)
        if built:
            _store_with_base_fallback(out, built[0], base_slug, built[1], "cursor_score")


def parse_cursor_evals(payload, verbose: bool = False) -> dict[str, dict]:
    """Parse CursorBench 4.0 JSON snapshot (or raw HTML fallback) with distinct efforts."""
    out: dict[str, dict] = {}
    for item in _cursor_entries_from_payload(payload):
        if isinstance(item, dict):
            _ingest_cursor_item(out, item)
    if verbose:
        print(f"  CursorBench: parsed {len(out)} model/effort keys")
    return out


def _read_parsed_snapshots(raw_dir: pathlib.Path, glob_pat: str, parser, min_keys: int, verbose: bool) -> dict[str, dict]:
    for snap in sorted(raw_dir.glob(glob_pat), reverse=True):
        try:
            parsed = parser(snap.read_text(encoding="utf-8", errors="ignore"), verbose=verbose)
        except Exception as exc:
            print(f"  WARN snapshot parse failed ({snap.name}): {exc}", file=sys.stderr)
            continue
        if len(parsed) >= min_keys:
            return parsed
        print(f"  WARN snapshot below min_keys={min_keys}: {snap.name} ({len(parsed)})", file=sys.stderr)
    return {}


def load_or_fetch_frontiercode(raw_dir: pathlib.Path, fetch: bool = False, write: bool = True, verbose: bool = False) -> dict[str, dict]:
    """Load cached Cognition FrontierCode 2.0 JSON or fetch live with fail-closed validation."""
    if fetch:
        body = fetch_url(FRONTIERCODE_URL, timeout=20)
        txt = _decode_body(body) if body else ""
        parsed = parse_frontiercode(txt, verbose=verbose) if txt else {}
        if len(parsed) >= 20:
            if write:
                atomic_write_text(raw_dir / f"frontiercode_{dt.datetime.now(dt.UTC).strftime('%Y%m%d')}.json", txt)
            return parsed
        print("  WARN FrontierCode fetch failed/under-threshold, using cache", file=sys.stderr)
    return _read_parsed_snapshots(raw_dir, "frontiercode_*.json", parse_frontiercode, 20, verbose)


def load_or_fetch_frontierswe(raw_dir: pathlib.Path, fetch: bool = False, write: bool = True, verbose: bool = False) -> dict[str, dict]:
    """Load cached FrontierSWE HTML or fetch live with fail-closed validation."""
    if fetch:
        body = fetch_url(FRONTIERSWE_URL, timeout=20)
        txt = _decode_body(body) if body else ""
        parsed = parse_frontierswe(txt, verbose=verbose) if txt else {}
        if len(parsed) >= 15:
            if write:
                atomic_write_text(raw_dir / f"frontierswe_{dt.datetime.now(dt.UTC).strftime('%Y%m%d')}.html", txt)
            return parsed
        print("  WARN FrontierSWE fetch failed/under-threshold, using cache", file=sys.stderr)
    return _read_parsed_snapshots(raw_dir, "frontierswe_*.html", parse_frontierswe, 15, verbose)


def load_or_fetch_cursor_evals(raw_dir: pathlib.Path, fetch: bool = False, write: bool = True, verbose: bool = False) -> dict[str, dict]:
    """Load cached CursorBench JSON or fetch live with fail-closed validation."""
    if fetch:
        txt = fetch_cursor_evals_json(timeout=20) or ""
        parsed = parse_cursor_evals(txt, verbose=verbose) if txt else {}
        if len(parsed) >= 15:
            if write:
                atomic_write_text(raw_dir / f"cursor_evals_{dt.datetime.now(dt.UTC).strftime('%Y%m%d')}.json", txt)
            return parsed
        print("  WARN CursorBench fetch failed/under-threshold, using cache", file=sys.stderr)
    return _read_parsed_snapshots(raw_dir, "cursor_evals_*.json", parse_cursor_evals, 15, verbose)


def _geom_mean_costs(m: dict, bm: dict) -> float | None:
    costs = [
        float(v) for v in (
            bm.get("cursor_cost"), bm.get("fc2_cost"), bm.get("aa_cost_per_task"), m.get("vals_cost_per_test")
        )
        if _is_num(v) and float(v) > 0
    ]
    return round(math.exp(sum(math.log(c) for c in costs) / len(costs)), 2) if costs else None


def _fswe_code_leg(bm: dict) -> float | None:
    impl, perf = _safe_float(bm.get("fswe_impl")), _safe_float(bm.get("fswe_perf"))
    if impl is not None and perf is not None:
        return 0.60 * impl + 0.40 * perf
    return impl if impl is not None else _safe_float(bm.get("fswe_overall"))


def _neg_log10(val) -> float | None:
    return -math.log10(max(0.0001, float(val))) if _is_num(val) else None


def _pos_log10(val) -> float | None:
    return math.log10(max(1.0, float(val))) if _is_num(val) else None


def _z_against_non_mirrors(m_list: list[dict], values: list) -> list[float | None]:
    """Z-score all rows (including mirrors) against the non-mirror cohort mean and stddev."""
    cohort = [float(v) for m, v in zip(m_list, values) if not m.get("signal_mirror_of") and _is_num(v)]
    if len(cohort) < 2:
        return [0.0 if _is_num(v) else None for v in values]
    mean_v = statistics.mean(cohort)
    std_v = statistics.pstdev(cohort) or 1.0
    return [(float(v) - mean_v) / std_v if _is_num(v) else None for v in values]


_AXIS_EXTRACTORS: tuple[tuple[str, object], ...] = (
    ("aa_hle", lambda m, bm, lb: bm.get("aa_hle")),
    ("aa_critpt", lambda m, bm, lb: bm.get("aa_critpt")),
    ("aa_intel", lambda m, bm, lb: _first_num(m.get("aa_live_quality"), bm.get("aa_quality"))),
    ("lb_overall", lambda m, bm, lb: _safe_float(lb.get("overall"))),
    ("cursor", lambda m, bm, lb: bm.get("cursor_score")),
    ("fc2", lambda m, bm, lb: _first_num(bm.get("fc2_score"), bm.get("aa_fc2"))),
    ("fswe_code", lambda m, bm, lb: _fswe_code_leg(bm)),
    ("aa_tb4", lambda m, bm, lb: _first_num(bm.get("aa_tb4"), bm.get("aa_coding"))),
    ("vals_code", lambda m, bm, lb: _first_num(m.get("vals_coding_blend"), m.get("vals_coding"))),
    ("lb_agentic", lambda m, bm, lb: _safe_float(lb.get("agentic_coding"))),
    ("lm_coding", lambda m, bm, lb: bm.get("lm_coding")),
    ("lm_elo", lambda m, bm, lb: bm.get("lm_elo")),
    ("aa_ifbench", lambda m, bm, lb: bm.get("aa_ifbench")),
    ("aa_non_halluc", lambda m, bm, lb: bm.get("aa_non_halluc")),
    ("aa_lcr", lambda m, bm, lb: bm.get("aa_lcr")),
    ("fswe_res", lambda m, bm, lb: bm.get("fswe_research")),
    ("aa_scicode", lambda m, bm, lb: bm.get("aa_scicode")),
    ("aa_gpqa", lambda m, bm, lb: bm.get("aa_gpqa")),
    ("emp_cost", lambda m, bm, lb: _neg_log10(m.get("empirical_cost"))),
    ("speed", lambda m, bm, lb: _pos_log10(bm.get("speed_tps"))),
    ("blended", lambda m, bm, lb: _neg_log10(m.get("blended_price"))),
)


def _build_axis_z_table(m_list: list[dict]) -> dict[str, list[float | None]]:
    triples = [(m, _as_dict(m.get("base_metrics")), _as_dict(m.get("livebench"))) for m in m_list]
    return {
        key: _z_against_non_mirrors(m_list, [fn(m, bm, lb) for m, bm, lb in triples])
        for key, fn in _AXIS_EXTRACTORS
    }


def _compute_row_axes_z(zt: dict[str, list[float | None]], i: int) -> dict[str, float | None]:
    return {
        "reasoning": shrunk_weighted_z([
            (0.30, zt["aa_hle"][i]), (0.25, zt["aa_critpt"][i]), (0.25, zt["aa_intel"][i]), (0.20, zt["lb_overall"][i]),
        ]),
        "coding": shrunk_weighted_z([
            (0.22, zt["cursor"][i]), (0.22, zt["fc2"][i]), (0.18, zt["fswe_code"][i]),
            (0.16, zt["aa_tb4"][i]), (0.12, zt["vals_code"][i]), (0.10, zt["lb_agentic"][i]),
        ]),
        "design": shrunk_weighted_z([
            (0.45, zt["lm_coding"][i]), (0.35, zt["lm_elo"][i]), (0.20, zt["aa_ifbench"][i]),
        ]),
        "research": shrunk_weighted_z([
            (0.25, zt["aa_non_halluc"][i]), (0.20, zt["aa_lcr"][i]), (0.20, zt["fswe_res"][i]),
            (0.20, zt["aa_scicode"][i]), (0.15, zt["aa_gpqa"][i]),
        ]),
        "economics": shrunk_weighted_z([
            (0.50, zt["emp_cost"][i]), (0.30, zt["speed"][i]), (0.20, zt["blended"][i]),
        ]),
    }


def _compute_row_roles(m: dict, az: dict[str, float | None]) -> dict[str, float | None]:
    cap_count = sum(az[k] is not None for k in ("reasoning", "coding", "design", "research"))
    s_arc = scale_axis_score(
        shrunk_weighted_z([(0.45, az["reasoning"]), (0.30, az["coding"]), (0.25, az["research"])], lam=0.10)
    ) if cap_count >= 2 else None
    s_dev = scale_axis_score(
        shrunk_weighted_z([(0.55, az["coding"]), (0.20, az["reasoning"]), (0.25, az["economics"])], lam=0.10)
    ) if az["coding"] is not None else None
    s_des = scale_axis_score(
        shrunk_weighted_z([(0.65, az["design"]), (0.20, az["coding"]), (0.15, az["economics"])], lam=0.10)
    ) if az["design"] is not None else None
    s_res = scale_axis_score(
        shrunk_weighted_z([(0.55, az["research"]), (0.30, az["reasoning"]), (0.15, az["coding"])], lam=0.10)
    ) if az["research"] is not None else None
    ctx = _safe_int(m.get("context_length"))
    if s_res is not None and ctx is not None and ctx < 200_000:
        s_res = round(max(40.0, s_res - 10.0), 1)
    return {"architecture": s_arc, "software_dev": s_dev, "design": s_des, "research": s_res}


def _populate_price_and_emp_cost(m: dict) -> None:
    bm = m.get("base_metrics") or {}
    pin, pout = _safe_float(m.get("price_in")), _safe_float(m.get("price_out"))
    blended = round((0.80 * pin) + (0.20 * pout), 2) if (pin is not None and pout is not None) else None
    emp = _geom_mean_costs(m, bm)
    eff_cost = emp if emp is not None else blended
    m["blended_price"] = blended
    m["empirical_cost"] = emp
    m["effective_cost"] = eff_cost


def _apply_five_axis_row(m: dict, az: dict[str, float | None]) -> None:
    cz = shrunk_weighted_z([
        (0.30, az["reasoning"]), (0.30, az["coding"]), (0.20, az["research"]), (0.20, az["design"]),
    ])
    if cz is None:
        for k in ("composite_score", "capability_q", "avi_score", "axes", "roles", "best_role"):
            m[k] = None
        m["unmatched"] = True
        return
    q_score = scale_axis_score(cz)
    axes_scaled = {k: scale_axis_score(v) for k, v in az.items()}
    roles = _compute_row_roles(m, az)
    eff = m.get("effective_cost")
    m["composite_score"] = q_score
    m["capability_q"] = q_score
    m["axes"] = axes_scaled
    m["roles"] = roles
    m["avi_score"] = compute_avi(q_score, eff) if (_is_num(eff) and float(eff) > 0.0) else None
    cov = extract_capability_pillars(m)["coverage_count"]
    m["best_role"] = _best_role_from_map(roles, q_score, cov)


def score_five_axes_and_roles(models_list: list[dict]) -> None:
    """Authoritative 5-axis + 4-role shrunk z-score engine over the full model cohort."""
    for m in models_list:
        _populate_price_and_emp_cost(m)
    zt = _build_axis_z_table(models_list)
    for i, m in enumerate(models_list):
        _apply_five_axis_row(m, _compute_row_axes_z(zt, i))
