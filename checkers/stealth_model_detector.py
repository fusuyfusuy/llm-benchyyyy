#!/usr/bin/env python3
"""
stealth_model_detector.py — OpenRouter stealth models (stealth/ namespace) ranked by composite intelligence

Reads the OpenRouter model catalog from the raw cache by default
(--fetch is the only network path) and keeps only models in `stealth/`.
"""
import argparse
import datetime as dt
import html
import json
import os
import pathlib
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

import benchmark_common as bc  # noqa: E402
from benchmark_common import (  # noqa: E402
    AA_URL,
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_MAGENTA,
    C_WHITE,
    C_YELLOW,
    HTML_CSS_COMMON,
    HTML_SORT_SCRIPT,
    LMARENA_URL,
    OPENROUTER_API,
    _safe_float,
    _safe_int,
    base_id,
    comp_key,
    compute_meanfill_composite,
    is_stealth_model,
    medal_badge,
    score_color_q,
)

STEALTH_PREFIX = "stealth/"
_HEADERS_SLIM = [
    ("Rank", 4, "^"), ("Model", 24, "<"), ("Q(Cap)", 6, ">"), ("Comp", 6, ">"),
    ("Coverage", 8, "^"), ("Ctx", 5, ">"), ("Price", 12, ">"), ("Created", 10, "^"),
]
_HEADERS_FULL = [
    ("Rank", 4, "^"), ("Model", 28, "<"), ("Q(Cap)", 6, ">"), ("AA Intel", 8, ">"),
    ("LM ELO", 7, ">"), ("Comp", 6, ">"), ("Coverage", 8, "^"), ("Ctx", 5, ">"),
    ("Modality", 12, "<"), ("Price", 12, ">"), ("Created", 10, "^"),
]


def pick_latest_raw(name_part: str) -> pathlib.Path | None:
    """Newest snapshot in docs/data/raw/ whose name contains name_part, or None."""
    return bc.pick_latest_raw(RAW, name_part)


def created_date(rec: dict) -> str:
    """OpenRouter 'created' epoch -> ISO date string, or '—'."""
    c = rec.get("created")
    try:
        return dt.datetime.fromtimestamp(int(c), tz=dt.UTC).date().isoformat()
    except Exception:
        return "—"


def _fmt_num(val, spec: str) -> str:
    return f"{val:{spec}}" if bc._is_num(val) else "—"


def _render_html_row(r: dict, top_id: str | None) -> str:
    b = r["benchmarks"]
    ctx_val = b.get("openrouter_context")
    ctx = f"{int(ctx_val) // 1000}k" if bc._is_num(ctx_val) else "—"
    lm_rk = b.get("lmarena_rank")
    rk = f"#{lm_rk}" if isinstance(lm_rk, int) else "—"
    cls = " class='top-row'" if r["model_id"] == top_id else ""
    return (
        f"<tr{cls}>"
        f'<td class="m">{html.escape(r["display"])} <span class="badge badge-stl">STEALTH</span></td>'
        f'<td>{html.escape(r["provider"])}</td>'
        f'<td class="n" style="font-weight:700; color:#3fb950;">{_fmt_num(b.get("capability_q"), ".1f")}</td>'
        f'<td class="n">{_fmt_num(b.get("aa_intelligence"), ".1f")}<span class="mid">{html.escape(b.get("aa_slug") or "")}</span></td>'
        f'<td class="n">{_fmt_num(b.get("lmarena_elo"), ".0f")}</td><td class="n">{rk}</td>'
        f'<td class="n" style="font-weight:700; color:#58a6ff;">{_fmt_num(r.get("composite"), ".2f")}</td>'
        f'<td>{"·".join(r.get("coverage", ["—"]))}</td><td class="n">{ctx}</td>'
        f'<td>{html.escape(r.get("modality", "—"))}</td>'
        f"<td class='n'>{html.escape(r.get('price_str', '—'))}</td>"
        f"<td class='n'>{html.escape(r.get('created', '—'))}</td></tr>"
    )


