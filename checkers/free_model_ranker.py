#!/usr/bin/env python3
"""
free_models_check.py — Free models (OpenCode Zen/Go + Cline) ranked by composite intelligence

Reads the OpenCode Zen/Go free-tier ids (`-free` naming) and the Cline
Recommended-Models free tier from the raw cache and lists exactly those. The
OpenRouter catalog is fetched ONLY to validate Cline free claims and supply
price/context enrichment — OpenRouter-only free models are never listed.
Each listed model gets intelligence signals from Artificial Analysis
(Intelligence Index) and LMArena (ELO); a normalized composite score
(z-scored per source, averaged) sorts the printed table.

Stdlib only. Reuses parsers + cross-source matchers from ocgo_check.py.
Offline by default (rule 7): --fetch is the only network path.
No API keys. Console table by default; --json / --html flag the files.
"""
import argparse
import datetime as dt
import html
import json
import os
import pathlib
import shutil
import statistics
import sys

# ---- import ocgo_check's battle-tested parsers without duplicating them ----
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
from benchmark_common import (
    C_RESET, C_BOLD, C_DIM,
    BG_EVEN, BG_ODD, BG_HEADER,
    C_GOLD, C_SILVER, C_BRONZE,
    C_GREEN, C_CYAN, C_YELLOW, C_MAGENTA, C_WHITE, C_RED,
    _safe_float, _safe_int,
    norm_id,
    compute_p_success, compute_token_multiplier,
    compute_fgi,
    compute_meanfill_composite, comp_key, is_stealth_model, base_id,
    medal_badge,
    color_cell, pool_badge,
    score_color_q, score_color_p, score_color_fgi,
    HTML_CSS_COMMON, HTML_SORT_SCRIPT,
    load_previous_snapshot, diff_model_catalog, render_removed_models_cli,
    AA_URL, LMARENA_URL, OPENROUTER_API, OPENCODE_ZEN_API, OPENCODE_GO_API, CLINE_RECOMMENDED_MODELS_API,
    find_aa_for_model, find_lm_for_model,
)

CLINE_FREEMODEL_API = CLINE_RECOMMENDED_MODELS_API


def is_free_model(rec):
    """OpenRouter pricing $0 → free. Fields are strings like '0' or '0.0001'."""
    oid = rec.get("id", "") or ""
    if oid.endswith(":free"):
        return True
    p = rec.get("pricing", {}) or {}
    try:
        prompt = float(p.get("prompt", 0) or 0)
        completion = float(p.get("completion", 0) or 0)
    except (ValueError, TypeError):
        return False
    return prompt == 0.0 and completion == 0.0


def _free_key(oid: str) -> str:
    """S3-F3-3 dedup key: base_id + norm_id with the provider segment stripped.
    OpenCode lists bare 'x-free' while OpenRouter/Cline list 'prov/x[:free]' —
    the old raw-norm compare missed every cross-platform duplicate."""
    return norm_id(base_id(oid).rsplit("/", 1)[-1])


def pick_latest_raw(name_part: str) -> pathlib.Path | None:
    """Newest snapshot in data/raw/ whose name contains name_part, or None."""
    return bc.pick_latest_raw(RAW, name_part)


def fetch_or_load_cached_json(
    api_url: str,
    snapshot_prefix: str,
    fetch: bool = False,
    write: bool = True,
    verbose: bool = False,
) -> dict | list | None:
    """Offline-by-default (rule 7 / S3-F3-5): the plain path reads the newest dated
    snapshot in RAW; fetch=True is the only network path. Snapshots are saved only
    when write=True (--check wins on writes). >24h-old cache is tagged and used,
    never fetched. Does not use hardcoded fallback lists. Returns parsed JSON or None.
    """
    if fetch:
        body = bc.fetch_url(api_url, timeout=20)
        if body:
            try:
                data = json.loads(body if isinstance(body, str) else body.decode("utf-8", errors="ignore"))
                if write:
                    target = RAW / f"{snapshot_prefix}_{dt.date.today().isoformat().replace('-', '')}.json"
                    bc.atomic_write_text(target, json.dumps(data, indent=2))
                    print(f"  saved {snapshot_prefix} -> {target.relative_to(ROOT)} ({len(body)} bytes)")
                return data
            except Exception as e:
                print(f"  WARN {snapshot_prefix} json parse: {e}", file=sys.stderr)
        else:
            print(f"  WARN {api_url} fetch failed, falling back to cached snapshot", file=sys.stderr)

    snap = pick_latest_raw(snapshot_prefix)
    if snap:
        try:
            data = json.loads(snap.read_text(errors="replace"))
            print(f"  cached {snapshot_prefix}: {snap.name}{bc.staleness_tag(snap)}")
            return data
        except Exception as e:
            print(f"  WARN {snapshot_prefix} cached snapshot bad: {e}", file=sys.stderr)
            return None
    print(f"  WARN no cached snapshot found for {snapshot_prefix} — run with --fetch once to populate", file=sys.stderr)
    return None


