#!/usr/bin/env python3
"""
frontier_model_tracker.py — OpenAI, Claude (Anthropic), and Gemini (Google) Model Tracker

Cross-references master benchmark evaluations (LiveBench, Artificial Analysis, Arena ELO)
with live token pricing and context allowances from OpenRouter/provider catalogs.

Outputs:
  - docs/data/frontier_models.json
  - docs/reports/frontier_models.html (optional)
"""
import argparse
import datetime as dt
import glob
import json
import os
import pathlib
import re
import shutil
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
OUT = ROOT / "docs" / "reports"

import benchmark_common as bc

TRACKED_PROVIDERS = {
    "claude": {
        "title": "Anthropic (Claude)",
        "icon": "🧠",
        "keywords": ["claude"],
        "prefixes": ["anthropic/"],
    },
    "openai": {
        "title": "OpenAI (GPT & Reasoning)",
        "icon": "⚡",
        "keywords": ["gpt", "o1", "o3", "openai"],
        "prefixes": ["openai/", "~openai/"],
    },
    "gemini": {
        "title": "Google (Gemini)",
        "icon": "💎",
        "keywords": ["gemini"],
        "prefixes": ["google/"],
    },
}


def load_openrouter_pricing_map(raw_dir: pathlib.Path = RAW) -> dict:
    """Load latest OpenRouter catalog snapshot and index by normalized slug and bare id."""
    matches = sorted(glob.glob(str(raw_dir / "openrouter_models_*.json")))
    if not matches:
        return {}
    latest = pathlib.Path(matches[-1])
    try:
        data = json.loads(latest.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}

    items = data.get("data", data if isinstance(data, list) else [])
    pricing_map = {}
    for item in items:
        mid = item.get("id", "")
        if not mid:
            continue
        p = item.get("pricing", {})
        pin = float(p.get("prompt", 0) or 0) * 1_000_000
        pout = float(p.get("completion", 0) or 0) * 1_000_000
        pcache = float(p.get("input_cache_read", 0) or 0) * 1_000_000
        rec = {
            "id": mid,
            "name": item.get("name") or mid,
            "price_in": pin,
            "price_out": pout,
            "price_cache": pcache,
            "context_length": item.get("context_length"),
        }
        pricing_map[mid.lower()] = rec
        bare = mid.split("/", 1)[-1].split(":", 1)[0].lower()
        pricing_map.setdefault(bare, rec)
        pricing_map.setdefault(bc.norm_id(bare), rec)
        if item.get("name"):
            pricing_map.setdefault(bc.norm_id(item["name"]), rec)
    return pricing_map


def find_model_pricing(display_name: str, pricing_map: dict) -> dict | None:
    """Match a benchmark model display name to OpenRouter pricing records."""
    if not display_name or not pricing_map:
        return None

    # 1. Exact or normalized
    clean = re.sub(r"\(.*?\)", "", display_name).strip()
    slug = bc.norm_id(clean)
    if slug in pricing_map:
        return pricing_map[slug]

    full_slug = bc.norm_id(display_name)
    if full_slug in pricing_map:
        return pricing_map[full_slug]

    # 2. Strip trailing tier or effort tokens
    slug_base = re.sub(r"-(max|high|medium|low|xhigh|thinking|reasoning|exp)$", "", slug)
    if slug_base in pricing_map:
        return pricing_map[slug_base]

    # 3. Provider-prefixed attempts
    for pfx in ("anthropic/", "openai/", "google/"):
        cand = f"{pfx}{slug}"
        if cand in pricing_map:
            return pricing_map[cand]
        cand_base = f"{pfx}{slug_base}"
        if cand_base in pricing_map:
            return pricing_map[cand_base]

    return None


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

    result_providers = {}

    for pkey, pcfg in TRACKED_PROVIDERS.items():
        matched_models = []
        for m in catalog_models:
            disp = m.get("display") or m.get("name") or ""
            disp_lower = disp.lower()
            if not any(kw in disp_lower for kw in pcfg["keywords"]):
                continue

            pr = find_model_pricing(disp, pricing_map)
            price_in = pr.get("price_in") if pr else None
            price_out = pr.get("price_out") if pr else None
            price_cache = pr.get("price_cache") if pr else None
            ctx = pr.get("context_length") if pr else None

            lb = None
            if isinstance(m.get("livebench"), dict):
                lb = m.get("livebench", {}).get("overall")

            aa = m.get("aa_live_quality")
            elo = None
            if isinstance(m.get("base_metrics"), dict):
                elo = m.get("base_metrics", {}).get("lm_elo")

            comp_score = 0.0
            if isinstance(m.get("composite_score"), dict):
                comp_score = m.get("composite_score", {}).get("score", 0.0) or 0.0
            elif lb:
                comp_score = lb
            elif aa:
                comp_score = aa * 1.5

            matched_models.append({
                "model_id": pr.get("id") if pr else bc.norm_id(disp),
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
                    "composite_score": comp_score,
                },
            })

        # Sort models: those with valid pricing/benchmarks first, then by composite / livebench / aa
        matched_models.sort(
            key=lambda x: (
                x["pricing"]["price_in_1m"] is not None,
                x["benchmarks"]["composite_score"] or 0.0,
                x["benchmarks"]["livebench_overall"] or 0.0,
                x["benchmarks"]["aa_quality"] or 0.0,
            ),
            reverse=True,
        )

        result_providers[pkey] = {
            "title": pcfg["title"],
            "icon": pcfg["icon"],
            "total_tracked": len(matched_models),
            "with_pricing": sum(1 for m in matched_models if m["pricing"]["price_in_1m"] is not None),
            "models": matched_models,
        }

    return {
        "pricing_standard": "USD per 1M tokens ($/1M)",
        "unit": "USD / 1M tokens",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "providers": result_providers,
    }