def render_html(rows, n_aa, n_lm):
    title = f"OpenRouter Stealth Models — Composite Intelligence ({dt.date.today().isoformat()})"
    top_id = rows[0]["model_id"] if rows and rows[0].get("composite") is not None else None
    trs = [_render_html_row(r, top_id) for r in rows]
    top_disp = html.escape(rows[0]["display"]) if top_id else "none"
    now_str = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    body = f"""
<div class="wrap">
<h1>{html.escape(title)}</h1>
<p class="sub">Models in OpenRouter's <code>stealth/</code> namespace (anonymous/undisclosed models being tested publicly, e.g. <code>stealth/ox-alpha</code>), ranked by normalized composite intelligence = mean of z-scored <a href="https://artificialanalysis.ai/leaderboards/models">Artificial Analysis</a> Intelligence Index and <a href="https://arena.ai/leaderboard/text">Arena.ai</a> ELO. <b>{len(rows)}</b> stealth models · <b>{n_aa}</b> on AA · <b>{n_lm}</b> on Arena · Generated {now_str}</p>
<div class="card"><b>How to read:</b> <span class="badge badge-gold">TOP LEADER</span> = highest composite intelligence · <b>Q(Cap)</b> = Composite Capability (40–99.9). Stealth identity means provider/author is undisclosed on OpenRouter; AA/LMArena slugs may or may not resolve. Empty table = no stealth models currently listed.</div>
<div class="card">
<table id="tbl">
<thead><tr><th>model</th><th>provider</th><th>Q(Cap)</th><th>AA intel</th><th>LM ELO</th><th>LM rank</th><th>composite</th><th>coverage</th><th>ctx</th><th>modality</th><th>$in/$out</th><th>created</th></tr></thead>
<tbody>{''.join(trs)}</tbody>
</table>
<div class="legend">Click headers to sort. — = not on that leaderboard / unknown.</div>
</div>
<div class="footer"><span class="path">docs/reports/stealth_models.html</span><span class="work">Composite rank of {len(rows)} stealth model(s) ({n_aa} on AA, {n_lm} on LMArena — top: {top_disp}).</span></div>
</div>
{HTML_SORT_SCRIPT}
"""
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{HTML_CSS_COMMON}</style></head><body>{body}</body></html>"


def _cli_row_cells(idx: int, r: dict, meds: dict, color: bool, is_slim: bool) -> list[tuple[str, str, int, str]]:
    rank_str, rank_col = bc.rank_label_and_color(idx + 1)
    b = r["benchmarks"]
    q_val, comp_val = b.get("capability_q"), r.get("composite")
    ctx_val = b.get("openrouter_context")
    ctx_s = f"{int(ctx_val) // 1000}k" if bc._is_num(ctx_val) else "—"
    m_w = 24 if is_slim else 28

    cells: list[tuple[str, str, int, str]] = [
        (rank_str, rank_col, 4, "^"),
        (r["display"][:m_w], C_BOLD + C_MAGENTA, m_w, "<"),
        (_fmt_num(q_val, ".1f") + medal_badge(meds.get("q"), color=color), score_color_q(q_val), 6, ">"),
    ]
    if not is_slim:
        cells.extend([
            (_fmt_num(b.get("aa_intelligence"), ".1f"), C_WHITE, 8, ">"),
            (_fmt_num(b.get("lmarena_elo"), ".0f"), C_WHITE, 7, ">"),
        ])
    cells.extend([
        (_fmt_num(comp_val, ".2f"), C_BOLD + C_CYAN if comp_val is not None else C_DIM, 6, ">"),
        ("·".join(r.get("coverage", ["—"])), C_DIM, 8, "^"),
        (ctx_s, C_CYAN, 5, ">"),
    ])
    if not is_slim:
        cells.append((r.get("modality", "—")[:12], C_WHITE, 12, "<"))
    cells.extend([
        (r.get("price_str", "—"), C_YELLOW, 12, ">"),
        (r.get("created", "—"), C_DIM, 10, "^"),
    ])
    return cells