def render_html(rows, n_aa, n_lm, added_ids=None, removed_models=None):
    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []

    title = f"Free Models (OpenCode Zen/Go + Cline) — Composite Intelligence ({dt.date.today().isoformat()})"
    trs = []
    top_id = rows[0]["model_id"] if rows and rows[0].get("composite") is not None else None
    for r in rows:
        is_added = (r.get("model_id") in added_ids) or (r.get("display") in added_ids)
        b = r["benchmarks"]
        raw_mid = html.escape(r["display"])
        mid = f'{raw_mid}<span class="badge badge-new">+NEW</span>' if is_added else raw_mid
        prov = html.escape(r.get("provider", ""))
        aa_int = b.get("aa_intelligence")
        aa = f"{aa_int:.1f}" if isinstance(aa_int, (int, float)) else "\u2014"
        aa_slug = html.escape(b.get("aa_slug") or "")
        aa_cod = b.get("aa_coding")
        cod = f"{aa_cod:.1f}" if isinstance(aa_cod, (int, float)) else "\u2014"
        aa_age = b.get("aa_agentic")
        age = f"{aa_age:.1f}" if isinstance(aa_age, (int, float)) else "\u2014"
        lm_elo = b.get("lmarena_elo")
        elo = f"{lm_elo:.0f}" if isinstance(lm_elo, (int, float)) else "\u2014"
        lm_rk = b.get("lmarena_rank")
        rk = f"#{lm_rk}" if isinstance(lm_rk, int) else "\u2014"
        comp = f"{r['composite']:.2f}" if isinstance(r.get("composite"), (int, float)) else "\u2014"
        q_s = f"{b['capability_q']:.1f}" if isinstance(b.get("capability_q"), (int, float)) else "\u2014"
        p_s = f"{b['p_success']:.1f}%" if isinstance(b.get("p_success"), (int, float)) else "\u2014"
        fgi_s = f"{b['fgi_score']:.1f}" if isinstance(b.get("fgi_score"), (int, float)) else "\u2014"
        cov = "\u00b7".join(r.get("coverage", ["\u2014"]))
        ctx_val = b.get("openrouter_context")
        ctx = f"{ctx_val // 1000}k" if isinstance(ctx_val, (int, float)) else "\u2014"
        src_raw = r.get("source", "oc")
        src_cls = {"oc": "badge-ocg", "cln": "badge-cln", "stl": "badge-stl"}.get(src_raw, "badge-ocg")
        src = f'<span class="badge {src_cls}">{html.escape(src_raw.upper())}</span>'
        stl = ' <span class="badge badge-stl">STEALTH</span>' if r.get("stealth") else ""
        cls_parts = []
        if is_added:
            cls_parts.append("added")
        if r["model_id"] == top_id:
            cls_parts.append("top-row")
        cls = f" class='{' '.join(cls_parts)}'" if cls_parts else ""
        trs.append(
            f'<tr{cls}>'
            f'<td class="m">{mid}{stl}</td><td>{prov}</td><td>{src}</td>'
            f'<td class="n" style="font-weight:700; color:#3fb950;">{q_s}</td>'
            f'<td class="n">{p_s}</td>'
            f'<td class="n" style="font-weight:700; color:#a371f7;">{fgi_s}</td>'
            f'<td class="n">{aa}<span class="mid">{aa_slug}</span></td>'
            f'<td class="n">{cod}</td><td class="n">{age}</td>'
            f'<td class="n">{elo}</td><td class="n">{rk}</td>'
            f'<td class="n" style="font-weight:700; color:#58a6ff;">{comp}</td><td>{cov}</td><td class="n">{ctx}</td>'
            f"</tr>"
        )

    removed_html = ""
    if removed_models:
        rem_tags = []
        for rm in removed_models:
            rm_id = html.escape(rm.get("display") or rm.get("model_id", "unknown"))
            prov = html.escape(rm.get("provider", "unknown"))
            q_val = rm.get("benchmarks", {}).get("capability_q")
            q_s = f"Q {q_val:.1f}" if isinstance(q_val, (int, float)) else "Q —"
            rem_tags.append(f'<span class="removed-tag">❌ <b>{rm_id}</b> <span class="mid">({prov}, {q_s})</span></span>')
        removed_html = f"""
        <div class="removed-section">
          <div class="removed-title">🔻 Removed / Deprecated Free Models ({len(removed_models)})</div>
          <div class="sub" style="margin-bottom:8px;">These models were present in the previous free model catalog snapshot but are no longer active in the current OpenCode or Cline free tier:</div>
          <div>{''.join(rem_tags)}</div>
        </div>
        """

    body = f"""
<div class="wrap">
<h1>{html.escape(title)}</h1>
<p class="sub">Free models (<b>OpenCode Zen/Go</b> <code>-free</code> tiers + <b>Cline</b> Free tier — OpenRouter-only free models are not listed) ranked by normalized composite intelligence = mean of z-scored <a href="https://artificialanalysis.ai/leaderboards/models">Artificial Analysis</a> Intelligence Index and <a href="https://arena.ai/leaderboard/text">Arena.ai</a> ELO. <b>{len(rows)}</b> free models · <b>{n_aa}</b> on AA · <b>{n_lm}</b> on Arena · Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
<div class="card"><b>How to read:</b> <span class="badge badge-gold">TOP LEADER</span> = highest composite intelligence · <b>Q(Cap)</b> = Composite Capability (40–99.9) · <b>P(Succ)</b> = 1-turn pass rate · <b>FGI (Gate)</b> = Frontier Gate Index. AA Intelligence/Coding/Agentic from artificialanalysis.ai; Arena rank/ELO from arena.ai text leaderboard; context from OpenRouter. Cross-source scales are z-scored per source and averaged.</div>
<div class="card">
<table id="tbl">
<thead><tr><th>model</th><th>provider</th><th>src</th><th>Q(Cap)</th><th>P(Succ)</th><th>FGI (Gate)</th><th>AA intel</th><th>AA cod</th><th>AA agent</th><th>LM ELO</th><th>LM rank</th><th>composite</th><th>coverage</th><th>ctx</th></tr></thead>
<tbody>{''.join(trs)}</tbody>
</table>
<div class="legend">Click headers to sort. \u2014 = not on that leaderboard. <span class="badge badge-stl">STEALTH</span> = OpenRouter anonymous namespace (<code>stealth/…</code>).</div>
</div>
{removed_html}
<div class="footer"><span class="path">docs/reports/free_models.html</span><span class="work">Composite rank of {len(rows)} free models ({n_aa} on AA, {n_lm} on LMArena — top: {html.escape(rows[0]['display']) if rows and rows[0].get('composite') is not None else 'none'}).</span></div>
</div>
{HTML_SORT_SCRIPT}
"""
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{HTML_CSS_COMMON}\n.top-row {{{{ background: rgba(210,153,34,0.08); font-weight: 600; }}}}</style></head><body>{body}</body></html>"


