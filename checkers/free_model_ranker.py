#!/usr/bin/env python3
"""
free_model_ranker.py — Free models (OpenCode Zen/Go + Cline) ranked by composite intelligence

Reads the OpenCode Zen/Go free-tier ids (`-free` naming) and the Cline
Recommended-Models free tier from the raw cache and lists those models.
OpenRouter catalog is loaded only to validate Cline free claims and supply
price/context enrichment — OpenRouter-only free models are never listed.
Offline by default; --fetch is the only network path.
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
    C_GOLD,
    C_GREEN,
    C_MAGENTA,
    C_RED,
    C_RESET,
    C_WHITE,
    C_YELLOW,
    CLINE_RECOMMENDED_MODELS_API,
    HTML_CSS_COMMON,
    HTML_SORT_SCRIPT,
    LMARENA_URL,
    OPENCODE_GO_API,
    OPENCODE_ZEN_API,
    OPENROUTER_API,
    _safe_float,
    _safe_int,
    base_id,
    comp_key,
    compute_fgi,
    compute_meanfill_composite,
    compute_p_success,
    compute_token_multiplier,
    diff_model_catalog,
    is_stealth_model,
    load_previous_snapshot,
    medal_badge,
    norm_id,
    pool_badge,
    render_removed_models_cli,
    score_color_fgi,
    score_color_p,
    score_color_q,
)

_SRC_BADGE_CLASS = {"oc": "badge-ocg", "cln": "badge-cln", "stl": "badge-stl"}
_HEADER_WIDE = [
    ("Rank", 4, "^"), ("Model", 26, "<"), ("Provider", 12, "<"), ("Src", 5, "^"),
    ("Q(Cap)", 6, ">"), ("P(Succ)", 7, ">"), ("FGI", 5, ">"), ("AA Intel", 8, ">"),
    ("LM ELO", 7, ">"), ("Comp", 6, ">"), ("Cov", 5, "^"), ("Ctx", 5, ">"),
]
_HEADER_SLIM = [
    ("Rank", 4, "^"), ("Model", 18, "<"), ("Src", 5, "^"), ("Q(Cap)", 6, ">"),
    ("P(Succ)", 7, ">"), ("FGI", 5, ">"), ("Cov", 5, "^"), ("Ctx", 5, ">"),
]
_HEADER_COMPACT = [
    ("Rank", 4, "^"), ("Model", 22, "<"), ("Provider", 10, "<"), ("Src", 5, "^"),
    ("Q(Cap)", 6, ">"), ("P(Succ)", 7, ">"), ("FGI", 5, ">"), ("Cov", 5, "^"), ("Ctx", 5, ">"),
]


def is_free_model(rec: dict) -> bool:
    """OpenRouter pricing $0 or ':free' suffix -> free."""
    oid = rec.get("id", "") or ""
    if oid.endswith(":free"):
        return True
    p = rec.get("pricing")
    if not isinstance(p, dict) or p.get("prompt") is None or p.get("completion") is None:
        return False
    try:
        return float(p["prompt"]) == 0.0 and float(p["completion"]) == 0.0
    except (ValueError, TypeError):
        return False


def _free_key(oid: str) -> str:
    """Provider-stripped dedup key across OpenCode and OpenRouter/Cline ids."""
    return norm_id(base_id(oid).rsplit("/", 1)[-1])


def pick_latest_raw(name_part: str) -> pathlib.Path | None:
    """Newest snapshot in docs/data/raw/ whose name contains name_part, or None."""
    return bc.pick_latest_raw(RAW, name_part)


def fetch_or_load_cached_json(
    api_url: str,
    snapshot_prefix: str,
    fetch: bool = False,
    write: bool = True,
    verbose: bool = False,
) -> dict | list | None:
    """Offline-by-default JSON snapshot loader shared via benchmark_common."""
    return bc.fetch_or_load_json_snapshot(RAW, ROOT, api_url, snapshot_prefix, fetch=fetch, write=write, verbose=verbose)


def _fmt_num(val, spec: str, prefix: str = "", suffix: str = "") -> str:
    return f"{prefix}{val:{spec}}{suffix}" if bc._is_num(val) else "—"


def _render_html_row(r: dict, added_ids: set, top_id: str | None) -> str:
    is_added = (r.get("model_id") in added_ids) or (r.get("display") in added_ids)
    b = r["benchmarks"]
    raw_mid = html.escape(r["display"])
    mid = f'{raw_mid}<span class="badge badge-new">+NEW</span>' if is_added else raw_mid
    prov = html.escape(r.get("provider", ""))
    src_raw = r.get("source", "oc")
    src = f'<span class="badge {_SRC_BADGE_CLASS.get(src_raw, "badge-ocg")}">{html.escape(src_raw.upper())}</span>'
    stl = ' <span class="badge badge-stl">STEALTH</span>' if r.get("stealth") else ""
    ctx_val = b.get("openrouter_context")
    ctx = f"{int(ctx_val) // 1000}k" if bc._is_num(ctx_val) else "—"
    lm_rk = b.get("lmarena_rank")
    rk = f"#{lm_rk}" if isinstance(lm_rk, int) else "—"
    cls_parts = ["added"] if is_added else []
    if r["model_id"] == top_id:
        cls_parts.append("top-row")
    cls = f" class='{' '.join(cls_parts)}'" if cls_parts else ""
    return (
        f"<tr{cls}>"
        f'<td class="m">{mid}{stl}</td><td>{prov}</td><td>{src}</td>'
        f'<td class="n" style="font-weight:700; color:#3fb950;">{_fmt_num(b.get("capability_q"), ".1f")}</td>'
        f'<td class="n">{_fmt_num(b.get("p_success"), ".1f", suffix="%")}</td>'
        f'<td class="n" style="font-weight:700; color:#a371f7;">{_fmt_num(b.get("fgi_score"), ".1f")}</td>'
        f'<td class="n">{_fmt_num(b.get("aa_intelligence"), ".1f")}<span class="mid">{html.escape(b.get("aa_slug") or "")}</span></td>'
        f'<td class="n">{_fmt_num(b.get("aa_coding"), ".1f")}</td>'
        f'<td class="n">{_fmt_num(b.get("aa_agentic"), ".1f")}</td>'
        f'<td class="n">{_fmt_num(b.get("lmarena_elo"), ".0f")}</td><td class="n">{rk}</td>'
        f'<td class="n" style="font-weight:700; color:#58a6ff;">{_fmt_num(r.get("composite"), ".2f")}</td>'
        f'<td>{"·".join(r.get("coverage", ["—"]))}</td><td class="n">{ctx}</td>'
        "</tr>"
    )


def _render_removed_html(removed_models: list[dict]) -> str:
    if not removed_models:
        return ""
    tags = []
    for rm in removed_models:
        rm_id = html.escape(rm.get("display") or rm.get("model_id", "unknown"))
        prov = html.escape(rm.get("provider", "unknown"))
        q_val = (rm.get("benchmarks") or {}).get("capability_q")
        q_s = f"Q {q_val:.1f}" if bc._is_num(q_val) else "Q —"
        tags.append(f'<span class="removed-tag">❌ <b>{rm_id}</b> <span class="mid">({prov}, {q_s})</span></span>')
    return (
        '<div class="removed-section">'
        f'<div class="removed-title">🔻 Removed / Deprecated Free Models ({len(removed_models)})</div>'
        '<div class="sub" style="margin-bottom:8px;">These models were present in the previous free model catalog snapshot but are no longer active in the current OpenCode or Cline free tier:</div>'
        f'<div>{"".join(tags)}</div></div>'
    )


def render_html(rows, n_aa, n_lm, added_ids=None, removed_models=None):
    added = added_ids or set()
    removed = removed_models or []
    title = f"Free Models (OpenCode Zen/Go + Cline) — Composite Intelligence ({dt.date.today().isoformat()})"
    top_id = rows[0]["model_id"] if rows and rows[0].get("composite") is not None else None
    trs = [_render_html_row(r, added, top_id) for r in rows]
    removed_html = _render_removed_html(removed)
    top_disp = html.escape(rows[0]["display"]) if rows and rows[0].get("composite") is not None else "none"
    now_str = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    body = f"""
