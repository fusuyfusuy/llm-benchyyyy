#!/usr/bin/env python3
"""
benchmark_tui.py — Zero-dependency interactive Terminal User Interface (TUI) for llm-benchyyyy.

Features:
- Responsive elastic table: dynamically adapts column count & widths to terminal size without border clipping.
- Focused Top 50 models cohort with dynamic role distribution & statistics.
- Tri-Verified (3/3) models only by default on main screen (toggled with 'e').
- Explicit pagination ('n' for next, 'p' for prev, '[' / ']', PgDn / PgUp).
- Zebra-striped alternating rows and bold gold ('⭐') Pareto frontier styling.
- Model capability inspection drawer ('Enter' / 'Space').
- Interactive Top 50 Role Distribution modal ('R').
- Side-by-side model comparison diff ('d') with custom baseline pinning ('b').
- Quick Pareto frontier filter ('P').
- Conflict-free single-key capability sorting ('c', 'r', 's', 'x', '$', 'v', 'S').
- Live search filter ('/') with real-time match count, and pool switching ('Tab' or '1'-'6').
- Direct atomic export to Markdown ('m') and HTML ('h').
"""
import curses
import dataclasses
import math
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA = ROOT / "docs" / "data"

import benchmark_common as bc
from benchmark_common import (
    extract_capability_pillars, format_context_window,
    compute_priced_pareto_frontier, compute_role_recommendations,
    pad_display, display_len,
)

POOLS = ["all", "agy", "claude", "ocgo", "frontier", "api"]
POOL_LABELS = {
    "all": "ALL",
    "agy": "AGY (Gemini)",
    "claude": "CLAUDE",
    "ocgo": "OPENCODE",
    "frontier": "FRONTIER",
    "api": "API",
}

SORT_KEYS = ["composite", "coding", "reasoning", "speed", "ctx", "price", "avi"]


@dataclasses.dataclass
class TUIState:
    all_models: list[dict]
    unmatched_models: list[dict]
    filtered_models: list[dict] = dataclasses.field(default_factory=list)
    top_cohort: list[dict] = dataclasses.field(default_factory=list)
    cursor_idx: int = 0
    page_idx: int = 0
    page_size: int = 15
    sort_key: str = "composite"
    sort_reverse: bool = True
    pool_filter: str = "all"
    tri_verified_only: bool = True       # Default: show only 3/3 models on main screen
    top_limit: int = 50                 # Focus on top 50 models
    pareto_only: bool = False           # Toggle: show only pareto frontier models
    search_query: str = ""
    searching: bool = False
    inspecting: bool = False            # Model detail drawer
    showing_roles: bool = False         # Top 50 Role distribution overlay
    showing_diff: bool = False          # Side-by-side comparison overlay
    diff_baseline_idx: int = 0          # Target baseline model to compare against (default: #1)
    showing_help: bool = False          # Keybindings & formulas guide
    status_msg: str = ""
    pareto_ids: set = dataclasses.field(default_factory=set)
    role_recs: dict = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        self.apply_filters()

    def apply_filters(self):
        """Apply active coverage filter, pool filter, search query, sorting, and Top 50 bound."""
        rows = list(self.all_models)

        # 1. Tri-Verified coverage filter (3/3 benchmarks present)
        if self.tri_verified_only:
            tri_rows = []
            for m in rows:
                pl = extract_capability_pillars(m)
                if pl.get("coverage_count") == 3:
                    tri_rows.append(m)
            rows = tri_rows

        # 2. Pool filter
        if self.pool_filter != "all":
            rows = [m for m in rows if (m.get("pool") or "").lower() == self.pool_filter]

        # 3. Search query
        if self.search_query.strip():
            q = self.search_query.strip().lower()
            rows = [
                m for m in rows
                if q in (m.get("display") or "").lower()
                or q in (m.get("provider") or "").lower()
                or q in (m.get("model_id") or "").lower()
            ]

        # 4. Sorting
        def sort_val(m):
            pl = extract_capability_pillars(m)
            if self.sort_key in ("composite", "q"):
                return m.get("capability_q") or 0.0
            elif self.sort_key == "coding":
                return pl.get("coding") or 0.0
            elif self.sort_key == "reasoning":
                return pl.get("reasoning") or 0.0
            elif self.sort_key == "speed":
                return pl.get("speed") or 0.0
            elif self.sort_key == "ctx":
                return pl.get("context_length") or 0
            elif self.sort_key == "price":
                p_in = m.get("price_in")
                return p_in if p_in is not None else 9999.0
            elif self.sort_key == "avi":
                return m.get("avi_score") or 0.0
            elif self.sort_key == "fgi":
                return m.get("fgi_score") or 0.0
            return m.get("capability_q") or 0.0

        rev = self.sort_reverse if self.sort_key != "price" else not self.sort_reverse
        rows.sort(key=sort_val, reverse=rev)

        # 5. Pareto frontier filter (if toggled)
        if self.pareto_only:
            active_pareto = compute_priced_pareto_frontier(rows)
            rows = [m for m in rows if m.get("display") in active_pareto]

        # 6. Bound to Top 50 cohort
        if self.top_limit and len(rows) > self.top_limit:
            rows = rows[:self.top_limit]

        self.filtered_models = rows
        self.top_cohort = list(rows)

        # 7. Recompute Pareto frontier & Role distribution strictly on active cohort
        self.pareto_ids = compute_priced_pareto_frontier(self.top_cohort)
        if len(self.top_cohort) >= 2:
            self.role_recs = compute_role_recommendations(self.top_cohort, context="bcheck")
        else:
            self.role_recs = {}

        # 8. Clamping baseline index
        if self.diff_baseline_idx >= len(self.filtered_models):
            self.diff_baseline_idx = 0

        # 9. Pagination clamping
        total_p = self.total_pages
        self.page_idx = max(0, min(self.page_idx, total_p - 1))
        if not self.filtered_models:
            self.cursor_idx = 0
        else:
            self.cursor_idx = max(0, min(self.cursor_idx, len(self.filtered_models) - 1))
            self.page_idx = self.cursor_idx // self.page_size

    @property
    def total_pages(self) -> int:
        if not self.filtered_models:
            return 1
        return max(1, math.ceil(len(self.filtered_models) / self.page_size))

    def move_cursor(self, delta: int):
        if not self.filtered_models:
            return
        self.cursor_idx = max(0, min(self.cursor_idx + delta, len(self.filtered_models) - 1))
        self.page_idx = self.cursor_idx // self.page_size

    def next_page(self):
        if self.page_idx < self.total_pages - 1:
            self.page_idx += 1
            self.cursor_idx = min(self.page_idx * self.page_size, len(self.filtered_models) - 1)
            self.status_msg = f"Page {self.page_idx + 1} of {self.total_pages}"

    def prev_page(self):
        if self.page_idx > 0:
            self.page_idx -= 1
            self.cursor_idx = self.page_idx * self.page_size
            self.status_msg = f"Page {self.page_idx + 1} of {self.total_pages}"

    def cycle_pool(self):
        idx = POOLS.index(self.pool_filter) if self.pool_filter in POOLS else 0
        self.pool_filter = POOLS[(idx + 1) % len(POOLS)]
        self.page_idx = 0
        self.cursor_idx = 0
        self.apply_filters()
        self.status_msg = f"Filtered pool: {POOL_LABELS.get(self.pool_filter, self.pool_filter.upper())}"

    def toggle_tri_verified(self):
        self.tri_verified_only = not self.tri_verified_only
        self.page_idx = 0
        self.cursor_idx = 0
        self.apply_filters()
        mode_label = "Tri-Verified (3/3 Only)" if self.tri_verified_only else "All Evaluated Models (3/3 · 2/3 · 1/3*)"
        self.status_msg = f"Coverage Filter: {mode_label}"

    def toggle_pareto_only(self):
        self.pareto_only = not self.pareto_only
        self.page_idx = 0
        self.cursor_idx = 0
        self.apply_filters()
        self.status_msg = "Focus: Pareto Frontier Only" if self.pareto_only else "Focus: All Cohort Models"

    def set_sort(self, key: str):
        if self.sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_key = key
            self.sort_reverse = True
        self.page_idx = 0
        self.cursor_idx = 0
        self.apply_filters()
        direction = "▼" if self.sort_reverse else "▲"
        self.status_msg = f"Sorted by {self.sort_key.upper()} {direction}"

    def cycle_sort(self):
        idx = SORT_KEYS.index(self.sort_key) if self.sort_key in SORT_KEYS else 0
        nxt = SORT_KEYS[(idx + 1) % len(SORT_KEYS)]
        self.set_sort(nxt)

    def pin_current_as_baseline(self):
        if self.filtered_models:
            self.diff_baseline_idx = self.cursor_idx
            disp = self.filtered_models[self.cursor_idx].get("display", "Model")
            self.status_msg = f"Pinned diff baseline: #{self.cursor_idx + 1} {disp[:22]}"


