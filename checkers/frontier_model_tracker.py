#!/usr/bin/env python3
"""
frontier_model_tracker.py — OpenAI, Claude (Anthropic), and Gemini (Google) Model Tracker

Cross-references master benchmark evaluations (LiveBench, Artificial Analysis, Arena ELO)
with live token pricing and context allowances from OpenRouter/provider catalogs.

Outputs:
  - docs/data/frontier_models.json
"""
import argparse
import datetime as dt
import glob
import json
import os
import pathlib
import re
import sys

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

import benchmark_common as bc  # noqa: E402

TRACKED_PROVIDERS = {
    "claude": {
        "title": "Anthropic (Claude)",
        "icon": "🧠",
        "pattern": re.compile(r"\bclaude\b"),
        "exclude": re.compile(r"^$"),
    },
    "openai": {
        "title": "OpenAI (GPT & Reasoning)",
        "icon": "⚡",
        "pattern": re.compile(r"\b(gpt|o1|o3|o4|openai)\b"),
        "exclude": re.compile(r"\bgpt-oss\b"),
    },
    "gemini": {
        "title": "Google (Gemini)",
        "icon": "💎",
        "pattern": re.compile(r"\bgemini\b"),
        "exclude": re.compile(r"^$"),
    },
}


def _or_pricing_record(item: dict) -> dict | None:
    """Convert one OpenRouter catalog entry into a pricing record."""
    mid = item.get("id", "")
    if not mid:
        return None
    p = item.get("pricing") or {}
    pin_v = bc._safe_float(p.get("prompt"))
    pout_v = bc._safe_float(p.get("completion"))
    pcache_v = bc._safe_float(p.get("input_cache_read"))
    return {
        "id": mid,
        "name": item.get("name") or mid,
        "price_in": pin_v * 1_000_000 if pin_v is not None else None,
        "price_out": pout_v * 1_000_000 if pout_v is not None else None,
        "price_cache": pcache_v * 1_000_000 if pcache_v is not None else 0.0,
        "context_length": item.get("context_length"),
    }


def _index_pricing_item(item: dict, pricing_map: dict[str, dict]) -> None:
    """Register canonical keys for one OpenRouter model entry into `pricing_map`."""
    if not (rec := _or_pricing_record(item)):
        return
    mid = rec["id"]
    pricing_map[mid.lower()] = rec
    if ":" in mid:
        return
    bare = mid.split("/", 1)[-1].lower()
    for key in (bare, bc.norm_id(bare), bc.norm_model_slug(bare), bc.norm_model_slug(mid)):
        if key:
            pricing_map.setdefault(key, rec)
    if item.get("name"):
        pricing_map.setdefault(bc.norm_id(item["name"]), rec)


