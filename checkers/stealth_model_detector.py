#!/usr/bin/env python3
"""
stealth_models_check.py — OpenRouter stealth models (stealth/ namespace) ranked by composite intelligence

Fetches the live OpenRouter model catalog and keeps only models in the
`stealth/` namespace (OpenRouter's home for anonymous/undisclosed models,
e.g. stealth/ox-alpha). Attaches intelligence signals from Artificial
Analysis (Intelligence Index) and LMArena (ELO), builds a normalized
composite score (z-scored per source, averaged — same scoring as fcheck),
and prints a table sorted by intelligence.

Stdlib only. Reuses parsers + cross-source matchers from ocgo_check.py.
No API keys. Console table by default; --json / --html flag the files.
"""
import argparse
import datetime as dt
import html
import json
import pathlib
import statistics
import sys

# ---- import ocgo_check's battle-tested parsers without duplicating them ----
HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
# repo root: llm-search has scripts/ one level down, agents-config has tui-agent-settings/usage/ two levels down
ROOT = HERE.parent
# walk up to find setup.sh / .git so the same file works in both repos
for _p in (HERE.parent, HERE.parent.parent, HERE.parent.parent.parent):
    if (_p / "setup.sh").exists() or (_p / ".git").exists():
        ROOT = _p
        break
DATA = ROOT / "docs" / "data"
RAW = DATA / "raw"
OUT = ROOT / "docs" / "reports"

import os
import shutil
import benchmark_common as bc
from benchmark_common import (
    C_RESET, C_BOLD, C_DIM,
    BG_EVEN, BG_ODD, BG_HEADER,
    C_GOLD, C_SILVER, C_BRONZE,
    C_CYAN, C_YELLOW, C_MAGENTA, C_WHITE,
    _safe_float, _safe_int,
    compute_meanfill_composite, comp_key, is_stealth_model, base_id,
    color_cell, medal_badge,
    score_color_q,
    HTML_CSS_COMMON, HTML_SORT_SCRIPT,
)

import opencode_cost_benefit_analyzer as ogc

OPENROUTER_API = ogc.OPENROUTER_API
AA_URL = ogc.AA_URL
LMARENA_URL = ogc.LMARENA_URL

STEALTH_PREFIX = "stealth/"


def pick_latest_raw(name_part):
    """Newest snapshot in data/raw/ whose name contains name_part, or None."""
    return bc.pick_latest_raw(RAW, name_part)


def created_date(rec):
    """OR 'created' epoch → ISO date string, or '—'."""
    c = rec.get("created")
    try:
        return dt.datetime.fromtimestamp(int(c), tz=dt.timezone.utc).date().isoformat()
    except Exception:
        return "\u2014"