def init_colors():
    """Initialize curses color pairs for TUI."""
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    try:
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)    # Header bar
        curses.init_pair(2, curses.COLOR_GREEN, -1)                  # High score / Tri-verified / Ahead
        curses.init_pair(3, curses.COLOR_YELLOW, -1)                 # Pareto Gold / Medals
        curses.init_pair(4, curses.COLOR_CYAN, -1)                   # Speed / Roles / Baseline
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)                # Single source / Emerging
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)   # Active modal header
        curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Search input bar
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_YELLOW) # Selected Pareto Gold row
        curses.init_pair(9, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Subtle zebra odd row
    except Exception:
        pass


def safe_addstr(win, y, x, text, attr=0, boxed=False):
    """Write text to window safely with display width awareness without edge corruption."""
    max_y, max_x = win.getmaxyx()
    if y < 0 or y >= max_y or x < 0 or x >= max_x:
        return
    if boxed and x > 0:
        avail = max(0, max_x - 1 - x)
    elif y >= max_y - 1:
        avail = max(0, max_x - x - 1)
    else:
        avail = max(0, max_x - x)
    if avail <= 0:
        return
    text_to_write = text
    if display_len(text) > avail:
        text_to_write = pad_display(text, avail, align="<")
    try:
        win.addstr(y, x, text_to_write, attr)
    except curses.error:
        pass


def draw_modal(stdscr, model: dict, state: TUIState, max_y: int, max_x: int):
    """Draw model capability detail drawer overlay."""
    win_h = min(23, max(16, max_y - 2))
    win_w = min(86, max(56, max_x - 4))
    start_y = max(1, (max_y - win_h) // 2)
    start_x = max(2, (max_x - win_w) // 2)

    modal = curses.newwin(win_h, win_w, start_y, start_x)
    modal.erase()
    modal.box()

    disp = model.get("display") or model.get("model_id") or "Unknown"
    prov = model.get("provider") or "Unknown"
    pool = (model.get("pool") or "API").upper()
    pl = extract_capability_pillars(model)

    bm = model.get("base_metrics", {})
    lb = model.get("livebench", {}) if isinstance(model.get("livebench"), dict) else {}
    lb_cats = lb.get("categories", {}) if isinstance(lb, dict) else {}

    pos_info = f"[{state.cursor_idx + 1}/{len(state.filtered_models)}]"
    title = f" 🔍 {disp[:max(8, win_w - len(pos_info) - 10)]} {pos_info} "
    safe_addstr(modal, 0, 2, title, curses.A_BOLD | curses.color_pair(6), boxed=True)

    if win_w >= 78:
        safe_addstr(modal, 1, 2, f"Provider: {prov:<18} │ Pool: [{pool}] │ Tier: {model.get('tier', 'Standard')}", curses.A_DIM, boxed=True)
    else:
        safe_addstr(modal, 1, 2, f"Provider: {prov[:12]} │ Pool: [{pool}]", curses.A_DIM, boxed=True)

    pin, pout = model.get("price_in"), model.get("price_out")
    p_str = f"${pin:.2f} / ${pout:.2f}" if (pin is not None and pout is not None) else "—"
    ctx_str = format_context_window(pl.get("context_length"))
    spd_str = f"{pl.get('speed'):.0f} t/s" if pl.get("speed") else "—"
    if win_w >= 78:
        safe_addstr(modal, 2, 2, f"Context Window: {ctx_str:<8} │ Speed: {spd_str:<10} │ Price $/M: {p_str}", curses.A_NORMAL, boxed=True)
    else:
        safe_addstr(modal, 2, 2, f"Ctx: {ctx_str} │ Spd: {spd_str} │ $/M: {p_str}", curses.A_NORMAL, boxed=True)

    safe_addstr(modal, 3, 0, "├" + "─" * (win_w - 2) + "┤", curses.A_DIM, boxed=True)
    safe_addstr(modal, 4, 2, "📊 BENCHMARK EVALUATIONS", curses.A_BOLD | curses.color_pair(4), boxed=True)

    lb_overall = lb.get("overall")
    lb_ov_s = f"{lb_overall:.1f}%" if lb_overall is not None else "—"
    elo_g = bm.get("lm_elo")
    elo_c = bm.get("lm_coding")
    elo_g_s = f"{elo_g:.0f}" if isinstance(elo_g, (int, float)) else "—"
    elo_c_s = f"{elo_c:.0f}" if isinstance(elo_c, (int, float)) else "—"
    if win_w >= 78:
        safe_addstr(modal, 5, 4, f"• LiveBench Overall : {lb_ov_s:<8} │ LMSYS Arena Elo   : {elo_g_s} (Global) · Coding: {elo_c_s}", curses.A_NORMAL, boxed=True)
    else:
        safe_addstr(modal, 5, 4, f"• LiveBench: {lb_ov_s} │ LMSYS Arena: {elo_g_s} (Code: {elo_c_s})", curses.A_NORMAL, boxed=True)

    r_s = f"{lb_cats.get('Reasoning'):.1f}%" if lb_cats.get("Reasoning") is not None else "—"
    c_s = f"{lb_cats.get('Coding'):.1f}%" if lb_cats.get("Coding") is not None else "—"
    m_s = f"{lb_cats.get('Mathematics'):.1f}%" if lb_cats.get("Mathematics") is not None else "—"
    ag_s = f"{lb_cats.get('Agentic Coding'):.1f}%" if lb_cats.get("Agentic Coding") is not None else "—"

    if win_h >= 20:
        if win_w >= 78:
            safe_addstr(modal, 6, 6, f"- Reasoning       : {r_s:<8}  - Coding            : {c_s:<8}", curses.A_NORMAL, boxed=True)
            safe_addstr(modal, 7, 6, f"- Agentic SWE     : {ag_s:<8}  - Mathematics       : {m_s:<8}", curses.A_NORMAL, boxed=True)
        else:
            safe_addstr(modal, 6, 6, f"- Reasoning: {r_s} │ Coding: {c_s}", curses.A_NORMAL, boxed=True)
            safe_addstr(modal, 7, 6, f"- SWE: {ag_s} │ Math: {m_s}", curses.A_NORMAL, boxed=True)
        line_offset = 8
    else:
        safe_addstr(modal, 6, 6, f"- Reasoning: {r_s} │ Coding: {c_s} │ Agentic SWE: {ag_s}", curses.A_NORMAL, boxed=True)
        line_offset = 7

    aa_q = bm.get("aa_quality") or model.get("aa_live_quality")
    aa_c = bm.get("aa_coding") or model.get("aa_live_coding")
    aa_q_s = f"{aa_q:.1f}" if aa_q is not None else "—"
    aa_c_s = f"{aa_c:.1f}" if aa_c is not None else "—"
    if win_w >= 78:
        safe_addstr(modal, line_offset, 4, f"• Artificial Analysis Quality: {aa_q_s:<8} │ AA Coding: {aa_c_s}", curses.A_NORMAL, boxed=True)
    else:
        safe_addstr(modal, line_offset, 4, f"• AA Quality: {aa_q_s} │ AA Coding: {aa_c_s}", curses.A_NORMAL, boxed=True)

    safe_addstr(modal, line_offset + 1, 0, "├" + "─" * (win_w - 2) + "┤", curses.A_DIM, boxed=True)
    safe_addstr(modal, line_offset + 2, 2, "📐 AGENTIC ECONOMETRICS & VALUE", curses.A_BOLD | curses.color_pair(3), boxed=True)

    q_val = model.get("capability_q")
    q_s = f"{q_val:.1f}" if q_val is not None else "—"
    p_val = model.get("p_success")
    p_s = f"{p_val:.1f}%" if p_val is not None else "—"
    fgi_val = model.get("fgi_score")
    fgi_s = f"{fgi_val:.1f}" if fgi_val is not None else "—"
    avi_val = model.get("avi_score")
    avi_s = f"{avi_val:.1f}" if avi_val is not None else "—"
    eff_c = model.get("effective_cost")
    eff_s = f"${eff_c:.2f}" if eff_c is not None else "—"

    if win_w >= 78:
        safe_addstr(modal, line_offset + 3, 4, f"• Composite Q       : {q_s:<8}  • FGI (Architect Gate): {fgi_s:<8}", curses.A_NORMAL, boxed=True)
        safe_addstr(modal, line_offset + 4, 4, f"• 1-Turn Pass Rate  : {p_s:<8}  • AVI (Agentic ROI)   : {avi_s:<8}", curses.A_NORMAL, boxed=True)
        safe_addstr(modal, line_offset + 5, 4, f"• Effective Cost    : {eff_s:<8}  • Recommended Role    : {pl.get('best_role', '—')}", curses.A_NORMAL, boxed=True)
    else:
        safe_addstr(modal, line_offset + 3, 4, f"• Q: {q_s} │ Pass: {p_s} │ AVI: {avi_s}", curses.A_NORMAL, boxed=True)
        safe_addstr(modal, line_offset + 4, 4, f"• FGI: {fgi_s} │ Cost: {eff_s} │ Role: {pl.get('best_role', '—')}", curses.A_NORMAL, boxed=True)

    is_pareto = (model.get("display") in state.pareto_ids)
    par_label = "⭐ UNDEFEATED (On Pareto Frontier)" if is_pareto else "Standard Efficiency Curve"
    safe_addstr(modal, line_offset + (6 if win_w >= 78 else 5), 4, f"• Frontier Status   : {par_label}", curses.color_pair(3) | curses.A_BOLD if is_pareto else curses.A_DIM, boxed=True)

    safe_addstr(modal, win_h - 2, 2, "Press [Esc]/[q]/[Enter] to close │ [j/k] browse models", curses.A_DIM, boxed=True)
    modal.noutrefresh()


def draw_role_distribution_modal(stdscr, state: TUIState, max_y: int, max_x: int):
    """Draw Top 50 Role Distribution & Workforce Archetypes overlay."""
    win_h = min(23, max_y - 2)
    win_w = min(86, max_x - 4)
    start_y = max(1, (max_y - win_h) // 2)
    start_x = max(2, (max_x - win_w) // 2)

    modal = curses.newwin(win_h, win_w, start_y, start_x)
    modal.erase()
    modal.box()

    recs = state.role_recs
    cohort_len = len(state.top_cohort)

    safe_addstr(modal, 0, 2, f" 🏆 TOP {cohort_len} ROLE DISTRIBUTION & ARCHETYPES ", curses.A_BOLD | curses.color_pair(3), boxed=True)

    roles_data = [
        ("🏗️", "System Architecture & Complex Design", "architecture", "High FGI gates & reasoning. Spec lock, contracts, and deep debugging."),
        ("💻", "Pair Programming & Code Editing", "pair_programming", "Surgical diffs, coding Elo & multi-turn alignment without drift."),
        ("🔄", "Daily Driver (High ROI Workhorse)", "daily_driver", "Top AVI & cost-efficiency. Autonomous loops without token runaway."),
        ("⚡", "Fast Boilerplate & Mechanical Fill", "boilerplate", "High TPS & low cost for mechanical generation and scaffolding."),
    ]

    compact_mode = win_h < 21
    cur_y = 2
    w_w = 16 if win_w >= 78 else 12
    for icon, name, role_key, desc in roles_data:
        r_info = recs.get(role_key, {})
        w_name = r_info.get("winner", {}).get("name") or "None"
        w_score = r_info.get("winner", {}).get("score")
        w_s = f"({w_score:.1f})" if w_score is not None else ""
        run_name = r_info.get("runner_up", {}).get("name") or "None"
        run_score = r_info.get("runner_up", {}).get("score")
        run_s = f"({run_score:.1f})" if run_score is not None else ""

        w_disp = pad_display(w_name, w_w, "<")
        run_disp = pad_display(run_name, w_w, "<")

        safe_addstr(modal, cur_y, 2, f"{icon} {name}", curses.A_BOLD | curses.color_pair(4), boxed=True)
        role_line = f"  🥇 Top: {w_disp} {w_s:<7} │ 🥈 Run: {run_disp} {run_s}"
        safe_addstr(modal, cur_y + 1, 2, role_line, curses.A_NORMAL, boxed=True)
        if not compact_mode:
            safe_addstr(modal, cur_y + 2, 4, f"↳ {desc}", curses.A_DIM, boxed=True)
            cur_y += 3
        else:
            cur_y += 2

    # Top 50 Cohort Statistics pinned cleanly near bottom
    summary_sep_y = win_h - 5
    safe_addstr(modal, summary_sep_y, 0, "├" + "─" * (win_w - 2) + "┤", curses.A_DIM, boxed=True)
    safe_addstr(modal, summary_sep_y + 1, 2, f"📊 TOP {cohort_len} COHORT SUMMARY METRICS", curses.A_BOLD | curses.color_pair(2), boxed=True)

    speeds = [m.get("base_metrics", {}).get("speed_tps") for m in state.top_cohort if m.get("base_metrics", {}).get("speed_tps")]
    med_speed = sorted(speeds)[len(speeds) // 2] if speeds else 0
    q_scores = [m.get("capability_q") for m in state.top_cohort if m.get("capability_q")]
    avg_q = sum(q_scores) / len(q_scores) if q_scores else 0
    par_count = sum(1 for m in state.top_cohort if m.get("display") in state.pareto_ids)
    cov_str = "Tri-Verified (3/3)" if state.tri_verified_only else "All Models"

    if win_w >= 78:
        line1 = f"• Avg Capability Q : {avg_q:.1f} / 100       │ • Median Throughput : {med_speed:.0f} t/s"
        line2 = f"• Pareto Frontier  : {par_count} undefeated models   │ • Active Filter     : {cov_str}"
    else:
        line1 = f"• Avg Q: {avg_q:.1f} │ Median TPS: {med_speed:.0f} t/s"
        line2 = f"• Pareto: {par_count} models │ Filter: {cov_str}"
    safe_addstr(modal, summary_sep_y + 2, 4, line1, curses.A_NORMAL, boxed=True)
    safe_addstr(modal, summary_sep_y + 3, 4, line2, curses.A_NORMAL, boxed=True)

    safe_addstr(modal, win_h - 2, 2, "Press [Esc], [q], or [R] to close", curses.A_DIM, boxed=True)
    modal.noutrefresh()


def draw_diff_modal(stdscr, state: TUIState, max_y: int, max_x: int):
    """Draw side-by-side comparison diff overlay with aligned columns and colorized advantage."""
    win_h = min(22, max_y - 2)
    win_w = min(84, max(56, max_x - 4))
    start_y = max(1, (max_y - win_h) // 2)
    start_x = max(2, (max_x - win_w) // 2)

    modal = curses.newwin(win_h, win_w, start_y, start_x)
    modal.erase()
    modal.box()

    if not state.filtered_models:
        return

    base_idx = state.diff_baseline_idx if (0 <= state.diff_baseline_idx < len(state.filtered_models)) else 0
    m_base = state.filtered_models[base_idx]
    m_curr = state.filtered_models[state.cursor_idx]

    disp_base = (m_base.get("display") or "Baseline")[:18]
    disp_curr = (m_curr.get("display") or "Selected")[:18]

    safe_addstr(modal, 0, 2, " ⚔️ SIDE-BY-SIDE CAPABILITY DIFF ", curses.A_BOLD | curses.color_pair(1), boxed=True)
    safe_addstr(modal, 1, 2, f"Selected [A]: #{state.cursor_idx + 1} {disp_curr} vs Baseline [B]: #{base_idx + 1} {disp_base}", curses.A_DIM, boxed=True)
    safe_addstr(modal, 2, 0, "├" + "─" * (win_w - 2) + "┤", curses.A_DIM, boxed=True)

    pl_b = extract_capability_pillars(m_base)
    pl_c = extract_capability_pillars(m_curr)

    if win_w >= 82:
        col_dim, col_c, col_b, col_adv = 22, 15, 15, 16
    elif win_w >= 68:
        col_dim, col_c, col_b, col_adv = 18, 11, 11, 13
    else:
        col_dim, col_c, col_b, col_adv = 15, 9, 9, 11

    h_dim = pad_display("Metric Dimension", col_dim, "<")
    h_c = pad_display(f"#{state.cursor_idx + 1} Sel", col_c, ">")
    h_b = pad_display(f"#{base_idx + 1} Base", col_b, ">")
    h_adv = pad_display("Advantage", col_adv, ">")

    hdr_line = f"{h_dim} │ {h_c} │ {h_b} │ {h_adv}"
    safe_addstr(modal, 3, 2, hdr_line, curses.A_BOLD, boxed=True)
    safe_addstr(modal, 4, 0, "├" + "─" * (win_w - 2) + "┤", curses.A_DIM, boxed=True)

    diff_rows = [
        ("Capability Q", m_curr.get("capability_q"), m_base.get("capability_q"), lambda v: f"{v:.1f}", False),
        ("1-Turn Pass Rate", m_curr.get("p_success"), m_base.get("p_success"), lambda v: f"{v:.1f}%", False),
        ("Reasoning %", pl_c.get("reasoning"), pl_b.get("reasoning"), lambda v: f"{v:.1f}%", False),
        ("Coding %", pl_c.get("coding"), pl_b.get("coding"), lambda v: f"{v:.1f}%", False),
        ("Speed Throughput", pl_c.get("speed"), pl_b.get("speed"), lambda v: f"{v:.0f}t/s", False),
        ("Context Window", pl_c.get("context_length"), pl_b.get("context_length"), lambda v: format_context_window(v), False),
        ("Prompt Price $/M", m_curr.get("price_in"), m_base.get("price_in"), lambda v: f"${v:.2f}", True),
        ("Effective Task Cost", m_curr.get("effective_cost"), m_base.get("effective_cost"), lambda v: f"${v:.2f}", True),
    ]

    for idx, (label, val_c, val_b, fmt_fn, lower_better) in enumerate(diff_rows):
        y = 5 + idx
        if y >= win_h - 2:
            break
        s_c = fmt_fn(val_c) if val_c is not None else "—"
        s_b = fmt_fn(val_b) if val_b is not None else "—"

        adv_attr = curses.A_NORMAL
        if val_c is not None and val_b is not None and isinstance(val_c, (int, float)) and isinstance(val_b, (int, float)):
            diff = val_c - val_b
            if abs(diff) < 0.01:
                adv = "Tied"
                adv_attr = curses.A_DIM
            elif (diff > 0 and not lower_better) or (diff < 0 and lower_better):
                adv = f"+{abs(diff):.1f} (Sel)"
                adv_attr = curses.color_pair(2) | curses.A_BOLD  # Green: Selected is winning!
            else:
                adv = f"+{abs(diff):.1f} (Base)"
                adv_attr = curses.color_pair(4)                  # Cyan: Baseline is winning!
        else:
            adv = "—"
            adv_attr = curses.A_DIM

        c_dim = pad_display(label, col_dim, "<")
        c_c = pad_display(s_c, col_c, ">")
        c_b = pad_display(s_b, col_b, ">")
        c_adv = pad_display(adv, col_adv, ">")

        prefix = f"{c_dim} │ {c_c} │ {c_b} │ "
        safe_addstr(modal, y, 2, prefix, curses.A_NORMAL, boxed=True)
        safe_addstr(modal, y, 2 + display_len(prefix), c_adv, adv_attr, boxed=True)

    safe_addstr(modal, win_h - 2, 2, "Press [Esc]/[q]/[d] close │ [j/k] switch model │ [b] pin baseline", curses.A_DIM, boxed=True)
    modal.noutrefresh()


def draw_help_modal(stdscr, max_y: int, max_x: int):
    """Draw keyboard shortcuts and capability guide overlay."""
    win_h = min(23, max_y - 2)
    win_w = min(84, max_x - 4)
    start_y = max(1, (max_y - win_h) // 2)
    start_x = max(2, (max_x - win_w) // 2)

    modal = curses.newwin(win_h, win_w, start_y, start_x)
    modal.erase()
    modal.box()

    safe_addstr(modal, 0, 2, " 🧭 CHECKERZ · SHORTCUTS & CAPABILITY GUIDE ", curses.A_BOLD | curses.color_pair(1), boxed=True)

    categories = [
        ("NAVIGATION & VIEWS", [
            ("j / k, ↓ / ↑", "Move cursor up and down through models"),
            ("n / p, ] / [", "Next / Previous page (or PgDn / PgUp)"),
            ("g / G, Home/End", "Jump directly to top / bottom of table"),
            ("Enter / Space", "Open deep Capability Breakdown Drawer for highlighted model"),
            ("R", "Open Top 50 Role Distribution & Software Archetypes"),
            ("d", "Open Side-by-side Capability Diff vs Baseline"),
            ("b", "Pin highlighted model as Baseline [B] for comparison diff"),
        ]),
        ("FILTERS & CONTROLS", [
            ("e", "Toggle Tri-Verified (3/3) vs. All Evaluated Models"),
            ("P", "Toggle Pareto Frontier filter (⭐ undefeated models only)"),
            ("/", "Interactive Live Search by name/provider (Esc cancels)"),
            ("Tab / 1-6", "Filter by Subscription Pool (ALL, AGY, CLD, OCG, FRT, API)"),
            ("Esc", "Clear active search or reset all filters"),
        ]),
        ("SORTING & EXPORT", [
            ("c / r / s", "Sort by Coding / Reasoning / Speed Throughput"),
            ("x / $ / v", "Sort by Context Window / Price $/M / Agentic Value ROI"),
            ("S", "Cycle through all sort criteria"),
            ("m / h", "Direct atomic export to Markdown (benchmarks.md) or HTML"),
            ("q", "Quit back to terminal"),
        ]),
    ]

    cur_y = 2
    for cat_title, items in categories:
        if cur_y >= win_h - 3:
            break
        safe_addstr(modal, cur_y, 2, f"▪ {cat_title}", curses.A_BOLD | curses.color_pair(3), boxed=True)
        cur_y += 1
        for k, desc in items:
            if cur_y >= win_h - 3:
                break
            safe_addstr(modal, cur_y, 4, pad_display(k, 16, "<"), curses.A_BOLD | curses.color_pair(4), boxed=True)
            safe_addstr(modal, cur_y, 21, f"• {desc}", curses.A_NORMAL, boxed=True)
            cur_y += 1

    safe_addstr(modal, win_h - 2, 2, "Press [Esc], [q], or [?] to close", curses.A_DIM, boxed=True)
    modal.noutrefresh()


def render_tui(stdscr, state: TUIState):
    """Render full interactive screen with responsive elastic columns, zebra striping, and Pareto gold."""
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    if max_y < 12 or max_x < 60:
        safe_addstr(stdscr, 0, 0, "Terminal window too small for TUI (min 60x12).", curses.A_BOLD)
        stdscr.refresh()
        return

    # 1. Top Header Bar
    title_text = "⚡ CHECKERZ · ONE-SHOT CAPABILITIES"
    safe_addstr(stdscr, 0, 0, " " * (max_x - 1), curses.color_pair(1) | curses.A_BOLD)
    safe_addstr(stdscr, 0, 2, title_text, curses.color_pair(1) | curses.A_BOLD)

    # Header badges
    total_models = len(state.filtered_models)
    start_num = (state.page_idx * state.page_size) + 1 if total_models > 0 else 0
    end_num = min((state.page_idx + 1) * state.page_size, total_models)
    page_info = f"[Page {state.page_idx + 1}/{state.total_pages} · {start_num}–{end_num} of {total_models}]"
    cov_badge = "[3/3 Only]" if state.tri_verified_only else "[All Models]"
    sort_info = f"[{state.sort_key.upper()} {'▼' if state.sort_reverse else '▲'}]"
    pool_info = f"[{POOL_LABELS.get(state.pool_filter, state.pool_filter.upper())}]"

    right_header = f"{page_info} {cov_badge} {pool_info} {sort_info}"
    if max_x >= len(title_text) + len(right_header) + 6:
        safe_addstr(stdscr, 0, max_x - len(right_header) - 2, right_header, curses.color_pair(1))
    else:
        # Condensed badges for narrow screens
        condensed = f"[P.{state.page_idx + 1}/{state.total_pages}] {pool_info}"
        safe_addstr(stdscr, 0, max(len(title_text) + 3, max_x - len(condensed) - 1), condensed, curses.color_pair(1))

    # 2. Search & Info line
    if state.searching:
        matches_s = f"({len(state.filtered_models)} matches)"
        search_prompt = f" 🔍 Search: {state.search_query}█  {matches_s}  — [Enter] commit, [Esc] cancel"
        safe_addstr(stdscr, 1, 0, search_prompt + " " * max(0, max_x - len(search_prompt) - 1), curses.color_pair(7))
    else:
        q_str = f'"{state.search_query}"' if state.search_query else "None ([/] filter)"
        pareto_badge = " [⭐ PARETO ONLY]" if state.pareto_only else ""
        info_line = f" Filter: {q_str}{pareto_badge} │ Upstream: LiveBench · LMSYS Arena · Artificial Analysis"
        safe_addstr(stdscr, 1, 0, info_line, curses.A_DIM)

    # 3. Dynamic Column Configuration
    margin = 1 if max_x >= 90 else 0
    max_table_w = max_x - (margin * 2) - 1

    if max_table_w < 78:
        # Compact 5 columns for tight terminals
        fixed_before = [("Rank", 4, "^")]
        fixed_after = [
            ("Conf", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("Speed", 6, ">"),
        ]
    elif max_table_w < 89:
        # Standard 8 columns
        fixed_before = [("Rank", 5, "^")]
        fixed_after = [
            ("Pool", 5, "^"),
            ("Conf", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("Reason", 6, ">"),
            ("Coding", 6, ">"),
            ("Speed", 6, ">"),
        ]
    elif max_table_w < 109:
        # Enhanced 9 columns with Context Window
        fixed_before = [("Rank", 5, "^")]
        fixed_after = [
            ("Pool", 5, "^"),
            ("Conf", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("Reason", 6, ">"),
            ("Coding", 6, ">"),
            ("Speed", 6, ">"),
            ("Ctx", 6, ">"),
        ]
    elif max_table_w < 129:
        # Pricing 10 columns with Price $/M
        fixed_before = [("Rank", 5, "^")]
        fixed_after = [
            ("Pool", 5, "^"),
            ("Conf", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("Reason", 6, ">"),
            ("Coding", 6, ">"),
            ("Speed", 6, ">"),
            ("Ctx", 6, ">"),
            ("Price", 11, ">"),
        ]
    else:
        # Full 11 columns with Best Role
        fixed_before = [("Rank", 5, "^")]
        fixed_after = [
            ("Pool", 5, "^"),
            ("Conf", 5, "^"),
            ("Q(Cap)", 6, ">"),
            ("Reason", 6, ">"),
            ("Coding", 6, ">"),
            ("Speed", 6, ">"),
            ("Ctx", 6, ">"),
            ("Price", 11, ">"),
            ("Best Role", 14, "<"),
        ]

    num_cols = len(fixed_before) + 1 + len(fixed_after)
    sep_w = 3 * num_cols + 1
    fixed_w = sum(w for _, w, _ in fixed_before) + sum(w for _, w, _ in fixed_after)
    model_w = max(14, max_table_w - sep_w - fixed_w)
    if max_x >= 150:
        model_w = min(46, model_w)
    cols = fixed_before + [("Model", model_w, "<")] + fixed_after

    actual_table_w = fixed_w + model_w + sep_w
    start_x = max(0, (max_x - actual_table_w) // 2)

    # 4. Table Frame & Column Headers
    hdr_y = 2
    top_border = "┌" + "─" * (actual_table_w - 2) + "┐"
    safe_addstr(stdscr, hdr_y, start_x, top_border, curses.A_DIM)

    hdr_cells = [pad_display(name, w, align) for name, w, align in cols]
    hdr_row = "│ " + " │ ".join(hdr_cells) + " │"
    safe_addstr(stdscr, hdr_y + 1, start_x, hdr_row, curses.A_BOLD)

    sep_row = "├" + "─" * (actual_table_w - 2) + "┤"
    safe_addstr(stdscr, hdr_y + 2, start_x, sep_row, curses.A_DIM)

    # 5. Data Rows (Paginated slice)
    table_top_y = 5
    page_start = state.page_idx * state.page_size
    page_models = state.filtered_models[page_start : page_start + state.page_size]

    for r_idx in range(state.page_size):
        cur_y = table_top_y + r_idx
        if cur_y >= max_y - 2:
            break

        if r_idx >= len(page_models):
            if r_idx == 0 and not state.filtered_models:
                no_data_msg = " No models match current filter/pool. Press [Esc] to reset."
                empty_line = "│" + pad_display(no_data_msg, actual_table_w - 2, "<") + "│"
                safe_addstr(stdscr, cur_y, start_x, empty_line, curses.color_pair(3) | curses.A_BOLD)
            else:
                empty_line = "│" + " " * (actual_table_w - 2) + "│"
                safe_addstr(stdscr, cur_y, start_x, empty_line, curses.A_DIM)
            continue

        m = page_models[r_idx]
        global_idx = page_start + r_idx
        is_selected = (global_idx == state.cursor_idx)
        is_even_row = (r_idx % 2 == 0)
        pl = extract_capability_pillars(m)

        mid_raw = m.get("display") or m.get("model_id") or "Unknown"
        is_pareto = (mid_raw in state.pareto_ids)

        if global_idx == 0:
            rank_str = "🥇#1"
        elif global_idx == 1:
            rank_str = "🥈#2"
        elif global_idx == 2:
            rank_str = "🥉#3"
        else:
            rank_str = f"#{global_idx + 1}"

        if is_pareto:
            rank_str = "⭐" + rank_str.lstrip("⭐")

        pool_s = (m.get("pool") or "API").upper()[:4]

        cov = pl["coverage_count"]
        conf_s = "[3/3]" if cov == 3 else ("[2/3]" if cov == 2 else ("[1/3]*" if cov == 1 else "[0/3]"))

        q_val = m.get("capability_q")
        q_s = f"{q_val:.1f}" if q_val is not None else "—"
        r_val = pl.get("reasoning")
        r_s = f"{r_val:.1f}%" if r_val is not None else "—"
        c_val = pl.get("coding")
        c_s = f"{c_val:.1f}%" if c_val is not None else "—"
        s_val = pl.get("speed")
        s_s = f"{s_val:.0f}t/s" if s_val is not None else "—"
        ctx_s = format_context_window(pl.get("context_length"))

        pin = m.get("price_in", 0.0)
        pout = m.get("price_out", 0.0)
        p_str = f"${pin:.1f}/${pout:.1f}" if (pin is not None and pout is not None) else "—"
        role_s = pl.get("best_role", "—")

        # Map values according to active column set
        vals_map = {
            "Rank": rank_str,
            "Model": mid_raw,
            "Pool": pool_s,
            "Conf": conf_s,
            "Q(Cap)": q_s,
            "Reason": r_s,
            "Coding": c_s,
            "Speed": s_s,
            "Ctx": ctx_s,
            "Price": p_str,
            "Best Role": role_s,
        }

        row_cells = []
        for name, w, align in cols:
            val = vals_map.get(name, "—")
            row_cells.append(pad_display(val, w, align))

        cursor_mark = "▶" if is_selected else "│"
        row_line = f"{cursor_mark} " + " │ ".join(row_cells) + " │"

        # Row Styling: Selected > Pareto Gold > Zebra Even/Odd
        if is_selected:
            if is_pareto:
                attr = curses.color_pair(8) | curses.A_BOLD
            else:
                attr = curses.A_REVERSE | curses.A_BOLD
        elif is_pareto:
            attr = curses.color_pair(3) | curses.A_BOLD
        elif not is_even_row:
            attr = curses.A_DIM  # Zebra stripe: subtle dim on odd rows
        else:
            attr = curses.A_NORMAL

        safe_addstr(stdscr, cur_y, start_x, row_line, attr)

    # 6. Table Bottom Border
    bot_y = table_top_y + state.page_size
    if bot_y < max_y - 1:
        bot_border = "└" + "─" * (actual_table_w - 2) + "┘"
        safe_addstr(stdscr, bot_y, start_x, bot_border, curses.A_DIM)

    # 7. Status Bar & Keybindings Footer
    ftr_y = max_y - 1
    if state.status_msg:
        safe_addstr(stdscr, ftr_y, 0, f" 🔔 {state.status_msg} " + " " * max(0, max_x - len(state.status_msg) - 6), curses.color_pair(3) | curses.A_BOLD)
    else:
        ftr_text = f" [j/k] Move  [n/p] Page {state.page_idx + 1}/{state.total_pages}  [Enter] Drawer  [R]oles  [d]iff  [b]ase  [P]areto  [e] 3/3  [c/r/s/$] Sort  [?] Help  [q]uit"
        safe_addstr(stdscr, ftr_y, 0, ftr_text, curses.color_pair(1))

    # 8. Stage background table
    stdscr.noutrefresh()

    # 9. Active Modal Overlays (staged on top of background table)
    if state.inspecting and state.filtered_models:
        cur_model = state.filtered_models[state.cursor_idx]
        draw_modal(stdscr, cur_model, state, max_y, max_x)
    elif state.showing_roles:
        draw_role_distribution_modal(stdscr, state, max_y, max_x)
    elif state.showing_diff:
        draw_diff_modal(stdscr, state, max_y, max_x)
    elif state.showing_help:
        draw_help_modal(stdscr, max_y, max_x)

    # 10. Atomic screen refresh (zero flicker, zero overwrite)
    curses.doupdate()


def run_tui(models_list: list[dict], color: bool = True, unmatched_models: list[dict] = None, tri_verified_only: bool = True, top_limit: int = 50):
    """Run interactive curses TUI dashboard."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        from checkers.llm_benchmark_aggregator import render_one_shot_cli_table
        state = TUIState(
            all_models=models_list,
            unmatched_models=unmatched_models or [],
            tri_verified_only=tri_verified_only,
            top_limit=top_limit,
        )
        print(render_one_shot_cli_table(state.filtered_models, color=color, unmatched_models=unmatched_models))
        return

    unmatched = unmatched_models or []
    state = TUIState(
        all_models=models_list,
        unmatched_models=unmatched,
        tri_verified_only=tri_verified_only,
        top_limit=top_limit,
    )

    def _tui_loop(stdscr):
        try:
            curses.curs_set(0)
        except Exception:
            pass
        stdscr.keypad(True)
        stdscr.timeout(100)
        init_colors()

        while True:
            max_y, _ = stdscr.getmaxyx()
            state.page_size = max(5, max_y - 8)
            render_tui(stdscr, state)

            try:
                ch = stdscr.getch()
            except Exception:
                continue

            if ch == -1:
                continue

            # Handle terminal resize cleanly without ghost artifacts
            if ch == curses.KEY_RESIZE:
                stdscr.clear()
                curses.flushinp()
                continue

            # Handle search typing mode
            if state.searching:
                if ch in (10, 13):  # Enter confirms search
                    state.searching = False
                    state.apply_filters()
                elif ch in (27,):    # Esc cancels search
                    state.searching = False
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    state.search_query = state.search_query[:-1]
                    state.apply_filters()
                elif 32 <= ch <= 126:
                    state.search_query += chr(ch)
                    state.apply_filters()
                continue

            # Handle active modal interactions & dismissals
            if state.inspecting or state.showing_roles or state.showing_diff or state.showing_help:
                # Universal dismiss: Esc or 'q'
                if ch in (27, ord('q'), ord('Q')):
                    state.inspecting = False
                    state.showing_roles = False
                    state.showing_diff = False
                    state.showing_help = False
                    curses.flushinp()
                    continue

                # Drawer controls (allows live browsing while drawer is open!)
                if state.inspecting:
                    if ch in (10, 13, 32):  # Enter or Space closes drawer
                        state.inspecting = False
                        curses.flushinp()
                        continue
                    elif ch in (ord('j'), curses.KEY_DOWN):
                        state.move_cursor(1)
                        continue
                    elif ch in (ord('k'), curses.KEY_UP):
                        state.move_cursor(-1)
                        continue
                    elif ch in (ord('n'), ord(']'), curses.KEY_NPAGE):
                        state.next_page()
                        continue
                    elif ch in (ord('p'), ord('['), curses.KEY_PPAGE):
                        state.prev_page()
                        continue

                # Diff controls
                if state.showing_diff:
                    if ch in (ord('d'), ord('D'), 10, 13, 32):
                        state.showing_diff = False
                        curses.flushinp()
                        continue
                    elif ch in (ord('b'), ord('B')):
                        state.pin_current_as_baseline()
                        continue
                    elif ch in (ord('j'), curses.KEY_DOWN):
                        state.move_cursor(1)
                        continue
                    elif ch in (ord('k'), curses.KEY_UP):
                        state.move_cursor(-1)
                        continue

                # Roles modal controls
                if state.showing_roles:
                    if ch in (ord('R'), ord('r'), 10, 13, 32):
                        state.showing_roles = False
                        curses.flushinp()
                        continue

                # Help modal controls
                if state.showing_help:
                    if ch in (ord('?'), 10, 13, 32):
                        state.showing_help = False
                        curses.flushinp()
                        continue

                # Consume other keys while modal is active
                continue

            # Navigation
            if ch in (ord('j'), curses.KEY_DOWN):
                state.move_cursor(1)
            elif ch in (ord('k'), curses.KEY_UP):
                state.move_cursor(-1)
            elif ch in (ord('n'), ord(']'), curses.KEY_NPAGE, 4):  # Next page or PgDn
                state.next_page()
            elif ch in (ord('p'), ord('['), curses.KEY_PPAGE, 21): # Prev page or PgUp
                state.prev_page()
            elif ch in (ord('g'), curses.KEY_HOME):
                state.cursor_idx = 0
                state.page_idx = 0
            elif ch in (ord('G'), curses.KEY_END):
                if state.filtered_models:
                    state.cursor_idx = len(state.filtered_models) - 1
                    state.page_idx = state.cursor_idx // state.page_size

            # Modals & Views
            elif ch in (10, 13, 32):  # Enter or Space
                if state.filtered_models:
                    state.inspecting = True
                    curses.flushinp()
            elif ch in (ord('R'),):
                state.showing_roles = True
                curses.flushinp()
            elif ch in (ord('d'), ord('D')):
                if state.filtered_models:
                    state.showing_diff = True
                    curses.flushinp()
            elif ch in (ord('b'), ord('B')):
                state.pin_current_as_baseline()
            elif ch in (ord('?'),):
                state.showing_help = True
                curses.flushinp()

            # Filter Toggles
            elif ch in (ord('e'), ord('E')):
                state.toggle_tri_verified()
            elif ch in (ord('P'),):
                state.toggle_pareto_only()

            # Sorting Shortcuts (Conflict-Free)
            elif ch in (ord('c'), ord('C')):
                state.set_sort("coding")
            elif ch in (ord('r'),):
                state.set_sort("reasoning")
            elif ch in (ord('s'),):
                state.set_sort("speed")
            elif ch in (ord('x'), ord('X')):
                state.set_sort("ctx")
            elif ch in (ord('$'),):
                state.set_sort("price")
            elif ch in (ord('v'), ord('V')):
                state.set_sort("avi")
            elif ch in (ord('S'), ord('o'), ord('O')):
                state.cycle_sort()

            # Pool Cycling
            elif ch in (9,):  # Tab
                state.cycle_pool()
            elif ch in (ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6')):
                num = int(chr(ch)) - 1
                if 0 <= num < len(POOLS):
                    state.pool_filter = POOLS[num]
                    state.page_idx = 0
                    state.cursor_idx = 0
                    state.apply_filters()
                    state.status_msg = f"Pool: {POOL_LABELS.get(state.pool_filter, state.pool_filter.upper())}"

            # Search entry
            elif ch in (ord('/'),):
                state.searching = True
                state.status_msg = ""

            # Clear filter / Esc
            elif ch in (27,):
                state.search_query = ""
                state.pool_filter = "all"
                state.pareto_only = False
                state.status_msg = "Filters reset."
                state.apply_filters()

            # Direct Exports
            elif ch in (ord('m'), ord('M')):
                try:
                    from checkers.llm_benchmark_aggregator import render_markdown_report
                    md_text = render_markdown_report(state.filtered_models, top_n=len(state.filtered_models))
                    p = ROOT / "docs" / "reports" / "benchmarks.md"
                    bc.atomic_write_text(p, md_text)
                    state.status_msg = f"Exported Markdown -> {p.name}"
                except Exception as e:
                    state.status_msg = f"Export failed: {e}"

            elif ch in (ord('h'), ord('H')):
                try:
                    from checkers.llm_benchmark_aggregator import render_html_report
                    html_text = render_html_report(state.filtered_models, top_n=len(state.filtered_models))
                    p = ROOT / "docs" / "reports" / "benchmarks.html"
                    bc.atomic_write_text(p, html_text)
                    state.status_msg = f"Exported HTML -> {p.name}"
                except Exception as e:
                    state.status_msg = f"Export failed: {e}"

            # Quit back to shell
            elif ch in (ord('q'), ord('Q')):
                break

    try:
        curses.wrapper(_tui_loop)
    except KeyboardInterrupt:
        pass


def main():
    """CLI entrypoint for standalone checkerz TUI."""
    import argparse
    parser = argparse.ArgumentParser(description="checkerz — Interactive One-Shot Model Capabilities TUI")
    parser.add_argument("--fetch", action="store_true", help="Refresh upstream benchmark cache")
    parser.add_argument("--plain", action="store_true", help="Disable color in fallback")
    parser.add_argument("--all", action="store_true", help="Include all models (disable default tri-verified filter)")
    parser.add_argument("-n", "--top", type=int, default=50, help="Limit to top N models (default: 50)")
    args = parser.parse_args()

    from checkers.llm_benchmark_aggregator import (
        load_livebench_data, load_lmarena_data, load_aa_data,
        build_universal_catalog, calculate_composite_scores,
    )
    live_map = load_livebench_data(fetch=args.fetch)
    lm_map = load_lmarena_data(fetch=args.fetch)
    aa_map = load_aa_data(fetch=args.fetch)

    catalog = build_universal_catalog(live_map=live_map, lm_map=lm_map, aa_map=aa_map)
    calculate_composite_scores(catalog)

    unmatched_catalog = [m for m in catalog.values() if m.get("unmatched") or (not m.get("livebench") and not m.get("aa_live_quality") and not m.get("base_metrics", {}).get("lm_elo"))]
    models = [m for m in catalog.values() if m.get("livebench") or m.get("aa_live_quality") or m.get("base_metrics", {}).get("lm_elo")]

    run_tui(
        models,
        color=not args.plain,
        unmatched_models=unmatched_catalog,
        tri_verified_only=not args.all,
        top_limit=args.top,
    )


if __name__ == "__main__":
    main()