def load_openrouter_pricing_map(raw_dir: pathlib.Path = RAW) -> dict:
    """Load latest OpenRouter catalog snapshot; keep `:variant` SKUs from claiming bare slugs."""
    matches = sorted(glob.glob(str(raw_dir / "openrouter_models_*.json")))
    if not matches:
        return {}
    try:
        data = json.loads(pathlib.Path(matches[-1]).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    items = data.get("data", data if isinstance(data, list) else [])
    pricing_map: dict[str, dict] = {}
    for item in sorted(items, key=lambda x: ":" in (x.get("id") or "")):
        _index_pricing_item(item, pricing_map)
    return pricing_map


def _pricing_candidates(display_name: str) -> list[str]:
    """Generate ordered normalized pricing keys from a benchmark display name."""
    clean = re.sub(r"\(.*?\)", "", display_name).strip()
    slug = bc.norm_id(clean)
    norm_slug = bc.norm_model_slug(clean)
    slug_base = re.sub(r"-(?:\d{8}|\d+k)$", "", slug)
    stripped = bc.strip_tier_tokens(clean)
    dash_base = re.sub(r"-(max|high|medium|low|xhigh|thinking|reasoning|effort|exp)$", "", slug_base)
    cands = [slug, bc.norm_id(display_name), slug_base, dash_base, norm_slug, stripped]
    for pfx in ("anthropic/", "openai/", "google/"):
        cands.extend((f"{pfx}{slug}", f"{pfx}{dash_base}", f"{pfx}{stripped}"))
    return [c for c in cands if c]


def find_model_pricing(display_name: str, pricing_map: dict) -> dict | None:
    """Match a benchmark model display name to OpenRouter pricing records."""
    if not display_name or not pricing_map:
        return None
    for key in _pricing_candidates(display_name):
        if key in pricing_map:
            return pricing_map[key]
    return None


def _extract_comp_score(m: dict, lb: float | None, aa: float | None) -> float:
    """Read scalar capability_q/composite_score from benchmarks.json (dict-safe)."""
    raw_c = m.get("composite_score")
    if isinstance(raw_c, dict):
        q = bc._first_num(m.get("capability_q"), raw_c.get("score"))
    else:
        q = bc._first_num(m.get("capability_q"), raw_c)
    if q is not None:
        return q
    if lb is not None:
        return lb
    return (aa * 1.5) if aa is not None else 0.0


def _build_frontier_entry(m: dict, pkey: str, pcfg: dict, pricing_map: dict) -> dict:
    """Normalize one tracked frontier model record with pricing and benchmarks."""
    disp = m.get("display") or m.get("name") or ""
    pr = find_model_pricing(disp, pricing_map) or {}
    price_in = pr["price_in"] if pr else bc._safe_float(m.get("price_in"))
    price_out = pr["price_out"] if pr else bc._safe_float(m.get("price_out"))
    price_cache = pr.get("price_cache")
    ctx = pr.get("context_length") or m.get("context_length")

    lb = (m.get("livebench") or {}).get("overall")
    aa = m.get("aa_live_quality")
    elo = (m.get("base_metrics") or {}).get("lm_elo")

    return {
        "model_id": pr["id"] if pr else bc.norm_id(disp),
        "display": disp,
        "provider": pkey,
        "provider_title": pcfg["title"],
        "pricing": {
            "unit": "USD / 1M tokens",
            "input_per_1m": price_in,
            "output_per_1m": price_out,
            "cache_read_per_1m": price_cache,
            "price_in_1m": price_in,
            "price_out_1m": price_out,
            "price_cache_1m": price_cache,
            "context_length": ctx,
        },
        "benchmarks": {
            "livebench_overall": lb,
            "aa_quality": aa,
            "arena_elo": elo,
            "vals_overall": m.get("vals_overall"),
            "composite_score": _extract_comp_score(m, lb, aa),
        },
    }


def _collect_provider_models(catalog_models: list[dict], pkey: str, pcfg: dict, pricing_map: dict) -> dict:
    """Filter, enrich, and rank frontier models belonging to one tracked provider."""
    pat, excl = pcfg["pattern"], pcfg["exclude"]
    matched = []
    for m in catalog_models:
        disp = m.get("display") or m.get("name") or ""
        dl = disp.lower()
        if pat.search(dl) and not excl.search(dl):
            matched.append(_build_frontier_entry(m, pkey, pcfg, pricing_map))
    matched.sort(
        key=lambda x: (
            x["pricing"]["price_in_1m"] is not None,
            x["benchmarks"]["composite_score"] or 0.0,
            x["benchmarks"]["livebench_overall"] or 0.0,
            x["benchmarks"]["aa_quality"] or 0.0,
        ),
        reverse=True,
    )
    return {
        "title": pcfg["title"],
        "icon": pcfg["icon"],
        "total_tracked": len(matched),
        "with_pricing": sum(1 for m in matched if m["pricing"]["price_in_1m"] is not None),
        "models": matched,
    }


def extract_frontier_models(bench_path: pathlib.Path = DATA / "benchmarks.json", raw_dir: pathlib.Path = RAW) -> dict:
    """Extract, match, and rank OpenAI, Claude, and Gemini models with benchmarks and pricing."""
    if not bench_path.exists():
        return {}
    try:
        bench_data = json.loads(bench_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    catalog_models = bench_data.get("models", [])
    pricing_map = load_openrouter_pricing_map(raw_dir)
    providers = {
        pkey: _collect_provider_models(catalog_models, pkey, pcfg, pricing_map)
        for pkey, pcfg in TRACKED_PROVIDERS.items()
    }
    return {
        "pricing_standard": "USD per 1M tokens ($/1M)",
        "unit": "USD / 1M tokens",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "providers": providers,
    }


def save_frontier_models(payload: dict, out_path: pathlib.Path = DATA / "frontier_models.json") -> pathlib.Path:
    """Save frontier model tracking payload to json file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bc.atomic_write_text(out_path, json.dumps(payload, indent=2))
    return out_path


def _fmt_price(v: float | None) -> str:
    return f"${v:.2f}" if v is not None else "—"


def _format_cli_row(m: dict) -> str:
    """Format one model row for frontier CLI radar."""
    pr, bm = m.get("pricing", {}), m.get("benchmarks", {})
    pin = _fmt_price(pr.get("price_in_1m"))
    pout = _fmt_price(pr.get("price_out_1m"))
    pcache = _fmt_price(pr.get("price_cache_1m"))
    ctx = f"{pr['context_length'] // 1000}k" if pr.get("context_length") else "—"
    lb = f"{bm['livebench_overall']:.1f}" if bm.get("livebench_overall") is not None else "—"
    aa = f"{bm['aa_quality']:.1f}" if bm.get("aa_quality") is not None else "—"
    elo = f"{bm['arena_elo']:.0f}" if bm.get("arena_elo") is not None else "—"
    return f" {m.get('display', '')[:36]:<38} {pin:<12} {pout:<12} {pcache:<10} {ctx:<8} {lb:<8} {aa:<8} {elo:<6}"


def render_cli_table(payload: dict) -> str:
    """Format a clean terminal view of tracked frontier models and prices."""
    color = not os.environ.get("NO_COLOR") and sys.stdout.isatty()
    b, dim, rst = (bc.C_BOLD, bc.C_DIM, bc.C_RESET) if color else ("", "", "")
    lines = [
        f"{b}FRONTIER MODEL BENCHMARK & PRICING RADAR (OpenAI, Claude, Gemini){rst}",
        f"{dim}Generated: {payload.get('generated_at')} | Standard units: $/1M tokens{rst}",
        "=" * 105,
    ]
    for pkey, pdata in payload.get("providers", {}).items():
        title = f"{pdata.get('icon', '')} {pdata.get('title', pkey)} ({pdata.get('total_tracked', 0)} tracked, {pdata.get('with_pricing', 0)} priced)"
        lines.extend([
            f"\n{b}{title}{rst}",
            "-" * 105,
            f" {'Model':<38} {'Input/1M':<12} {'Output/1M':<12} {'Cache/1M':<10} {'Ctx':<8} {'LB':<8} {'AA':<8} {'ELO':<6}",
            "-" * 105,
            *(_format_cli_row(m) for m in pdata.get("models", [])[:10]),
            "-" * 105,
        ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Track benchmarks and pricing for OpenAI, Claude, and Gemini models.")
    parser.add_argument("--json", action="store_true", default=True, help="Save docs/data/frontier_models.json (default unless --check)")
    parser.add_argument("--check", action="store_true", help="Print table only, do not write files")
    args = parser.parse_args()

    payload = extract_frontier_models()
    if not payload:
        print("WARN: No model data available to extract frontier tracking", file=sys.stderr)
        return 1

    print(render_cli_table(payload))
    if not args.check:
        out_p = save_frontier_models(payload)
        print(f"\nSaved frontier models database -> {out_p.relative_to(ROOT) if out_p.is_relative_to(ROOT) else out_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