def render_cli_table(rows_sorted, color=True, is_slim=False, n_aa=0, n_lm=0):
    """Render structured TUI table with adaptive terminal width and alternating row zebra striping."""
    headers = _HEADERS_SLIM if is_slim else _HEADERS_FULL
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    top_model = rows_sorted[0] if rows_sorted and rows_sorted[0].get("composite") is not None else None
    col_medals = bc.compute_column_medals(
        rows_sorted,
        {"q": (lambda r: r["benchmarks"].get("capability_q") or 0, True, None)},
        id_key="model_id",
    )

    top_info = f"Top Leader: {top_model['display'][:16]} (Q {top_model['benchmarks'].get('capability_q', 0):.1f})" if top_model else "No benchmarked models"
    summary_str = f" Tracked: {len(rows_sorted)} stealth models │ AA data: {n_aa} │ Arena data: {n_lm} │ {top_info}"
    out = bc.render_banner_box(
        "⚡ STEALTH MODEL RADAR (OpenRouter stealth/ Anonymous Namespace)",
        summary_lines=[summary_str],
        inner_w=inner_w,
        color=color,
        plain_title_line=f" STEALTH MODEL RADAR (OpenRouter stealth/ namespace) — Tracked: {len(rows_sorted)} models",
    )
    styled = [_cli_row_cells(i, r, col_medals.get(r.get("model_id"), {}), color, is_slim) for i, r in enumerate(rows_sorted)]
    out.extend(bc.render_styled_cli_table(headers, styled, color=color))
    out.append("")
    out.extend(bc.render_metric_guide_cli(
        "Stealth Model Intelligence Guide",
        [
            ("Stealth Namespace", "Anonymous / blind test candidate models on OpenRouter.", C_MAGENTA),
            ("Badges ¹²³", "🥇/🥈/🥉 place leaders in respective column.", C_YELLOW),
            ("Q(Cap)", "Normalized Capability Score (40.0–99.9) when cross-indexed with benchmark sources.", C_WHITE),
        ],
        color=color,
    ))
    return "\n".join(out)


def _load_or_catalog(do_fetch: bool, do_write: bool, verbose: bool) -> dict:
    if not do_fetch and not pick_latest_raw("openrouter_models"):
        print("  ERROR: no docs/data/raw/openrouter_models*.json snapshot — run with --fetch once to populate.", file=sys.stderr)
        sys.exit(2)
    j = bc.fetch_or_load_json_snapshot(RAW, ROOT, OPENROUTER_API, "openrouter_models", fetch=do_fetch, write=do_write, verbose=verbose)
    or_map = bc.parse_openrouter(j, verbose=verbose) if isinstance(j, dict) else {}
    if do_fetch and not or_map:
        cached = bc.fetch_or_load_json_snapshot(RAW, ROOT, OPENROUTER_API, "openrouter_models", fetch=False, write=False, verbose=verbose)
        or_map = bc.parse_openrouter(cached, verbose=verbose) if isinstance(cached, dict) else {}
    return or_map


def _format_or_price(pricing: dict | None) -> str:
    p = pricing or {}
    try:
        pin = float(p.get("prompt", 0) or 0) * 1e6
        pout = float(p.get("completion", 0) or 0) * 1e6
        price_str = f"{pin:.2f}/{pout:.2f}"
    except Exception:
        return "—"
    return f"{price_str} ($0)" if price_str == "0.00/0.00" else price_str


def _stealth_bench_dict(b_id: str, oid: str, aa_map: dict, lm_map: dict, or_ctx) -> dict:
    aa = (bc.find_aa_for_model(b_id, aa_map) or bc.find_aa_for_model(oid, aa_map) or {}) if aa_map else {}
    lm = (bc.find_lm_for_model(b_id, lm_map) or bc.find_lm_for_model(oid, lm_map) or {}) if lm_map else {}
    slug_raw = str(aa.get("slug") or "")
    return {
        "aa_slug": slug_raw if slug_raw and not slug_raw.startswith("$") else None,
        "aa_intelligence": _safe_float(aa.get("intelligenceIndex")),
        "lmarena_rank": _safe_int(lm.get("rank")),
        "lmarena_elo": _safe_float(lm.get("elo")),
        "openrouter_context": or_ctx,
    }


def _build_stealth_row(rec: dict, aa_map: dict, lm_map: dict) -> dict:
    oid = rec.get("id", "") or ""
    b_id = base_id(oid)
    bench = _stealth_bench_dict(b_id, oid, aa_map, lm_map, rec.get("context_length"))
    cov = [tag for tag, val in (("AA", bench["aa_intelligence"]), ("LM", bench["lmarena_elo"])) if val is not None]
    return {
        "model_id": oid,
        "display": b_id.split("/")[-1],
        "display_full": b_id,
        "provider": STEALTH_PREFIX.rstrip("/"),
        "name": rec.get("name") or "",
        "description": (rec.get("description") or "")[:280],
        "created": created_date(rec),
        "modality": (rec.get("architecture") or {}).get("modality") or "—",
        "price_str": _format_or_price(rec.get("pricing")),
        "benchmarks": bench,
        "coverage": cov or ["—"],
    }