def save_frontier_models(payload: dict, out_path: pathlib.Path = DATA / "frontier_models.json") -> pathlib.Path:
    """Save frontier model tracking payload to json file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bc.atomic_write_text(out_path, json.dumps(payload, indent=2))
    return out_path


def render_cli_table(payload: dict) -> str:
    """Format a clean terminal view of tracked frontier models and prices."""
    lines = [
        f"{bc.C_BOLD}FRONTIER MODEL BENCHMARK & PRICING RADAR (OpenAI, Claude, Gemini){bc.C_RESET}",
        f"{bc.C_DIM}Generated: {payload.get('generated_at')} | Standard units: $/1M tokens{bc.C_RESET}",
        "=" * 105,
    ]

    for pkey, pdata in payload.get("providers", {}).items():
        title = f"{pdata.get('icon', '')} {pdata.get('title', pkey)} ({pdata.get('total_tracked', 0)} tracked, {pdata.get('with_pricing', 0)} priced)"
        lines.append(f"\n{bc.C_BOLD}{title}{bc.C_RESET}")
        lines.append("-" * 105)
        lines.append(f" {'Model':<38} {'Input/1M':<12} {'Output/1M':<12} {'Cache/1M':<10} {'Ctx':<8} {'LB':<8} {'AA':<8} {'ELO':<6}")
        lines.append("-" * 105)
        for m in pdata.get("models", [])[:10]:
            disp = m.get("display")[:36]
            pr = m.get("pricing", {})
            bm = m.get("benchmarks", {})
            pin = f"${pr.get('price_in_1m'):.2f}" if pr.get("price_in_1m") is not None else "—"
            pout = f"${pr.get('price_out_1m'):.2f}" if pr.get("price_out_1m") is not None else "—"
            pcache = f"${pr.get('price_cache_1m'):.2f}" if pr.get("price_cache_1m") is not None else "—"
            ctx_val = pr.get("context_length")
            ctx = f"{ctx_val//1000}k" if ctx_val else "—"
            lb = f"{bm.get('livebench_overall'):.1f}" if bm.get("livebench_overall") is not None else "—"
            aa = f"{bm.get('aa_quality'):.1f}" if bm.get("aa_quality") is not None else "—"
            elo = f"{bm.get('arena_elo'):.0f}" if bm.get("arena_elo") is not None else "—"

            lines.append(f" {disp:<38} {pin:<12} {pout:<12} {pcache:<10} {ctx:<8} {lb:<8} {aa:<8} {elo:<6}")
        lines.append("-" * 105)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Track benchmarks and pricing for OpenAI, Claude, and Gemini models.")
    parser.add_argument("--json", action="store_true", default=True, help="Save to docs/data/frontier_models.json")
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