def render_cli_table(rows_sorted, color=True, is_slim=False, is_wide=False, n_aa=0, n_lm=0, added_ids=None, removed_models=None):
    """Render structured TUI table with adaptive terminal width and alternating row zebra striping."""
    if added_ids is None:
        added_ids = set()
    if removed_models is None:
        removed_models = []

    if is_wide:
        headers = [
            ("Rank", 4, "^"),
            ("Model", 26, "<"),
            ("Provider", 12, "<"),
            ("Src", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("P(Succ)", 7, ">"),
            ("FGI", 5, ">"),
            ("AA Intel", 8, ">"),
            ("LM ELO", 7, ">"),
            ("Comp", 6, ">"),
            ("Cov", 5, "^"),
            ("Ctx", 5, ">"),
        ]
    elif is_slim:
        headers = [
            ("Rank", 4, "^"),
            ("Model", 18, "<"),
            ("Src", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("P(Succ)", 7, ">"),
            ("FGI", 5, ">"),
            ("Cov", 5, "^"),
            ("Ctx", 5, ">"),
        ]
    else:
        # Standard compact layout (<95 chars)
        headers = [
            ("Rank", 4, "^"),
            ("Model", 22, "<"),
            ("Provider", 10, "<"),
            ("Src", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("P(Succ)", 7, ">"),
            ("FGI", 5, ">"),
            ("Cov", 5, "^"),
            ("Ctx", 5, ">"),
        ]

    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    total_models = len(rows_sorted)
    top_model = rows_sorted[0] if rows_sorted and rows_sorted[0].get("composite") is not None else None

    col_medals = bc.compute_column_medals(
        rows_sorted,
        {
            "q": (lambda r: r["benchmarks"].get("capability_q") or 0, True, None),
            "psucc": (lambda r: r["benchmarks"].get("p_success") or 0, True, None),
            "fgi": (lambda r: r["benchmarks"].get("fgi_score") or 0, True, None),
        },
        id_key="model_id",
    )

    out = []
    title_str = "⚡ FREE MODEL RADAR (OpenCode Zen/Go + Cline Free Tiers)"
    top_info = f"Top: {top_model['display'][:14]} (Q {top_model['benchmarks'].get('capability_q', 0):.1f})" if top_model else ""
    if is_slim:
        summary_str = f" Tracked: {total_models} free models │ {top_info}"
    else:
        summary_str = f" Tracked: {total_models} free models │ AA data: {n_aa} │ Arena data: {n_lm} │ {top_info}"

    diff_notices = []
    diff_parts = []
    if added_ids:
        diff_notices.append(f"{C_BOLD}{C_GREEN}✨ New (+{len(added_ids)}): {', '.join(sorted(added_ids))}{C_RESET}")
        diff_parts.append(f"[+NEW (+{len(added_ids)}): {', '.join(sorted(added_ids))}]")
    if removed_models:
        rem_names = [m.get("display") or m.get("model_id", "unknown") for m in removed_models]
        diff_notices.append(f"{C_BOLD}{C_RED}🔻 Removed (-{len(removed_models)}): {', '.join(rem_names)}{C_RESET}")
        diff_parts.append(f"[-REMOVED (-{len(removed_models)}): {', '.join(rem_names)}]")

    out.extend(bc.render_banner_box(
        title_str,
        summary_lines=[summary_str],
        diff_notices=diff_notices,
        inner_w=inner_w,
        color=color,
        plain_title_line=f" FREE MODEL RADAR (OpenCode Zen/Go + Cline) — Tracked: {total_models} free models",
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
        p_val = b.get("p_success")
        p_s = (f"{p_val:.1f}%" if isinstance(p_val, (int, float)) else "—") + medal_badge(meds.get("psucc"), color=color)
        fgi_val = b.get("fgi_score")
        fgi_s = (f"{fgi_val:.1f}" if isinstance(fgi_val, (int, float)) else "—") + medal_badge(meds.get("fgi"), color=color)

        aa_s = f"{b['aa_intelligence']:.1f}" if isinstance(b["aa_intelligence"], (int, float)) else "—"
        lm_s = f"{b['lmarena_elo']:.0f}" if isinstance(b["lmarena_elo"], (int, float)) else "—"
        comp_val = r.get("composite")
        comp_s = f"{comp_val:.2f}" if isinstance(comp_val, (int, float)) else "—"
        cov_s = "·".join(r.get("coverage", ["—"]))
        ctx_val = b.get("openrouter_context")
        ctx_s = f"{ctx_val // 1000}k" if isinstance(ctx_val, (int, float)) else "—"

        is_stealth = bool(r.get("stealth"))
        src_raw = "stl" if is_stealth else r.get("source", "oc")
        src_badge_str = pool_badge(src_raw, color=color)

        if is_wide:
            m_w, p_w = 26, 12
        elif is_slim:
            m_w, p_w = 18, 0
        else:
            m_w, p_w = 22, 10

        is_added = (r.get("model_id") in added_ids) or (r.get("display") in added_ids)
        raw_disp = r["display"]
        m_name = f"+{raw_disp}"[:m_w] if is_added else raw_disp[:m_w]
        prov_name = r["provider"][:p_w] if p_w > 0 else ""

        if color:
            rank_col = C_BOLD + (C_GOLD if rank_num == 1 else (C_SILVER if rank_num == 2 else (C_BRONZE if rank_num == 3 else C_WHITE)))
            if is_added:
                mid_col = C_BOLD + C_GREEN
            elif rank_num == 1:
                mid_col = C_BOLD + C_GOLD
            elif is_stealth:
                mid_col = C_MAGENTA
            else:
                mid_col = C_WHITE

            q_col = score_color_q(q_val)
            p_col = score_color_p(p_val)
            fgi_col = score_color_fgi(fgi_val)
            comp_col = C_BOLD + C_CYAN if comp_val is not None else C_DIM

            row_cells = [
                color_cell(rank_str, rank_col, width=4, align="^", bg=bg),
                color_cell(m_name, mid_col, width=m_w, align="<", bg=bg),
            ]
            if p_w > 0:
                row_cells.append(color_cell(prov_name, C_WHITE, width=p_w, align="<", bg=bg))
            row_cells.extend([
                color_cell(src_badge_str, width=5, align="^", bg=bg),
                color_cell(q_s, q_col, width=6, align=">", bg=bg),
                color_cell(p_s, p_col, width=7, align=">", bg=bg),
                color_cell(fgi_s, fgi_col, width=5, align=">", bg=bg),
            ])
            if is_wide:
                row_cells.extend([
                    color_cell(aa_s, C_WHITE, width=8, align=">", bg=bg),
                    color_cell(lm_s, C_WHITE, width=7, align=">", bg=bg),
                    color_cell(comp_s, comp_col, width=6, align=">", bg=bg),
                ])
            row_cells.extend([
                color_cell(cov_s, C_DIM, width=5, align="^", bg=bg),
                color_cell(ctx_s, C_CYAN, width=5, align=">", bg=bg),
            ])
            out.append(f"{bg}{C_DIM}│{C_RESET}" + f"{bg}{C_DIM}│{C_RESET}".join(row_cells) + f"{bg}{C_DIM}│{C_RESET}")
        else:
            row_items = [
                f"{rank_str:^4}",
                f"{m_name:<{m_w}}",
            ]
            if p_w > 0:
                row_items.append(f"{prov_name:<{p_w}}")
            row_items.extend([
                f"{src_badge_str:^5}",
                f"{q_s:>6}",
                f"{p_s:>7}",
                f"{fgi_s:>5}",
            ])
            if is_wide:
                row_items.extend([
                    f"{aa_s:>8}",
                    f"{lm_s:>7}",
                    f"{comp_s:>6}",
                ])
            row_items.extend([
                f"{cov_s:^5}",
                f"{ctx_s:>5}",
            ])
            out.append(" ".join(row_items))

    if color:
        out.append(f"{C_DIM}{bot_border}{C_RESET}")
    else:
        out.append("-" * (inner_w + 2))

    # Removed models display
    if removed_models:
        out.append("")
        out.extend(render_removed_models_cli(removed_models, color=color, is_slim=is_slim, id_key="display"))

    out.append("")
    out.extend(bc.render_metric_guide_cli(
        "Free Model Intelligence Guide",
        [
            ("#1 Gold Leader", "Highest composite capability index across evaluated free tiers.", C_GOLD),
            ("Green (+)", "Newly added free model vs previous baseline snapshot.", C_GREEN),
            ("Badges ¹²³", "🥇/🥈/🥉 place leaders in respective column.", C_YELLOW),
            ("Q(Cap)", "Normalized Capability Score (40.0–99.9) across Artificial Analysis and Arena.ai.", C_WHITE),
            ("P(Succ)", "Estimated autonomous single-turn pass probability on non-trivial logic.", C_WHITE),
            ("[STL]", "OpenRouter anonymous namespace model (see `scheck` for dedicated analysis).", C_MAGENTA),
        ],
        color=color,
    ))

    return "\n".join(out)


def main():  # noqa: PLR0915
    ap = argparse.ArgumentParser(
        description="OpenCode Zen/Go + Cline free models ranked by composite intelligence (AA Index + LMArena ELO, z-scored)"
    )
    ap.add_argument("--fetch", action="store_true",
                    help="network path: live-fetch OpenRouter/Zen/Go/Cline/AA/LMArena and save dated snapshots to "
                         "data/raw/. The default run is fully offline on the raw cache: >24h-old sources are tagged and used, never fetched.")
    ap.add_argument("--check", action="store_true", help="print only: writes NOTHING (data/html outputs, raw snapshots) — even combined with --fetch")
    ap.add_argument("--json", action="store_true", help="write data/free_models.json")
    ap.add_argument("--html", action="store_true", help="write outputs/free_models.html")
    ap.add_argument("--verbose", action="store_true", help="verbose fetch logging")
    ap.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors and box drawing")
    ap.add_argument("--slim", action="store_true", help="Force compact table layout for split panes")
    ap.add_argument("--wide", action="store_true", help="Force wide table layout")
    args = ap.parse_args()
    verbose = bool(args.verbose)
    do_fetch = bool(args.fetch)
    do_write = not bool(args.check)
    color = not bool(args.plain or os.getenv("NO_COLOR"))
    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_wide = bool(args.wide)
    is_slim = bool(args.slim or (term_cols < 95 and not is_wide))

    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    print("Free models (OpenCode Zen/Go + Cline) \u2014 composite intelligence")
    print(f"  date: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    print(f"  mode: {'fetch (network)' if do_fetch else 'OFFLINE (cache-only)'}" + (" · check: no writes" if args.check else ""))

    # ---- 1. OpenRouter (validation + enrichment only; never listed) ----
    or_json = fetch_or_load_cached_json(OPENROUTER_API, "openrouter_models", fetch=do_fetch, write=do_write, verbose=verbose)
    or_map = bc.parse_openrouter(or_json, verbose=verbose) if or_json is not None else {}
    # Rows come exclusively from the OpenCode Zen/Go + Cline sections below; the
    # OR catalog joins on the provider-tolerant _free_key (platform ids lack OR's
    # provider prefix / `:free` suffix, so exact-id gets would never hit).
    free_recs: list[dict] = []
    or_free_by_key: dict[str, dict] = {}
    for orid, orrec in or_map.items():
        if is_free_model(orrec):
            or_free_by_key.setdefault(_free_key(orid), orrec)
    print(f"  OR catalog: {len(or_map)} models loaded, {len(or_free_by_key)} free keys (validation + price/context only — not listed)")

    # ---- 1b. OpenCode free models (Zen + Go catalogs) ----
    oc_zen_json = fetch_or_load_cached_json(OPENCODE_ZEN_API, "opencode_zen_models", fetch=do_fetch, write=do_write, verbose=verbose)
    oc_go_json = fetch_or_load_cached_json(OPENCODE_GO_API, "opencode_go_models", fetch=do_fetch, write=do_write, verbose=verbose)

    oc_free_ids: list[str] = []
    if isinstance(oc_zen_json, dict) and "data" in oc_zen_json:
        for m in oc_zen_json["data"]:
            mid = m.get("id", "")
            # ponytail: naming convention only — Zen /v1/models entries carry no `pricing`
            # field (0/64 in the 20260828+20260830 snapshots), so the former
            # price==0 clause could never fire and is deleted (S3-F3-4). If upstream
            # ever ships pricing, reinstate a real price check instead of trusting names.
            is_free = "-free" in mid.lower() or mid.lower() in ("big-pickle", "ox-alpha-free")
            if is_free and mid and mid not in oc_free_ids:
                oc_free_ids.append(mid)

    if isinstance(oc_go_json, dict) and "data" in oc_go_json:
        for m in oc_go_json["data"]:
            mid = m.get("id", "")
            if mid and (mid.lower().endswith("-free") or "-free" in mid.lower() or mid.lower() in ("big-pickle", "ox-alpha-free")) and mid not in oc_free_ids:
                oc_free_ids.append(mid)

    # S3-F3-3: dedup on the provider-tolerant free key; duplicates merge into the
    # earlier-listed row with an _also provenance marker.
    listed = {_free_key(r["id"]): r for r in free_recs}
    oc_added = oc_merged = oc_enriched = 0
    for oid in oc_free_ids:
        k = _free_key(oid)
        if k in listed:
            listed[k].setdefault("_also", []).append("oc")
            oc_merged += 1
            continue
        # OpenCode's own list is authoritative for membership; the OR catalog is
        # consulted only to carry real context_length/pricing onto the row when it
        # confirms the free claim. The platform's own id stays.
        or_rec = or_free_by_key.get(k)
        if or_rec is not None:
            rec = {"id": oid, "context_length": or_rec.get("context_length"), "pricing": or_rec.get("pricing") or {"prompt": "0", "completion": "0"}, "_source": "OC"}
            oc_enriched += 1
        else:
            rec = {"id": oid, "context_length": None, "pricing": {"prompt": "0", "completion": "0"}, "_source": "OC"}
        free_recs.append(rec)
        listed[k] = rec
        oc_added += 1
    if oc_free_ids:
        print(f"  OpenCode free: {len(oc_free_ids)} found ({', '.join(oc_free_ids)}), {oc_added} added new ({oc_enriched} price/ctx via OR), {oc_merged} merged into existing rows")
    else:
        print("  OpenCode free: none found")

    # ---- 1c. Cline provided models (Recommended Models API / Free tier) ----
    cline_json = fetch_or_load_cached_json(CLINE_RECOMMENDED_MODELS_API, "cline_models", fetch=do_fetch, write=do_write, verbose=verbose)
    cline_ids: list[tuple[str, dict | None]] = []
    if isinstance(cline_json, dict):
        raw_cline_models = cline_json.get("free", []) if "free" in cline_json else cline_json.get("data", [])
        if isinstance(raw_cline_models, list):
            for m in raw_cline_models:
                mid = m.get("id", "") if isinstance(m, dict) else str(m)
                if mid and mid not in [c[0] for c in cline_ids]:
                    cline_ids.append((mid, m if isinstance(m, dict) else None))
    elif isinstance(cline_json, list):
        for m in cline_json:
            mid = m.get("id", "") if isinstance(m, dict) else str(m)
            if mid and mid not in [c[0] for c in cline_ids]:
                cline_ids.append((mid, m if isinstance(m, dict) else None))

    cln_added = cln_merged = 0
    cln_skipped: list[str] = []
    for cid, crec in cline_ids:
        k = _free_key(cid)
        if k in listed:
            listed[k].setdefault("_also", []).append("cln")
            cln_merged += 1
            continue
        or_rec = or_free_by_key.get(k)
        # S3-F3-1: validate the loaded record with this script's own free check
        # before appending — paid OpenRouter models listed under Cline's "free"
        # tier must not enter the headline list with fabricated $0 pricing.
        check_rec = or_rec if or_rec is not None else (crec if crec is not None else {"id": cid})
        if not is_free_model(check_rec):
            cln_skipped.append(cid)
            continue
        if or_rec is not None:
            rec = {"id": cid, "context_length": or_rec.get("context_length"), "pricing": or_rec.get("pricing") or {"prompt": "0", "completion": "0"}, "_source": "CLN"}
        else:
            ctx = crec.get("context_length") if isinstance(crec, dict) else None
            rec = {"id": cid, "context_length": ctx, "pricing": {"prompt": "0", "completion": "0"}, "_source": "CLN"}
        free_recs.append(rec)
        listed[k] = rec
        cln_added += 1
    if cline_ids:
        skip_note = f" ({len(cln_skipped)} dropped as not-free per validation: {', '.join(cln_skipped)})" if cln_skipped else ""
        print(f"  Cline free: {len(cline_ids)} found, {cln_added} added new ({cln_merged} merged into existing rows){skip_note}")
    else:
        print("  Cline free: none found")

    free_recs.sort(key=lambda r: (r.get("id", "")))
    print(f"  free total: {len(free_recs)} (OC {oc_added} + CLN {cln_added})")

    # ---- 2. AA ----
    aa_map = {}
    if not do_fetch:
        snap = pick_latest_raw("artificial_analysis")
        if snap:
            try:
                aa_map = bc.parse_aa(snap.read_text(errors="ignore"), verbose=verbose)
            except Exception as e:  # noqa: BLE001
                print(f"  WARN AA offline parse: {e}", file=sys.stderr)
            print(f"  AA: {len(aa_map)} entries ({snap.name}{bc.staleness_tag(snap)})")
        else:
            print("  AA: no cached snapshot available — run with --fetch once to populate")
    else:
        body = bc.fetch_url(AA_URL, timeout=20)
        if body:
            html_txt = body if isinstance(body, str) else body.decode(errors="ignore")
            if do_write:
                s = RAW / f"artificial_analysis_{dt.date.today().isoformat().replace('-', '')}.html"
                bc.atomic_write_text(s, html_txt)
                print(f"  saved AA -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
            aa_map = bc.parse_aa(html_txt, verbose=verbose)
            print(f"  AA: {len(aa_map)} models")
        else:
            print("  WARN AA fetch failed", file=sys.stderr)

    # ---- 3. LMArena ----
    lm_map = {}
    if not do_fetch:
        snap = pick_latest_raw("lmarena")
        if snap:
            try:
                lm_map = bc.parse_lmarena(snap.read_text(errors="ignore"), verbose=verbose)
            except Exception as e:  # noqa: BLE001
                print(f"  WARN LMArena offline parse: {e}", file=sys.stderr)
            print(f"  LMArena: {len(lm_map)} entries ({snap.name}{bc.staleness_tag(snap)})")
        else:
            print("  LMArena: no cached snapshot available — run with --fetch once to populate")
    else:
        body = bc.fetch_url(LMARENA_URL, timeout=20)
        if body:
            html_txt = body if isinstance(body, str) else body.decode(errors="ignore")
            if do_write:
                s = RAW / f"lmarena_{dt.date.today().isoformat().replace('-', '')}.html"
                bc.atomic_write_text(s, html_txt)
                print(f"  saved LMArena -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
            lm_map = bc.parse_lmarena(html_txt, verbose=verbose)
            print(f"  LMArena: {len(lm_map)} entries")
        else:
            print("  WARN LMArena fetch failed", file=sys.stderr)

    # ---- 4. merge: attach intelligence to each free model ----
    rows = []
    for rec in free_recs:
        oid = rec.get("id", "") or ""
        b_id = base_id(oid)
        # AA lookup — provider-stripped base is the canonical slug; try it first
        aa_rec = bc.find_aa_for_model(b_id, aa_map) or bc.find_aa_for_model(oid, aa_map) if aa_map else None
        lm_rec = bc.find_lm_for_model(b_id, lm_map) or bc.find_lm_for_model(oid, lm_map) if lm_map else None

        aa_int = _safe_float(aa_rec.get("intelligenceIndex")) if aa_rec else None
        aa_cod = _safe_float(aa_rec.get("codingIndex")) if aa_rec else None
        aa_age = _safe_float(aa_rec.get("agenticIndex")) if aa_rec else None
        aa_tps = _safe_float(aa_rec.get("medianOutputTokensPerSecond")) if aa_rec else None
        aa_ctx = _safe_int(aa_rec.get("contextWindowTokens")) if aa_rec else None
        aa_slug = str(aa_rec.get("slug") or "") if aa_rec and not str(aa_rec.get("slug", "")).startswith("$") else None

        lm_elo = _safe_float(lm_rec.get("elo")) if lm_rec else None
        lm_rank = _safe_int(lm_rec.get("rank")) if lm_rec else None
        lm_votes = _safe_int(lm_rec.get("votes")) if lm_rec else None

        or_ctx = rec.get("context_length")
        src = rec.get("_source", "OC")
        if src == "CLN":
            provider = "cline"
        else:
            provider = "opencode"

        coverage = []
        if aa_int is not None:
            coverage.append("AA")
        if lm_elo is not None:
            coverage.append("LM")
        if not coverage:
            coverage = ["\u2014"]

        # provider column already shows it — strip "provider/" prefix from display
        display_short = b_id.split("/")[-1] if "/" in b_id else b_id
        rows.append(
            {
                "model_id": oid,
                "display": display_short,
                "display_full": b_id,
                "provider": provider,
                "source": src.lower(),  # "oc" / "cln" provenance for the src column
                "stealth": is_stealth_model(rec),
                "also_listed": sorted(set(rec.get("_also", []))),  # S3-F3-3 provenance merge marker

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
                    "openrouter_context": or_ctx,
                },
                "coverage": coverage,
            }
        )

    # ---- 5. normalized composite — mean of available z-scores ----
    aa_vals, lm_vals, aa_mean, aa_std, lm_mean, lm_std = compute_meanfill_composite(rows)

    if aa_vals:
        print(f"  AA Intelligence across {len(aa_vals)} free models: mean {aa_mean:.1f}  std {aa_std:.2f}")
    if lm_vals:
        print(f"  LMArena ELO across {len(lm_vals)} free models: mean {lm_mean:.1f}  std {lm_std:.2f}")
    if not aa_vals and not lm_vals:
        print("  Note: no free model found on AA or LMArena — composites will be \u2014", file=sys.stderr)
        print("  OpenRouter has no public bulk intelligence metric (per this repo's finding) — composite falls back to ordering by OR context.", file=sys.stderr)

    for r in rows:
        b = r["benchmarks"]
        if b["capability_q"] is not None:
            q_score = b["capability_q"]
            p_succ = compute_p_success(q_score)
            b["p_success"] = p_succ
            t_mult = compute_token_multiplier(p_succ)
            b["token_multiplier"] = t_mult
            fgi = compute_fgi(q_score, p_succ)
            b["fgi_score"] = fgi
        else:
            b["p_success"] = None
            b["token_multiplier"] = None
            b["fgi_score"] = None

    rows_sorted = sorted(rows, key=comp_key)
    n_aa = sum(1 for r in rows if r["benchmarks"]["aa_intelligence"] is not None)
    n_lm = sum(1 for r in rows if r["benchmarks"]["lmarena_elo"] is not None)

    # Load previous baseline snapshot for catalog diffing (additions in green, removals in red)
    # fcheck's own payload has no is_docs_model tag; require_docs_tag=False so the
    # previous free-models rows actually populate the baseline map (S3-F3-2).
    prev_snapshot = load_previous_snapshot(DATA / "free_models.json")
    catalog_diff = diff_model_catalog(rows_sorted, prev_snapshot, id_key="model_id", require_docs_tag=False)
    added_ids = catalog_diff["added_ids"]
    removed_ids = catalog_diff["removed_ids"]
    removed_models = catalog_diff["removed_models"]

    # ---- 6. console table (always, the default output) ----
    print("")
    print(render_cli_table(rows_sorted, color=color, is_slim=is_slim, is_wide=is_wide, n_aa=n_aa, n_lm=n_lm, added_ids=added_ids, removed_models=removed_models))

    # ---- 7. file outputs (only when --json/--html and not --check) ----
    if not do_write:
        print("\n(check-only, no files written)")
        return
    if args.json:
        OUT.mkdir(parents=True, exist_ok=True)
        DATA.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sources": {
                "openrouter_api": OPENROUTER_API,
                "opencode_zen_api": OPENCODE_ZEN_API,
                "opencode_go_api": OPENCODE_GO_API,
                "cline_recommended_models_api": CLINE_RECOMMENDED_MODELS_API,
                "cline_freemodel_api": CLINE_FREEMODEL_API,
                "artificial_analysis": AA_URL,
                "lmarena": LMARENA_URL,
                "note": "free = OpenCode Zen/Go -free tiers + Cline Free tier (OpenRouter list NOT shown; OR catalog fetched only to validate Cline free claims + price/context); composite = mean of per-source z-scores (AA Intelligence Index, LMArena ELO); cross-source scales incomparable",
            },
            "catalog_diff": {
                "added": sorted(list(added_ids)),
                "removed": sorted(list(removed_ids)),
                "total_current": len(rows_sorted),
                "total_previous": len(prev_snapshot.get("models", [])) if isinstance(prev_snapshot, dict) else len(rows_sorted),
            },
            "n_free": len(rows_sorted),
            "n_with_aa": n_aa,
            "n_with_lm": n_lm,
            "models": rows_sorted,
        }
        p = DATA / "free_models.json"
        bc.atomic_write_text(p, json.dumps(payload, indent=2))
        print(f"\nwrote {p.relative_to(ROOT)}")
    if args.html:
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / "free_models.html"
        bc.atomic_write_text(p, render_html(rows_sorted, n_aa, n_lm, added_ids=added_ids, removed_models=removed_models))
        print(f"wrote {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