def _write_stealth_outputs(args, rows_sorted: list[dict], or_map: dict, n_aa: int, n_lm: int) -> None:
    if (args.json or args.html) and not or_map:
        print("  ERROR: OpenRouter catalog yielded 0 records (live fetch failed and no usable cached snapshot) — refusing --json/--html write", file=sys.stderr)
        sys.exit(1)
    if args.json:
        payload = {
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "sources": {
                "openrouter_api": OPENROUTER_API,
                "artificial_analysis": AA_URL,
                "lmarena": LMARENA_URL,
                "note": "stealth = OpenRouter id starts with 'stealth/' (anonymous/undisclosed models); composite = mean of per-source z-scores (AA Intelligence Index, LMArena ELO)",
            },
            "n_stealth": len(rows_sorted),
            "n_with_aa": n_aa,
            "n_with_lm": n_lm,
            "models": rows_sorted,
        }
        p = DATA / "stealth_models.json"
        bc.atomic_write_text(p, json.dumps(payload, indent=2))
        print(f"\nwrote {p.relative_to(ROOT)}")
    if args.html:
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / "stealth_models.html"
        bc.atomic_write_text(p, render_html(rows_sorted, n_aa, n_lm))
        print(f"wrote {p.relative_to(ROOT)}")


def _parse_args():
    ap = argparse.ArgumentParser(
        description="OpenRouter stealth models (stealth/ namespace) ranked by composite intelligence (AA Index + LMArena ELO, z-scored)"
    )
    ap.add_argument("--fetch", action="store_true", help="network path: live-fetch OpenRouter/AA/LMArena and save dated snapshots")
    ap.add_argument("--check", action="store_true", help="print only: writes NOTHING (data/html outputs, raw snapshots) — even combined with --fetch")
    ap.add_argument("--json", action="store_true", help="write docs/data/stealth_models.json")
    ap.add_argument("--html", action="store_true", help="write docs/reports/stealth_models.html")
    ap.add_argument("--verbose", action="store_true", help="verbose fetch logging")
    ap.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors and box drawing")
    ap.add_argument("--slim", action="store_true", help="Force compact table layout for split panes")
    ap.add_argument("--wide", action="store_true", help="Force wide table layout")
    return ap.parse_args()


def _prepare_runtime(args) -> tuple[bool, bool, bool, bool, bool]:
    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    do_fetch, do_write = bool(args.fetch), not bool(args.check)
    mode = "fetch (network)" if do_fetch else "OFFLINE (cache-only)"
    chk = " · check: no writes" if args.check else ""
    print("Stealth models (OpenRouter stealth/ namespace) — composite intelligence")
    print(f"  date: {dt.datetime.now(dt.UTC).isoformat()}")
    print(f"  mode: {mode}{chk}")
    color = not bool(args.plain or os.getenv("NO_COLOR"))
    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_slim = bool(args.slim or (term_cols < 115 and not args.wide))
    return bool(args.verbose), do_fetch, do_write, color, is_slim


def main():
    args = _parse_args()
    verbose, do_fetch, do_write, color, is_slim = _prepare_runtime(args)

    or_map = _load_or_catalog(do_fetch, do_write, verbose)
    stealth_recs = sorted((rec for rec in or_map.values() if is_stealth_model(rec)), key=lambda r: r.get("id", ""))
    print(f"  catalog: {len(or_map)} models in OR; stealth: {len(stealth_recs)}")

    aa_map = bc.fetch_or_load_aa(RAW, ROOT, fetch=do_fetch, write=do_write, verbose=verbose) if stealth_recs else {}
    lm_map = bc.fetch_or_load_lmarena(RAW, fetch=do_fetch, write=do_write, verbose=verbose) if stealth_recs else {}
    rows = [_build_stealth_row(rec, aa_map, lm_map) for rec in stealth_recs]

    aa_vals, lm_vals, *_ = compute_meanfill_composite(rows)
    if not aa_vals and not lm_vals:
        print("  Note: no stealth model found on AA or LMArena — composites will be —", file=sys.stderr)

    rows_sorted = sorted(rows, key=comp_key)
    print("")
    print(render_cli_table(rows_sorted, color=color, is_slim=is_slim, n_aa=len(aa_vals), n_lm=len(lm_vals)))

    if not do_write:
        print("\n(check-only, no files written)")
        return
    _write_stealth_outputs(args, rows_sorted, or_map, len(aa_vals), len(lm_vals))


if __name__ == "__main__":
    main()