<div class="wrap">
<h1>{html.escape(title)}</h1>
<p class="sub">Free models (<b>OpenCode Zen/Go</b> <code>-free</code> tiers + <b>Cline</b> Free tier — OpenRouter-only free models are not listed) ranked by normalized composite intelligence = mean of z-scored <a href="https://artificialanalysis.ai/leaderboards/models">Artificial Analysis</a> Intelligence Index and <a href="https://arena.ai/leaderboard/text">Arena.ai</a> ELO. <b>{len(rows)}</b> free models · <b>{n_aa}</b> on AA · <b>{n_lm}</b> on Arena · Generated {now_str}</p>
<div class="card"><b>How to read:</b> <span class="badge badge-gold">TOP LEADER</span> = highest composite intelligence · <b>Q(Cap)</b> = Composite Capability (40–99.9) · <b>P(Succ)</b> = 1-turn pass rate · <b>FGI (Gate)</b> = Frontier Gate Index. AA Intelligence/Coding/Agentic from artificialanalysis.ai; Arena rank/ELO from arena.ai text leaderboard; context from OpenRouter. Cross-source scales are z-scored per source and averaged.</div>
<div class="card">
<table id="tbl">
<thead><tr><th>model</th><th>provider</th><th>src</th><th>Q(Cap)</th><th>P(Succ)</th><th>FGI (Gate)</th><th>AA intel</th><th>AA cod</th><th>AA agent</th><th>LM ELO</th><th>LM rank</th><th>composite</th><th>coverage</th><th>ctx</th></tr></thead>
<tbody>{''.join(trs)}</tbody>
</table>
<div class="legend">Click headers to sort. — = not on that leaderboard. <span class="badge badge-stl">STEALTH</span> = OpenRouter anonymous namespace (<code>stealth/…</code>).</div>
</div>
{removed_html}
<div class="footer"><span class="path">docs/reports/free_models.html</span><span class="work">Composite rank of {len(rows)} free models ({n_aa} on AA, {n_lm} on LMArena — top: {top_disp}).</span></div>
</div>
{HTML_SORT_SCRIPT}
"""
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{HTML_CSS_COMMON}</style></head><body>{body}</body></html>"


def _row_model_color(rank_num: int, is_added: bool, is_stealth: bool) -> str:
    if is_added:
        return C_BOLD + C_GREEN
    if rank_num == 1:
        return C_BOLD + C_GOLD
    return C_MAGENTA if is_stealth else C_WHITE


def _cli_row_cells(
    idx: int,
    r: dict,
    meds: dict,
    added_ids: set,
    color: bool,
    is_slim: bool,
    is_wide: bool,
) -> list[tuple[str, str, int, str]]:
    rank_num = idx + 1
    rank_str, rank_col = bc.rank_label_and_color(rank_num)
    b = r["benchmarks"]
    q_val, p_val, fgi_val = b.get("capability_q"), b.get("p_success"), b.get("fgi_score")
    comp_val = r.get("composite")
    ctx_val = b.get("openrouter_context")

    m_w, p_w = (26, 12) if is_wide else ((18, 0) if is_slim else (22, 10))
    is_added = (r.get("model_id") in added_ids) or (r.get("display") in added_ids)
    is_stealth = bool(r.get("stealth"))
    m_name = (f"+{r['display']}" if is_added else r["display"])[:m_w]
    src_badge_str = pool_badge("stl" if is_stealth else r.get("source", "oc"), color=color)

    cells: list[tuple[str, str, int, str]] = [
        (rank_str, rank_col, 4, "^"),
        (m_name, _row_model_color(rank_num, is_added, is_stealth), m_w, "<"),
    ]
    if p_w > 0:
        cells.append((r["provider"][:p_w], C_WHITE, p_w, "<"))
    cells.extend([
        (src_badge_str, "", 5, "^"),
        (_fmt_num(q_val, ".1f") + medal_badge(meds.get("q"), color=color), score_color_q(q_val), 6, ">"),
        (_fmt_num(p_val, ".1f", suffix="%") + medal_badge(meds.get("psucc"), color=color), score_color_p(p_val), 7, ">"),
        (_fmt_num(fgi_val, ".1f") + medal_badge(meds.get("fgi"), color=color), score_color_fgi(fgi_val), 5, ">"),
    ])
    if is_wide:
        cells.extend([
            (_fmt_num(b.get("aa_intelligence"), ".1f"), C_WHITE, 8, ">"),
            (_fmt_num(b.get("lmarena_elo"), ".0f"), C_WHITE, 7, ">"),
            (_fmt_num(comp_val, ".2f"), C_BOLD + C_CYAN if comp_val is not None else C_DIM, 6, ">"),
        ])
    ctx_s = f"{int(ctx_val) // 1000}k" if bc._is_num(ctx_val) else "—"
    cells.extend([("·".join(r.get("coverage", ["—"])), C_DIM, 5, "^"), (ctx_s, C_CYAN, 5, ">")])
    return cells


def _diff_banner_notices(added_ids: set, removed_models: list[dict]) -> tuple[list[str], list[str]]:
    notices: list[str] = []
    parts: list[str] = []
    if added_ids:
        names = ", ".join(sorted(added_ids))
        notices.append(f"{C_BOLD}{C_GREEN}✨ New (+{len(added_ids)}): {names}{C_RESET}")
        parts.append(f"[+NEW (+{len(added_ids)}): {names}]")
    if removed_models:
        rem = ", ".join(m.get("display") or m.get("model_id", "unknown") for m in removed_models)
        notices.append(f"{C_BOLD}{C_RED}🔻 Removed (-{len(removed_models)}): {rem}{C_RESET}")
        parts.append(f"[-REMOVED (-{len(removed_models)}): {rem}]")
    return notices, parts


def _banner_summary(rows_sorted: list[dict], n_aa: int, n_lm: int, is_slim: bool) -> str:
    top_model = rows_sorted[0] if rows_sorted and rows_sorted[0].get("composite") is not None else None
    top_info = f"Top: {top_model['display'][:14]} (Q {top_model['benchmarks'].get('capability_q', 0):.1f})" if top_model else ""
    if is_slim:
        return f" Tracked: {len(rows_sorted)} free models │ {top_info}"
    return f" Tracked: {len(rows_sorted)} free models │ AA data: {n_aa} │ Arena data: {n_lm} │ {top_info}"


def _append_removed_and_guide(out: list[str], removed: list[dict], color: bool, is_slim: bool) -> None:
    if removed:
        out.extend(["", *render_removed_models_cli(removed, color=color, is_slim=is_slim, id_key="display")])
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


_FREE_MEDAL_COLS = {
    "q": (lambda r: r["benchmarks"].get("capability_q") or 0, True, None),
    "psucc": (lambda r: r["benchmarks"].get("p_success") or 0, True, None),
    "fgi": (lambda r: r["benchmarks"].get("fgi_score") or 0, True, None),
}


def _select_headers(is_wide: bool, is_slim: bool) -> list[tuple[str, int, str]]:
    if is_wide:
        return _HEADER_WIDE
    return _HEADER_SLIM if is_slim else _HEADER_COMPACT


def render_cli_table(rows_sorted, color=True, is_slim=False, is_wide=False, n_aa=0, n_lm=0, added_ids=None, removed_models=None):
    """Render structured TUI table with adaptive terminal width and alternating row zebra striping."""
    added = added_ids or set()
    removed = removed_models or []
    headers = _select_headers(is_wide, is_slim)
    inner_w = sum(w + 2 for _, w, _ in headers) + len(headers) - 1
    col_medals = bc.compute_column_medals(rows_sorted, _FREE_MEDAL_COLS, id_key="model_id")
    diff_notices, diff_parts = _diff_banner_notices(added, removed)
    out = bc.render_banner_box(
        "⚡ FREE MODEL RADAR (OpenCode Zen/Go + Cline Free Tiers)",
        summary_lines=[_banner_summary(rows_sorted, n_aa, n_lm, is_slim)],
        diff_notices=diff_notices,
        inner_w=inner_w,
        color=color,
        plain_title_line=f" FREE MODEL RADAR (OpenCode Zen/Go + Cline) — Tracked: {len(rows_sorted)} free models",
        plain_diff_parts=diff_parts,
    )
    styled = [_cli_row_cells(i, r, col_medals.get(r.get("model_id"), {}), added, color, is_slim, is_wide) for i, r in enumerate(rows_sorted)]
    out.extend(bc.render_styled_cli_table(headers, styled, color=color))
    _append_removed_and_guide(out, removed, color, is_slim)
    return "\n".join(out)


def _index_or_free(or_map: dict) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    for orid, orrec in or_map.items():
        if not is_free_model(orrec):
            continue
        key = _free_key(orid)
        cur = by_key.get(key)
        if cur is None or (orid.endswith(":free") and not cur["id"].endswith(":free")):
            by_key[key] = orrec
    return by_key


def _is_opencode_free_id(mid: str) -> bool:
    low = mid.lower()
    # ponytail: naming convention only <- Zen /v1/models entries carry no pricing field -> reinstate real price check if upstream ships pricing
    return "-free" in low or low in ("big-pickle", "ox-alpha-free")


def _extract_oc_free_ids(oc_zen_json, oc_go_json) -> list[str]:
    oc_ids: list[str] = []
    for payload in (oc_zen_json, oc_go_json):
        if not isinstance(payload, dict):
            continue
        for m in payload.get("data") or []:
            mid = m.get("id", "") if isinstance(m, dict) else ""
            if mid and _is_opencode_free_id(mid) and mid not in oc_ids:
                oc_ids.append(mid)
    return oc_ids


def _make_free_record(mid: str, source: str, or_rec: dict | None, fallback_ctx=None) -> dict:
    ctx = or_rec.get("context_length") if or_rec else fallback_ctx
    pricing = (or_rec.get("pricing") if or_rec else None) or {"prompt": "0", "completion": "0"}
    return {"id": mid, "context_length": ctx, "pricing": pricing, "_source": source}


def _collect_opencode_free(oc_zen_json, oc_go_json, or_free_by_key: dict[str, dict], listed: dict[str, dict]) -> list[dict]:
    oc_ids = _extract_oc_free_ids(oc_zen_json, oc_go_json)
    out: list[dict] = []
    merged = enriched = 0
    for oid in oc_ids:
        k = _free_key(oid)
        if k in listed:
            listed[k].setdefault("_also", []).append("oc")
            merged += 1
            continue
        or_rec = or_free_by_key.get(k)
        rec = _make_free_record(oid, "OC", or_rec)
        enriched += int(or_rec is not None)
        out.append(rec)
        listed[k] = rec
    if oc_ids:
        print(f"  OpenCode free: {len(oc_ids)} found ({', '.join(oc_ids)}), {len(out)} added new ({enriched} price/ctx via OR), {merged} merged into existing rows")
    else:
        print("  OpenCode free: none found")
    return out


def _extract_cline_entries(cline_json) -> list[tuple[str, dict | None]]:
    raw = cline_json.get("free", cline_json.get("data", [])) if isinstance(cline_json, dict) else cline_json
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    entries: list[tuple[str, dict | None]] = []
    for m in raw:
        rec = m if isinstance(m, dict) else None
        mid = rec.get("id", "") if rec else str(m)
        if mid and mid not in seen:
            seen.add(mid)
            entries.append((mid, rec))
    return entries


def _collect_cline_free(cline_json, or_free_by_key: dict[str, dict], listed: dict[str, dict]) -> list[dict]:
    entries = _extract_cline_entries(cline_json)
    out: list[dict] = []
    merged = 0
    skipped: list[str] = []
    for cid, crec in entries:
        k = _free_key(cid)
        if k in listed:
            listed[k].setdefault("_also", []).append("cln")
            merged += 1
            continue
        or_rec = or_free_by_key.get(k)
        if not is_free_model(or_rec or crec or {"id": cid}):
            skipped.append(cid)
            continue
        fallback_ctx = crec.get("context_length") if crec else None
        rec = _make_free_record(cid, "CLN", or_rec, fallback_ctx=fallback_ctx)
        out.append(rec)
        listed[k] = rec
    if entries:
        skip_note = f" ({len(skipped)} dropped as not-free per validation: {', '.join(skipped)})" if skipped else ""
        print(f"  Cline free: {len(entries)} found, {len(out)} added new ({merged} merged into existing rows){skip_note}")
    else:
        print("  Cline free: none found")
    return out


def _free_bench_dict(b_id: str, oid: str, aa_map: dict, lm_map: dict, or_ctx) -> dict:
    aa = (bc.find_aa_for_model(b_id, aa_map) or bc.find_aa_for_model(oid, aa_map) or {}) if aa_map else {}
    lm = (bc.find_lm_for_model(b_id, lm_map) or bc.find_lm_for_model(oid, lm_map) or {}) if lm_map else {}
    slug_raw = str(aa.get("slug") or "")
    return {
        "aa_slug": slug_raw if slug_raw and not slug_raw.startswith("$") else None,
        "aa_intelligence": _safe_float(aa.get("intelligenceIndex")),
        "aa_coding": _safe_float(aa.get("codingIndex")),
        "aa_agentic": _safe_float(aa.get("agenticIndex")),
        "aa_median_tps": _safe_float(aa.get("medianOutputTokensPerSecond")),
        "aa_context": _safe_int(aa.get("contextWindowTokens")),
        "lmarena_rank": _safe_int(lm.get("rank")),
        "lmarena_elo": _safe_float(lm.get("elo")),
        "lmarena_votes": _safe_int(lm.get("votes")),
        "openrouter_context": or_ctx,
    }


def _build_free_row(rec: dict, aa_map: dict, lm_map: dict) -> dict:
    oid = rec.get("id", "") or ""
    b_id = base_id(oid)
    bench = _free_bench_dict(b_id, oid, aa_map, lm_map, rec.get("context_length"))
    src = rec.get("_source", "OC")
    cov = [tag for tag, val in (("AA", bench["aa_intelligence"]), ("LM", bench["lmarena_elo"])) if val is not None]
    return {
        "model_id": oid,
        "display": b_id.split("/")[-1],
        "display_full": b_id,
        "provider": "cline" if src == "CLN" else "opencode",
        "source": src.lower(),
        "stealth": is_stealth_model(rec),
        "also_listed": sorted(set(rec.get("_also", []))),
        "benchmarks": bench,
        "coverage": cov or ["—"],
    }


def _score_free_rows(rows: list[dict]) -> tuple[int, int]:
    aa_vals, lm_vals, aa_mean, aa_std, lm_mean, lm_std = compute_meanfill_composite(rows)
    if aa_vals:
        print(f"  AA Intelligence across {len(aa_vals)} free models: mean {aa_mean:.1f}  std {aa_std:.2f}")
    if lm_vals:
        print(f"  LMArena ELO across {len(lm_vals)} free models: mean {lm_mean:.1f}  std {lm_std:.2f}")
    if not aa_vals and not lm_vals:
        print("  Note: no free model found on AA or LMArena — composites will be —", file=sys.stderr)
        print("  OpenRouter has no public bulk intelligence metric — composite falls back to OR context.", file=sys.stderr)

    for r in rows:
        b = r["benchmarks"]
        q = b["capability_q"]
        if q is None:
            b["p_success"] = b["token_multiplier"] = b["fgi_score"] = None
            continue
        p_succ = compute_p_success(q)
        b["p_success"] = p_succ
        b["token_multiplier"] = compute_token_multiplier(p_succ)
        b["fgi_score"] = compute_fgi(q, p_succ)
    return (
        sum(1 for r in rows if r["benchmarks"]["aa_intelligence"] is not None),
        sum(1 for r in rows if r["benchmarks"]["lmarena_elo"] is not None),
    )


def _write_free_outputs(args, rows_sorted, n_aa: int, n_lm: int, added_ids: set, removed_ids: set, removed_models: list, prev_snapshot) -> None:
    if (args.json or args.html) and not rows_sorted:
        print("  ERROR: Free model catalog yielded 0 records — refusing --json/--html write", file=sys.stderr)
        sys.exit(1)
    if args.json:
        OUT.mkdir(parents=True, exist_ok=True)
        DATA.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "sources": {
                "openrouter_api": OPENROUTER_API,
                "opencode_zen_api": OPENCODE_ZEN_API,
                "opencode_go_api": OPENCODE_GO_API,
                "cline_recommended_models_api": CLINE_RECOMMENDED_MODELS_API,
                "artificial_analysis": AA_URL,
                "lmarena": LMARENA_URL,
                "note": "free = OpenCode Zen/Go -free tiers + Cline Free tier (OpenRouter list NOT shown; OR catalog fetched only to validate Cline free claims + price/context); composite = mean of per-source z-scores (AA Intelligence Index, LMArena ELO); cross-source scales incomparable",
            },
            "catalog_diff": {
                "added": sorted(added_ids),
                "removed": sorted(removed_ids),
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


def _parse_args():
    ap = argparse.ArgumentParser(
        description="OpenCode Zen/Go + Cline free models ranked by composite intelligence (AA Index + LMArena ELO, z-scored)"
    )
    ap.add_argument("--fetch", action="store_true", help="network path: live-fetch OpenRouter/Zen/Go/Cline/AA/LMArena and save dated snapshots")
    ap.add_argument("--check", action="store_true", help="print only: writes NOTHING (data/html outputs, raw snapshots) — even combined with --fetch")
    ap.add_argument("--json", action="store_true", help="write docs/data/free_models.json")
    ap.add_argument("--html", action="store_true", help="write docs/reports/free_models.html")
    ap.add_argument("--verbose", action="store_true", help="verbose fetch logging")
    ap.add_argument("--plain", "--no-color", action="store_true", help="Disable ANSI colors and box drawing")
    ap.add_argument("--slim", action="store_true", help="Force compact table layout for split panes")
    ap.add_argument("--wide", action="store_true", help="Force wide table layout")
    return ap.parse_args()


def main():
    args = _parse_args()
    verbose, do_fetch, do_write = bool(args.verbose), bool(args.fetch), not bool(args.check)
    color = not bool(args.plain or os.getenv("NO_COLOR"))
    term_cols = shutil.get_terminal_size((120, 24)).columns
    is_wide = bool(args.wide)
    is_slim = bool(args.slim or (term_cols < 95 and not is_wide))

    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    print("Free models (OpenCode Zen/Go + Cline) — composite intelligence")
    print(f"  date: {dt.datetime.now(dt.UTC).isoformat()}")
    print(f"  mode: {'fetch (network)' if do_fetch else 'OFFLINE (cache-only)'}" + (" · check: no writes" if args.check else ""))

    or_json = fetch_or_load_cached_json(OPENROUTER_API, "openrouter_models", fetch=do_fetch, write=do_write, verbose=verbose)
    or_map = bc.parse_openrouter(or_json, verbose=verbose) if isinstance(or_json, dict) else {}
    or_free_by_key = _index_or_free(or_map)
    print(f"  OR catalog: {len(or_map)} models loaded, {len(or_free_by_key)} free keys (validation + price/context only — not listed)")

    oc_zen = fetch_or_load_cached_json(OPENCODE_ZEN_API, "opencode_zen_models", fetch=do_fetch, write=do_write, verbose=verbose)
    oc_go = fetch_or_load_cached_json(OPENCODE_GO_API, "opencode_go_models", fetch=do_fetch, write=do_write, verbose=verbose)
    listed: dict[str, dict] = {}
    free_recs = _collect_opencode_free(oc_zen, oc_go, or_free_by_key, listed)

    cline_json = fetch_or_load_cached_json(CLINE_RECOMMENDED_MODELS_API, "cline_models", fetch=do_fetch, write=do_write, verbose=verbose)
    free_recs.extend(_collect_cline_free(cline_json, or_free_by_key, listed))
    free_recs.sort(key=lambda r: r.get("id", ""))
    print(f"  free total: {len(free_recs)}")

    aa_map = bc.fetch_or_load_aa(RAW, ROOT, fetch=do_fetch, write=do_write, verbose=verbose)
    lm_map = bc.fetch_or_load_lmarena(RAW, fetch=do_fetch, write=do_write, verbose=verbose)
    rows = [_build_free_row(rec, aa_map, lm_map) for rec in free_recs]
    n_aa, n_lm = _score_free_rows(rows)
    rows_sorted = sorted(rows, key=comp_key)

    prev_snapshot = load_previous_snapshot(DATA / "free_models.json")
    catalog_diff = diff_model_catalog(rows_sorted, prev_snapshot, id_key="model_id", require_docs_tag=False)
    rows_sorted = catalog_diff["rows"]

    print("")
    print(render_cli_table(
        rows_sorted,
        color=color,
        is_slim=is_slim,
        is_wide=is_wide,
        n_aa=n_aa,
        n_lm=n_lm,
        added_ids=catalog_diff["added_ids"],
        removed_models=catalog_diff["removed_models"],
    ))

    if not do_write:
        print("\n(check-only, no files written)")
        return
    _write_free_outputs(
        args,
        rows_sorted,
        n_aa,
        n_lm,
        catalog_diff["added_ids"],
        catalog_diff["removed_ids"],
        catalog_diff["removed_models"],
        prev_snapshot,
    )


if __name__ == "__main__":
    main()