def render_html(rows, n_aa, n_lm):
    title = f"OpenRouter Stealth Models — Composite Intelligence ({dt.date.today().isoformat()})"
    trs = []
    top_id = rows[0]["model_id"] if rows and rows[0].get("composite") is not None else None
    for r in rows:
        b = r["benchmarks"]
        mid = html.escape(r["display"])
        prov = html.escape(r["provider"])
        aa = f"{b['aa_intelligence']:.1f}" if isinstance(b["aa_intelligence"], (int, float)) else "\u2014"
        aa_slug = html.escape(b["aa_slug"] or "")
        elo = f"{b['lmarena_elo']:.0f}" if isinstance(b["lmarena_elo"], (int, float)) else "\u2014"
        rk = f"#{b['lmarena_rank']}" if isinstance(b["lmarena_rank"], int) else "\u2014"
        comp = f"{r['composite']:.2f}" if isinstance(r.get("composite"), (int, float)) else "\u2014"
        q_s = f"{b.get('capability_q'):.1f}" if isinstance(b.get("capability_q"), (int, float)) else "\u2014"
        cov = "\u00b7".join(r.get("coverage", ["\u2014"]))
        ctx = f"{b['openrouter_context'] // 1000}k" if isinstance(b["openrouter_context"], (int, float)) else "\u2014"
        price_s = html.escape(r.get("price_str", "\u2014"))
        created = html.escape(r.get("created", "\u2014"))
        modality = html.escape(r.get("modality", "\u2014"))
        cls = " class='top-row'" if r["model_id"] == top_id else ""
        trs.append(
            f'<tr{cls}>'
            f'<td class="m">{mid} <span class="badge badge-stl">STEALTH</span></td><td>{prov}</td>'
            f'<td class="n" style="font-weight:700; color:#3fb950;">{q_s}</td>'
            f'<td class="n">{aa}<span class="mid">{aa_slug}</span></td>'
            f'<td class="n">{elo}</td><td class="n">{rk}</td>'
            f'<td class="n" style="font-weight:700; color:#58a6ff;">{comp}</td><td>{cov}</td><td class="n">{ctx}</td>'
            f"<td>{modality}</td><td class='n'>{price_s}</td><td class='n'>{created}</td>"
            f"</tr>"
        )
    body = f"""
<div class="wrap">
<h1>{html.escape(title)}</h1>
<p class="sub">Models in OpenRouter's <code>stealth/</code> namespace (anonymous/undisclosed models being tested publicly, e.g. <code>stealth/ox-alpha</code>), ranked by normalized composite intelligence = mean of z-scored <a href="https://artificialanalysis.ai/leaderboards/models">Artificial Analysis</a> Intelligence Index and <a href="https://arena.ai/leaderboard/text">Arena.ai</a> ELO. <b>{len(rows)}</b> stealth models · <b>{n_aa}</b> on AA · <b>{n_lm}</b> on Arena · Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
<div class="card"><b>How to read:</b> <span class="badge badge-gold">TOP LEADER</span> = highest composite intelligence · <b>Q(Cap)</b> = Composite Capability (40–99.9). Stealth identity means provider/author is undisclosed on OpenRouter; AA/LMArena slugs may or may not resolve. Empty table = no stealth models currently listed.</div>
<div class="card">
<table id="tbl">
<thead><tr><th>model</th><th>provider</th><th>Q(Cap)</th><th>AA intel</th><th>LM ELO</th><th>LM rank</th><th>composite</th><th>coverage</th><th>ctx</th><th>modality</th><th>$in/$out</th><th>created</th></tr></thead>
<tbody>{''.join(trs)}</tbody>
</table>
<div class="legend">Click headers to sort. \u2014 = not on that leaderboard / unknown.</div>
</div>
<div class="footer"><span class="path">docs/reports/stealth_models.html</span><span class="work">Composite rank of {len(rows)} stealth model(s) ({n_aa} on AA, {n_lm} on LMArena — top: {html.escape(rows[0]['display']) if rows and rows[0].get('composite') is not None else 'none'}).</span></div>
</div>
{HTML_SORT_SCRIPT}
"""
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{HTML_CSS_COMMON}\n.top-row {{{{ background: rgba(210,153,34,0.08); font-weight: 600; }}}}</style></head><body>{body}</body></html>"


def render_cli_table(rows_sorted, color=True, is_slim=False, n_aa=0, n_lm=0):
    """Render structured TUI table with adaptive terminal width and alternating row zebra striping."""
    if is_slim:
        headers = [
            ("Rank", 4, "^"),
            ("Model", 24, "<"),
            ("Q(Cap)", 6, ">"),
            ("Comp", 6, ">"),
            ("Coverage", 8, "^"),
            ("Ctx", 5, ">"),
            ("Price", 12, ">"),
            ("Created", 10, "^"),
        ]
    else:
        headers = [
            ("Rank", 4, "^"),
            ("Model", 28, "<"),
            ("Q(Cap)", 6, ">"),
            ("AA Intel", 8, ">"),
            ("LM ELO", 7, ">"),
            ("Comp", 6, ">"),
            ("Coverage", 8, "^"),
            ("Ctx", 5, ">"),
            ("Modality", 12, "<"),
            ("Price", 12, ">"),
            ("Created", 10, "^"),
        ]

    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    total_models = len(rows_sorted)
    top_model = rows_sorted[0] if rows_sorted and rows_sorted[0].get("composite") is not None else None

    col_medals = bc.compute_column_medals(
        rows_sorted,
        {"q": (lambda r: r["benchmarks"].get("capability_q") or 0, True, None)},
        id_key="model_id",
    )

    out = []
    title_str = "⚡ STEALTH MODEL RADAR (OpenRouter stealth/ Anonymous Namespace)"
    top_info = f"Top Leader: {top_model['display'][:16]} (Q {top_model['benchmarks'].get('capability_q', 0):.1f})" if top_model and top_model.get("composite") is not None else "No benchmarked models"
    summary_str = f" Tracked: {total_models} stealth models │ AA data: {n_aa} │ Arena data: {n_lm} │ {top_info}"

    out.extend(bc.render_banner_box(
        title_str,
        summary_lines=[summary_str],
        inner_w=inner_w,
        color=color,
        plain_title_line=f" STEALTH MODEL RADAR (OpenRouter stealth/ namespace) — Tracked: {total_models} models",
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
        hdr_str = " ".join([f"{h:^{w}}" if a == "^" else (f"{h:>{w}}" if a == ">" else f"{h:<{w}}") for h, w, a in headers])
        out.append(hdr_str)
        out.append("-" * (inner_w + 2))

    for idx, r in enumerate(rows_sorted):
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

        meds = col_medals.get(r.get("model_id"), {})
        b = r["benchmarks"]
        q_val = b.get("capability_q")
        q_s = (f"{q_val:.1f}" if isinstance(q_val, (int, float)) else "—") + medal_badge(meds.get("q"), color=color)
        aa_s = f"{b['aa_intelligence']:.1f}" if isinstance(b["aa_intelligence"], (int, float)) else "—"
        lm_s = f"{b['lmarena_elo']:.0f}" if isinstance(b["lmarena_elo"], (int, float)) else "—"
        comp_val = r.get("composite")
        comp_s = f"{comp_val:.2f}" if isinstance(comp_val, (int, float)) else "—"
        cov_s = "·".join(r.get("coverage", ["—"]))
        ctx_val = b.get("openrouter_context")
        ctx_s = f"{ctx_val // 1000}k" if isinstance(ctx_val, (int, float)) else "—"
        mod_str = r.get("modality", "—")[:12]
        price_str = r.get("price_str", "—")
        created_str = r.get("created", "—")

        m_w = 24 if is_slim else 28
        m_name = r["display"][:m_w]

        if color:
            rank_col = C_BOLD + (C_GOLD if rank_num == 1 else (C_SILVER if rank_num == 2 else (C_BRONZE if rank_num == 3 else C_WHITE)))
            mid_col = C_BOLD + C_MAGENTA
            q_col = score_color_q(q_val)
            comp_col = C_BOLD + C_CYAN if comp_val is not None else C_DIM

            row_cells = [
                color_cell(rank_str, rank_col, width=4, align="^", bg=bg),
                color_cell(m_name, mid_col, width=m_w, align="<", bg=bg),
                color_cell(q_s, q_col, width=6, align=">", bg=bg),
            ]
            if not is_slim:
                row_cells.extend([
                    color_cell(aa_s, C_WHITE, width=8, align=">", bg=bg),
                    color_cell(lm_s, C_WHITE, width=7, align=">", bg=bg),
                ])
            row_cells.extend([
                color_cell(comp_s, comp_col, width=6, align=">", bg=bg),
                color_cell(cov_s, C_DIM, width=8, align="^", bg=bg),
                color_cell(ctx_s, C_CYAN, width=5, align=">", bg=bg),
            ])
            if not is_slim:
                row_cells.append(color_cell(mod_str, C_WHITE, width=12, align="<", bg=bg))
            row_cells.extend([
                color_cell(price_str, C_YELLOW, width=12, align=">", bg=bg),
                color_cell(created_str, C_DIM, width=10, align="^", bg=bg),
            ])
            out.append(f"{bg}{C_DIM}│{C_RESET}" + f"{bg}{C_DIM}│{C_RESET}".join(row_cells) + f"{bg}{C_DIM}│{C_RESET}")
        else:
            row_items = [
                f"{rank_str:^4}",
                f"{m_name:<{m_w}}",
                f"{q_s:>6}",
            ]
            if not is_slim:
                row_items.extend([
                    f"{aa_s:>8}",
                    f"{lm_s:>7}",
                ])
            row_items.extend([
                f"{comp_s:>6}",
                f"{cov_s:^8}",
                f"{ctx_s:>5}",
            ])
            if not is_slim:
                row_items.append(f"{mod_str:<12}")
            row_items.extend([
                f"{price_str:>12}",
                f"{created_str:^10}",
            ])
            out.append(" ".join(row_items))

    if color:
        out.append(f"{C_DIM}{bot_border}{C_RESET}")
    else:
        out.append("-" * (inner_w + 2))
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


def main():  # noqa: PLR0915
    ap = argparse.ArgumentParser(
        description="OpenRouter stealth models (stealth/ namespace) ranked by composite intelligence (AA Index + LMArena ELO, z-scored)"
    )
    ap.add_argument("--offline", action="store_true", help="use cached data/raw/ snapshots, no network")
    ap.add_argument("--fetch", action="store_true", help="save raw snapshots to data/raw/")
    ap.add_argument("--check", action="store_true", help="dry-run: fetch + print, no file writes")
    ap.add_argument("--json", action="store_true", help="write data/stealth_models.json")
    ap.add_argument("--html", action="store_true", help="write outputs/stealth_models.html")
    ap.add_argument("--verbose", action="store_true", help="verbose fetch logging")
    ap.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors and box drawing")
    ap.add_argument("--slim", action="store_true", help="Force compact table layout for split panes")
    ap.add_argument("--wide", action="store_true", help="Force wide table layout")
    args = ap.parse_args()
    verbose = bool(args.verbose)
    offline = bool(args.offline)
    do_fetch = bool(args.fetch and not offline)
    do_write = not bool(args.check)
    color = not bool(args.plain or os.getenv("NO_COLOR"))
    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_slim = bool(args.slim or (term_cols < 115 and not args.wide))

    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    print("Stealth models (OpenRouter stealth/ namespace) \u2014 composite intelligence")
    print(f"  date: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    print(f"  mode: {'offline' if offline else 'live'}" + (" +fetch" if do_fetch else "") + (" check-only" if args.check else ""))

    # ---- 1. OpenRouter catalog → stealth filter ----
    or_map = {}
    if offline:
        snap = pick_latest_raw("openrouter_models")
        if not snap:
            print("  ERROR: --offline but no data/raw/openrouter_models*.json found; run without --offline first.", file=sys.stderr)
            sys.exit(2)
        try:
            j = json.loads(snap.read_text(errors="replace"))
        except Exception as e:  # noqa: BLE001
            print(f"  WARN offline OR snapshot bad: {e}", file=sys.stderr)
            j = None
        print(f"  offline OR snapshot: {snap.name}")
        or_map = ogc.parse_openrouter(j, verbose=verbose) if j is not None else {}
    else:
        body = ogc.fetch(OPENROUTER_API, verbose=verbose)
        if body:
            try:
                j = json.loads(body)
                if do_fetch:
                    s = RAW / f"openrouter_models_{dt.date.today().isoformat().replace('-', '')}.json"
                    s.write_text(json.dumps(j, indent=2))
                    print(f"  saved OR -> {s.relative_to(ROOT)} ({len(body)} bytes)")
                or_map = ogc.parse_openrouter(j, verbose=verbose)
            except Exception as e:  # noqa: BLE001
                print(f"  WARN OR json: {e}", file=sys.stderr)
        else:
            print("  WARN OR fetch failed", file=sys.stderr)

    stealth_recs = [rec for rec in or_map.values() if is_stealth_model(rec)]
    stealth_recs.sort(key=lambda r: r.get("id", ""))
    print(f"  catalog: {len(or_map)} models in OR; stealth: {len(stealth_recs)}")

    # ---- 2. AA ----
    aa_map = {}
    if stealth_recs:
        if offline:
            snap = pick_latest_raw("artificial_analysis")
            if snap:
                try:
                    aa_map = ogc.parse_aa(snap.read_text(errors="ignore"), verbose=verbose)
                except Exception as e:  # noqa: BLE001
                    print(f"  WARN AA offline parse: {e}", file=sys.stderr)
                print(f"  AA: {len(aa_map)} entries ({snap.name})")
            else:
                print("  AA: no offline snapshot available")
        else:
            body = ogc.fetch(AA_URL, verbose=verbose)
            if body:
                html_txt = body.decode(errors="ignore")
                if do_fetch:
                    s = RAW / f"artificial_analysis_{dt.date.today().isoformat().replace('-', '')}.html"
                    s.write_text(html_txt)
                    print(f"  saved AA -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
                aa_map = ogc.parse_aa(html_txt, verbose=verbose)
                print(f"  AA: {len(aa_map)} models")
            else:
                print("  WARN AA fetch failed", file=sys.stderr)

    # ---- 3. LMArena ----
    lm_map = {}
    if stealth_recs:
        if offline:
            snap = pick_latest_raw("lmarena")
            if snap:
                try:
                    lm_map = ogc.parse_lmarena(snap.read_text(errors="ignore"), verbose=verbose)
                except Exception as e:  # noqa: BLE001
                    print(f"  WARN LMArena offline parse: {e}", file=sys.stderr)
                print(f"  LMArena: {len(lm_map)} entries ({snap.name})")
            else:
                print("  LMArena: no offline snapshot available")
        else:
            body = ogc.fetch(LMARENA_URL, verbose=verbose)
            if body:
                html_txt = body.decode(errors="ignore")
                if do_fetch:
                    s = RAW / f"lmarena_{dt.date.today().isoformat().replace('-', '')}.html"
                    s.write_text(html_txt)
                    print(f"  saved LMArena -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
                lm_map = ogc.parse_lmarena(html_txt, verbose=verbose)
                print(f"  LMArena: {len(lm_map)} entries")
            else:
                print("  WARN LMArena fetch failed", file=sys.stderr)

    # ---- 4. merge: attach intelligence to each stealth model ----
    rows = []
    for rec in stealth_recs:
        oid = rec.get("id", "") or ""
        b_id = base_id(oid)
        aa_rec = ogc.find_aa_for_ocgo(b_id, aa_map) or ogc.find_aa_for_ocgo(oid, aa_map) if aa_map else None
        lm_rec = ogc.find_lm_for_ocgo(b_id, lm_map) or ogc.find_lm_for_ocgo(oid, lm_map) if lm_map else None

        aa_int = ogc._safe_float(aa_rec.get("intelligenceIndex")) if aa_rec else None
        aa_slug = str(aa_rec.get("slug") or "") if aa_rec and not str(aa_rec.get("slug", "")).startswith("$") else None
        lm_elo = ogc._safe_float(lm_rec.get("elo")) if lm_rec else None
        lm_rank = ogc._safe_int(lm_rec.get("rank")) if lm_rec else None

        p = rec.get("pricing", {}) or {}
        try:
            price_str = f"{float(p.get('prompt', 0) or 0)*1e6:.2f}/{float(p.get('completion', 0) or 0)*1e6:.2f}"
        except Exception:
            price_str = "\u2014"

        coverage = []
        if aa_int is not None:
            coverage.append("AA")
        if lm_elo is not None:
            coverage.append("LM")
        if not coverage:
            coverage = ["\u2014"]

        display_short = b_id.split("/")[-1] if "/" in b_id else b_id
        rows.append(
            {
                "model_id": oid,
                "display": display_short,
                "display_full": b_id,
                "provider": STEALTH_PREFIX.rstrip("/"),
                "name": rec.get("name") or "",
                "description": (rec.get("description") or "")[:280],
                "created": created_date(rec),
                "modality": (rec.get("architecture", {}) or {}).get("modality") or "\u2014",
                "price_str": price_str + (" ($0)" if price_str == "0.00/0.00" else ""),
                "benchmarks": {
                    "aa_slug": aa_slug,
                    "aa_intelligence": aa_int,
                    "lmarena_rank": lm_rank,
                    "lmarena_elo": lm_elo,
                    "openrouter_context": rec.get("context_length"),
                },
                "coverage": coverage,
            }
        )

    # ---- 5. normalized composite — mean of available z-scores ----
    aa_vals, lm_vals, aa_mean, aa_std, lm_mean, lm_std = compute_meanfill_composite(rows)
    if not aa_vals and not lm_vals:
        print("  Note: no stealth model found on AA or LMArena — composites will be \u2014", file=sys.stderr)

    rows_sorted = sorted(rows, key=comp_key)
    n_aa = len(aa_vals)
    n_lm = len(lm_vals)

    # ---- 6. console table (always, the default output) ----
    print("")
    print(render_cli_table(rows_sorted, color=color, is_slim=is_slim, n_aa=n_aa, n_lm=n_lm))

    # ---- 7. file outputs (only when --json/--html and not --check) ----
    if not do_write:
        print("\n(check-only, no files written)")
        return
    if args.json:
        payload = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
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
        p.write_text(json.dumps(payload, indent=2))
        print(f"\nwrote {p.relative_to(ROOT)}")
    if args.html:
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / "stealth_models.html"
        p.write_text(render_html(rows_sorted, n_aa, n_lm))
        print(f"wrote {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
