//! Ratatui rendering: elastic columns, zebra rows, pareto gold, modals.
//!
//! Column breakpoints mirror the Python TUI (`render_tui`) so narrow
//! terminals degrade to the same compact column sets.

use crate::app::App;
use crate::model::{conf_badge, fmt_price_pair, format_ctx, pillars, Model};
use crate::scoring::cohort_summary;
use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style, Stylize},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Paragraph},
    Frame,
};
use unicode_width::UnicodeWidthStr;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Align {
    Left,
    Center,
    Right,
}

#[derive(Debug, Clone, Copy)]
pub struct Column {
    pub name: &'static str,
    pub width: usize,
    pub align: Align,
}

pub fn disp_width(s: &str) -> usize {
    UnicodeWidthStr::width(s)
}

/// Pad/truncate to exactly `w` display columns.
pub fn pad(s: &str, w: usize, align: Align) -> String {
    let mut out = String::new();
    let mut width = 0;
    for ch in s.chars() {
        let cw = UnicodeWidthStr::width(ch.to_string().as_str());
        if width + cw > w {
            break;
        }
        out.push(ch);
        width += cw;
    }
    if width >= w {
        return out;
    }
    let fill = " ".repeat(w - width);
    match align {
        Align::Left => format!("{out}{fill}"),
        Align::Right => format!("{fill}{out}"),
        Align::Center => {
            let left = (w - width) / 2;
            let right = w - width - left;
            format!("{}{out}{}", " ".repeat(left), " ".repeat(right))
        }
    }
}

/// Fixed columns for a terminal width (before the elastic Model column).
pub fn fixed_columns(max_table_w: usize) -> (Vec<Column>, Vec<Column>) {
    let c = |name: &'static str, width: usize, align: Align| Column { name, width, align };
    if max_table_w < 78 {
        (
            vec![c("Rank", 4, Align::Center)],
            vec![
                c("Conf", 5, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Speed", 6, Align::Right),
            ],
        )
    } else if max_table_w < 89 {
        (
            vec![c("Rank", 5, Align::Center)],
            vec![
                c("Pool", 5, Align::Center),
                c("Conf", 5, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Reason", 6, Align::Right),
                c("Coding", 6, Align::Right),
                c("Speed", 6, Align::Right),
            ],
        )
    } else if max_table_w < 109 {
        (
            vec![c("Rank", 5, Align::Center)],
            vec![
                c("Pool", 5, Align::Center),
                c("Conf", 5, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Reason", 6, Align::Right),
                c("Coding", 6, Align::Right),
                c("Speed", 6, Align::Right),
                c("Ctx", 6, Align::Right),
            ],
        )
    } else if max_table_w < 129 {
        (
            vec![c("Rank", 5, Align::Center)],
            vec![
                c("Pool", 5, Align::Center),
                c("Conf", 5, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Reason", 6, Align::Right),
                c("Coding", 6, Align::Right),
                c("Speed", 6, Align::Right),
                c("Ctx", 6, Align::Right),
                c("Price", 11, Align::Right),
            ],
        )
    } else {
        (
            vec![c("Rank", 5, Align::Center)],
            vec![
                c("Pool", 5, Align::Center),
                c("Conf", 5, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Reason", 6, Align::Right),
                c("Coding", 6, Align::Right),
                c("Speed", 6, Align::Right),
                c("Ctx", 6, Align::Right),
                c("Price", 11, Align::Right),
                c("Best Role", 14, Align::Left),
            ],
        )
    }
}

/// Full column list including the elastic Model column for `term_w`.
pub fn columns_for(term_w: usize) -> Vec<Column> {
    let margin = if term_w >= 90 { 1 } else { 0 };
    let max_table_w = term_w.saturating_sub(margin * 2 + 1);
    let (before, after) = fixed_columns(max_table_w);
    let n_cols = before.len() + 1 + after.len();
    let sep_w = 3 * n_cols + 1;
    let fixed_w: usize = before.iter().chain(after.iter()).map(|c| c.width).sum();
    let mut model_w = max_table_w.saturating_sub(sep_w + fixed_w).max(14);
    if term_w >= 150 {
        model_w = model_w.min(46);
    }
    let mut cols = before;
    cols.push(Column { name: "Model", width: model_w, align: Align::Left });
    cols.extend(after);
    cols
}

pub fn table_width(cols: &[Column]) -> usize {
    let fixed: usize = cols.iter().map(|c| c.width).sum();
    fixed + 3 * cols.len() + 1
}

fn rank_str(global_idx: usize, pareto: bool) -> String {
    let base = match global_idx {
        0 => "🥇#1".to_string(),
        1 => "🥈#2".to_string(),
        2 => "🥉#3".to_string(),
        n => format!("#{}", n + 1),
    };
    if pareto {
        format!("⭐{base}")
    } else {
        base
    }
}

fn pool4(pool: &str) -> String {
    let p = if pool.is_empty() { "API" } else { pool };
    p.to_uppercase().chars().take(4).collect()
}

pub fn cell_value(col: &str, m: &Model, rank: &str) -> String {
    let p = pillars(m);
    match col {
        "Rank" => rank.to_string(),
        "Model" => {
            let base = if m.display.is_empty() {
                "Unknown".to_string()
            } else {
                m.display.clone()
            };
            if m.is_new { format!("+{base}") } else { base }
        }
        "Pool" => pool4(&m.pool),
        "Conf" => conf_badge(p.coverage_count).to_string(),
        "Q(Cap)" => m.quality().map(|q| format!("{q:.1}")).unwrap_or("—".into()),
        "Reason" => p.reasoning.map(|v| format!("{v:.1}%")).unwrap_or("—".into()),
        "Coding" => p.coding.map(|v| format!("{v:.1}%")).unwrap_or("—".into()),
        "Speed" => p.speed.map(|v| format!("{v:.0}t/s")).unwrap_or("—".into()),
        "Ctx" => format_ctx(p.context_length.map(|v| v as f64)),
        "Price" => fmt_price_pair(m.price_in, m.price_out),
        "Best Role" => p.best_role,
        _ => "—".to_string(),
    }
}

fn row_style(selected: bool, pareto: bool, odd: bool) -> Style {
    if selected {
        if pareto {
            Style::default().fg(Color::Black).bg(Color::Yellow).add_modifier(Modifier::BOLD)
        } else {
            Style::default().add_modifier(Modifier::REVERSED | Modifier::BOLD)
        }
    } else if pareto {
        Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)
    } else if odd {
        Style::default().add_modifier(Modifier::DIM)
    } else {
        Style::default()
    }
}

fn header_text(app: &App) -> (String, String) {
    let total = app.filtered.len();
    let start = if total == 0 { 0 } else { app.page * app.page_size + 1 };
    let end = ((app.page + 1) * app.page_size).min(total);
    let title = "⚡ CHECKERZ · ONE-SHOT CAPABILITIES".to_string();
    let right = format!(
        "[Page {}/{} · {start}–{end} of {total}] {} [{}] [{} {}]",
        app.page + 1,
        app.total_pages(),
        app.coverage_label(),
        crate::app::pool_label(&app.pool),
        app.sort_key.label(),
        if app.sort_desc { "▼" } else { "▲" },
    );
    (title, right)
}

fn info_text(app: &App) -> String {
    let q = if app.query.is_empty() { "None ([/] filter)".to_string() } else { format!("\"{}\"", app.query) };
    let pareto = if app.pareto_only { " [⭐ PARETO ONLY]" } else { "" };
    let mut s = format!(" Filter: {q}{pareto} │ Upstream: LiveBench · LMSYS Arena · Artificial Analysis");
    if app.unmatched_count > 0 {
        s.push_str(&format!(" · Unmatched: {}", app.unmatched_count));
    }
    if !app.stale_note.is_empty() {
        s.push_str(&format!(" │ ⚠ {}", app.stale_note));
    }
    s
}

pub fn draw(f: &mut Frame, app: &mut App) {
    let area = f.area();
    let (w, h) = (area.width as usize, area.height as usize);
    if h < 12 || w < 60 {
        f.render_widget(
            Paragraph::new("Terminal window too small for TUI (min 60x12).").bold(),
            area,
        );
        return;
    }
    app.page_size = (h.saturating_sub(8)).max(5);
    // Re-clamp page after a resize changed page_size.
    if !app.filtered.is_empty() {
        app.page = (app.cursor / app.page_size).min(app.total_pages() - 1);
    }

    let mut lines: Vec<Line> = Vec::new();
    let (title, right) = header_text(app);
    let mut hdr = format!("  {title}");
    if disp_width(&format!("{hdr}  {right}  ")) <= w {
        let gap = w.saturating_sub(disp_width(&hdr) + disp_width(&right) + 2);
        hdr.push_str(&" ".repeat(gap));
        hdr.push_str(&right);
        hdr.push_str("  ");
    }
    lines.push(Line::from(Span::styled(
        pad(&hdr, w.saturating_sub(1), Align::Left),
        Style::default().fg(Color::Black).bg(Color::Cyan).add_modifier(Modifier::BOLD),
    )));

    if app.searching {
        lines.push(Line::from(Span::styled(
            pad(
                &format!(" 🔍 Search: {}█  ({} matches)  — [Enter] commit, [Esc] cancel", app.query, app.filtered.len()),
                w.saturating_sub(1),
                Align::Left,
            ),
            Style::default().fg(Color::Black).bg(Color::White),
        )));
    } else {
        lines.push(Line::from(Span::styled(
            info_text(app),
            Style::default().add_modifier(Modifier::DIM),
        )));
    }

    let cols = columns_for(w);
    let tw = table_width(&cols).min(w);
    let start_x = (w.saturating_sub(tw)) / 2;
    let indent = " ".repeat(start_x);
    let inner = tw.saturating_sub(2);
    lines.push(Line::from(Span::styled(format!("{indent}┌{}┐", "─".repeat(inner)), Style::default().add_modifier(Modifier::DIM))));
    let hdr_cells: Vec<String> = cols.iter().map(|c| pad(c.name, c.width, c.align)).collect();
    lines.push(Line::from(Span::styled(
        format!("{indent}│ {} │", hdr_cells.join(" │ ")),
        Style::default().add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(Span::styled(format!("{indent}├{}┤", "─".repeat(inner)), Style::default().add_modifier(Modifier::DIM))));

    let page_start = app.page * app.page_size;
    for r in 0..app.page_size {
        let y_full = lines.len();
        let _ = y_full;
        if page_start + r >= app.filtered.len() {
            if r == 0 && app.filtered.is_empty() {
                let msg = pad(" No models match current filter/pool. Press [Esc] to reset.", inner, Align::Left);
                lines.push(Line::from(Span::styled(
                    format!("{indent}│{msg}│"),
                    Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD),
                )));
            } else {
                lines.push(Line::from(Span::styled(
                    format!("{indent}│{}│", " ".repeat(inner)),
                    Style::default().add_modifier(Modifier::DIM),
                )));
            }
            continue;
        }
        let g = page_start + r;
        let mi = app.filtered[g];
        let m = &app.all[mi];
        let pareto = app.is_pareto_idx(g);
        let rank = rank_str(g, pareto);
        let cells: Vec<String> = cols.iter().map(|c| pad(&cell_value(c.name, m, &rank), c.width, c.align)).collect();
        let mark = if g == app.cursor { "▶" } else { "│" };
        lines.push(Line::from(Span::styled(
            format!("{indent}{mark} {} │", cells.join(" │ ")),
            row_style(g == app.cursor, pareto, r % 2 == 1),
        )));
    }
    lines.push(Line::from(Span::styled(format!("{indent}└{}┘", "─".repeat(inner)), Style::default().add_modifier(Modifier::DIM))));

    // Footer: status or keybindings.
    if !app.status.is_empty() {
        lines.push(Line::from(Span::styled(
            pad(&format!(" 🔔 {}", app.status), w.saturating_sub(1), Align::Left),
            Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD),
        )));
    } else {
        lines.push(Line::from(Span::styled(
            format!(
                " [j/k] Move  [n/p] Page {}/{}  [Enter] Drawer  [R]oles  [d]iff  [b]ase  [P]areto  [e] 3/3  [c/r/s/$] Sort  [?] Help  [q]uit",
                app.page + 1,
                app.total_pages()
            ),
            Style::default().fg(Color::Black).bg(Color::Cyan),
        )));
    }

    // Clip to screen height so Paragraph never scrolls the frame.
    lines.truncate(h);
    f.render_widget(Paragraph::new(lines), area);

    if app.inspecting {
        if let Some(m) = app.current() {
            let rect = modal_rect(area, 92, 32);
            let inner_w = rect.width.saturating_sub(4) as usize;
            draw_modal(f, area, rect, drawer_lines(app, m, inner_w));
        }
    } else if app.showing_roles {
        draw_modal(f, area, modal_rect(area, 86, 23), roles_lines(app));
    } else if app.showing_diff {
        draw_modal(f, area, modal_rect(area, 84, 22), diff_lines(app));
    } else if app.showing_help {
        draw_modal(f, area, modal_rect(area, 84, 23), help_lines());
    }
}

fn modal_rect(area: Rect, max_w: u16, max_h: u16) -> Rect {
    let w = max_w.min(area.width.saturating_sub(4)).max(56);
    let h = max_h.min(area.height.saturating_sub(2)).max(16);
    Rect {
        x: area.x + area.width.saturating_sub(w) / 2,
        y: area.y + area.height.saturating_sub(h) / 2,
        width: w,
        height: h,
    }
}

fn draw_modal(f: &mut Frame, _area: Rect, rect: Rect, lines: Vec<Line<'static>>) {
    f.render_widget(Clear, rect);
    let block = Block::default().borders(Borders::ALL);
    let inner = block.inner(rect);
    f.render_widget(block, rect);
    // Clip modal body to the inner rect.
    let max_rows = inner.height as usize;
    let mut clipped = lines;
    clipped.truncate(max_rows);
    f.render_widget(Paragraph::new(clipped), inner);
}

/// Wrap `" │ "`-joined cells to `inner_w` display columns.
fn wrap_cells(cells: &[String], inner_w: usize) -> Vec<String> {
    let mut rows = Vec::new();
    let mut cur = String::new();
    for c in cells {
        let piece = if cur.is_empty() { c.clone() } else { format!(" │ {c}") };
        if !cur.is_empty() && disp_width(&cur) + disp_width(&piece) > inner_w {
            rows.push(cur);
            cur = c.clone();
        } else if cur.is_empty() {
            cur = c.clone();
        } else {
            cur.push_str(&piece);
        }
    }
    if !cur.is_empty() {
        rows.push(cur);
    }
    rows
}

fn short_id(s: &str, n: usize) -> String {
    let t: String = s.chars().take(n).collect();
    if s.chars().count() > n { format!("{t}…") } else { t }
}

fn drawer_lines(app: &App, m: &Model, inner_w: usize) -> Vec<Line<'static>> {
    let p = pillars(m);
    let wide = inner_w >= 76;
    let f1 = |v: Option<f64>, suffix: &str| {
        v.filter(|x| x.is_finite())
            .map(|x| format!("{x:.1}{suffix}"))
            .unwrap_or("—".into())
    };
    let disp = if m.display.is_empty() { "Unknown".to_string() } else { m.display.clone() };
    let mut title = format!(" 🔍 {disp} [{}/{}]", app.cursor + 1, app.filtered.len());
    if m.is_new {
        title.push_str(" +NEW");
    }
    title.push_str(&format!(" {}", conf_badge(p.coverage_count)));
    let mut out = vec![Line::from(Span::styled(title, Style::default().add_modifier(Modifier::BOLD)))];

    out.push(Line::from(format!(
        "Provider: {} │ Pool: [{}] │ Tier: {}",
        if m.provider.is_empty() { "Unknown" } else { &m.provider },
        pool4(&m.pool),
        if m.tier.is_empty() { "—" } else { &m.tier },
    )));
    if let Some(sub) = m.sub_cost.as_deref().filter(|s| !s.is_empty()) {
        out.push(Line::from(format!("Sub: {sub}")));
    }
    if wide {
        out.push(Line::from(format!(
            "Ctx: {} │ Speed: {} │ In/Out: {} │ Blended: {} │ Eff: {} │ TMult: {}",
            format_ctx(p.context_length.map(|v| v as f64)),
            p.speed.map(|v| format!("{v:.0} t/s")).unwrap_or("—".into()),
            fmt_price_pair(m.price_in, m.price_out),
            m.blended_price.map(|v| format!("${v:.2}")).unwrap_or("—".into()),
            m.effective_cost.map(|v| format!("${v:.2}")).unwrap_or("—".into()),
            m.token_multiplier.map(|v| format!("×{v:.2}")).unwrap_or("—".into()),
        )));
    } else {
        out.push(Line::from(format!(
            "Ctx: {} │ Spd: {} │ $/M: {}",
            format_ctx(p.context_length.map(|v| v as f64)),
            p.speed.map(|v| format!("{v:.0}t/s")).unwrap_or("—".into()),
            fmt_price_pair(m.price_in, m.price_out)
        )));
    }

    out.push(Line::from(Span::styled("📊 BENCHMARK EVALUATIONS", Style::default().add_modifier(Modifier::BOLD))));
    let lb = m.livebench.as_ref();
    let ov = lb.and_then(|l| l.overall).map(|v| format!("{v:.1}%")).unwrap_or("—".into());
    let lb_id = lb.and_then(|l| l.model.clone()).unwrap_or("—".into());
    out.push(Line::from(format!("• LiveBench Overall: {ov} │ id: {}", short_id(&lb_id, 40))));
    if let Some(l) = lb {
        if !l.categories.is_empty() {
            let mut cats: Vec<(&String, &f64)> = l.categories.iter().collect();
            cats.sort_by(|a, b| a.0.cmp(b.0));
            let cells: Vec<String> = cats.iter().map(|(k, v)| format!("{k}: {v:.1}%")).collect();
            for row in wrap_cells(&cells, inner_w.saturating_sub(2)) {
                out.push(Line::from(format!("  {row}")));
            }
        }
        // Top-level pillar legs not present in `categories`.
        let mut extra = Vec::new();
        if !l.categories.contains_key("Coding") {
            if let Some(v) = l.coding.filter(|v| v.is_finite()) {
                extra.push(format!("Coding: {v:.1}%"));
            }
        }
        if !l.categories.contains_key("Reasoning") {
            if let Some(v) = l.reasoning.filter(|v| v.is_finite()) {
                extra.push(format!("Reasoning: {v:.1}%"));
            }
        }
        for row in wrap_cells(&extra, inner_w.saturating_sub(2)) {
            out.push(Line::from(format!("  {row}")));
        }
    }
    let elo = m.base_metrics.lm_elo.map(|v| format!("{v:.0}")).unwrap_or("—".into());
    let elo_c = p.coding_elo.map(|v| format!("{v}")).unwrap_or("—".into());
    out.push(Line::from(format!("• LMSYS Arena Elo: {elo} (Coding: {elo_c})")));
    let aa_q = m.aa_live_quality.filter(|v| v.is_finite()).map(|v| (v, "live"))
        .or_else(|| m.base_metrics.aa_quality.filter(|v| v.is_finite()).map(|v| (v, "static")));
    let aa_c = m.aa_live_coding.filter(|v| v.is_finite()).map(|v| (v, "live"))
        .or_else(|| m.base_metrics.aa_coding.filter(|v| v.is_finite()).map(|v| (v, "static")));
    let aa_r = m.base_metrics.aa_reasoning.filter(|v| v.is_finite()).map(|v| (v, "static"));
    let aa_fmt = |(v, src): (f64, &str)| format!("{v:.1} ({src})");
    if wide {
        out.push(Line::from(format!(
            "• AA Quality: {} │ Coding: {} │ Reasoning: {}",
            aa_q.map(aa_fmt).unwrap_or("—".into()),
            aa_c.map(aa_fmt).unwrap_or("—".into()),
            aa_r.map(aa_fmt).unwrap_or("—".into()),
        )));
    } else {
        out.push(Line::from(format!(
            "• AA Q: {} │ Code: {}",
            aa_q.map(aa_fmt).unwrap_or("—".into()),
            aa_c.map(aa_fmt).unwrap_or("—".into()),
        )));
    }

    out.push(Line::from(Span::styled("📐 AGENTIC ECONOMETRICS & VALUE", Style::default().add_modifier(Modifier::BOLD))));
    if wide {
        out.push(Line::from(format!(
            "• Q: {} │ Pass: {} │ FGI: {} │ AVI: {} │ BFI: {}",
            f1(m.quality(), ""),
            f1(m.p_success, "%"),
            f1(m.fgi_score, ""),
            f1(m.avi_score, ""),
            f1(m.bfi_score, ""),
        )));
    } else {
        out.push(Line::from(format!(
            "• Q: {} │ Pass: {} │ AVI: {}",
            f1(m.quality(), ""),
            f1(m.p_success, "%"),
            f1(m.avi_score, ""),
        )));
        out.push(Line::from(format!("• FGI: {} │ BFI: {}", f1(m.fgi_score, ""), f1(m.bfi_score, ""))));
    }
    out.push(Line::from(format!("• Role: {}", p.best_role)));

    let mut legs = Vec::new();
    if let Some(id) = m.model_id.as_deref().filter(|s| !s.is_empty()) {
        legs.push(format!("id: {}", short_id(id, 26)));
    }
    if let Some(a) = m.live_aliases.first() {
        legs.push(format!("live: {}", short_id(a, 26)));
    }
    if let Some(a) = m.lm_aliases.first() {
        legs.push(format!("arena: {}", short_id(a, 26)));
    }
    if let Some(a) = m.aa_aliases.first() {
        legs.push(format!("aa: {}", short_id(a, 26)));
    }
    if !legs.is_empty() {
        out.push(Line::from(Span::styled("🔗 MATCHED UPSTREAM IDS", Style::default().add_modifier(Modifier::BOLD))));
        for row in wrap_cells(&legs, inner_w.saturating_sub(2)) {
            out.push(Line::from(format!("  {row}")));
        }
    }

    let pareto = app.is_pareto_idx(app.cursor);
    out.push(Line::from(Span::styled(
        format!(
            "• Frontier Status: {}",
            if pareto { "⭐ UNDEFEATED (On Pareto Frontier)" } else { "Standard Efficiency Curve" }
        ),
        if pareto {
            Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)
        } else {
            Style::default().add_modifier(Modifier::DIM)
        },
    )));
    out.push(Line::from(Span::styled(
        "Press [Esc]/[q]/[Enter] to close │ [j/k] browse models",
        Style::default().add_modifier(Modifier::DIM),
    )));
    out
}

fn roles_lines(app: &App) -> Vec<Line<'static>> {
    let mut out = vec![Line::from(Span::styled(
        format!(" 🏆 TOP {} ROLE DISTRIBUTION & ARCHETYPES", app.filtered.len()),
        Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD),
    ))];
    if let Some(r) = &app.roles {
        for role in [&r.architecture, &r.pair_programming, &r.daily_driver, &r.boilerplate] {
            out.push(Line::from(Span::styled(
                format!("{} {}", role.icon, role.title),
                Style::default().add_modifier(Modifier::BOLD),
            )));
            out.push(Line::from(format!(
                "  🥇 Top: {} {} ({:.1}, Q{:.0}) │ 🥈 Run: {} ({:.1})",
                role.winner.name, role.winner.pool, role.winner.score, role.winner.q,
                role.runner_up.name, role.runner_up.score
            )));
            out.push(Line::from(Span::styled(role.desc, Style::default().add_modifier(Modifier::DIM))));
        }
    } else {
        out.push(Line::from("Not enough scored models for role recommendations."));
    }
    let cohort: Vec<Model> = app.filtered.iter().map(|&i| app.all[i].clone()).collect();
    let (avg_q, med, par) = cohort_summary(&cohort, &app.pareto);
    out.push(Line::from(Span::styled(
        format!("📊 TOP {} COHORT SUMMARY", app.filtered.len()),
        Style::default().add_modifier(Modifier::BOLD),
    )));
    out.push(Line::from(format!(
        "• Avg Q: {avg_q:.1} │ Median TPS: {med:.0} │ Pareto: {par} models │ Filter: {}",
        if app.tri_only { "Tri-Verified (3/3)" } else { "All Models" }
    )));
    out.push(Line::from(Span::styled(
        "Press [Esc], [q], or [R] to close",
        Style::default().add_modifier(Modifier::DIM),
    )));
    out
}

fn diff_lines(app: &App) -> Vec<Line<'static>> {
    let mut out = vec![Line::from(Span::styled(
        " ⚔️ SIDE-BY-SIDE CAPABILITY DIFF",
        Style::default().add_modifier(Modifier::BOLD),
    ))];
    let (Some(cur), Some(base)) = (app.current(), app.baseline_model()) else {
        return vec![Line::from("No models to compare.")];
    };
    out.push(Line::from(Span::styled(
        format!(
            "Selected [A]: #{} {} vs Baseline [B]: #{} {}",
            app.cursor + 1,
            cur.display,
            app.baseline + 1,
            base.display
        ),
        Style::default().add_modifier(Modifier::DIM),
    )));
    let pc = pillars(cur);
    let pb = pillars(base);
    let rows: Vec<(&str, Option<f64>, Option<f64>, bool)> = vec![
        ("Capability Q", cur.quality(), base.quality(), false),
        ("1-Turn Pass Rate", cur.p_success, base.p_success, false),
        ("Reasoning %", pc.reasoning, pb.reasoning, false),
        ("Coding %", pc.coding, pb.coding, false),
        ("Speed Throughput", pc.speed, pb.speed, false),
        ("Context Window", pc.context_length.map(|v| v as f64), pb.context_length.map(|v| v as f64), false),
        ("Prompt Price $/M", cur.price_in, base.price_in, true),
        ("Effective Task Cost", cur.effective_cost, base.effective_cost, true),
    ];
    for (label, vc, vb, lower_better) in rows {
        let (sc, sb) = (
            vc.map(|v| format!("{v:.1}")).unwrap_or("—".into()),
            vb.map(|v| format!("{v:.1}")).unwrap_or("—".into()),
        );
        let (adv, style) = match (vc, vb) {
            (Some(c), Some(b)) if c.is_finite() && b.is_finite() => {
                let d = c - b;
                if d.abs() < 0.01 {
                    ("Tied".to_string(), Style::default().add_modifier(Modifier::DIM))
                } else if (d > 0.0) != lower_better {
                    (
                        format!("+{:.1} (Sel)", d.abs()),
                        Style::default().fg(Color::Green).add_modifier(Modifier::BOLD),
                    )
                } else {
                    (
                        format!("+{:.1} (Base)", d.abs()),
                        Style::default().fg(Color::Cyan),
                    )
                }
            }
            _ => ("—".to_string(), Style::default().add_modifier(Modifier::DIM)),
        };
        out.push(Line::from(vec![
            Span::raw(format!("{label}: {sc} vs {sb} │ ")),
            Span::styled(adv, style),
        ]));
    }
    out.push(Line::from(Span::styled(
        "Press [Esc]/[q]/[d] close │ [j/k] switch model │ [b] pin baseline",
        Style::default().add_modifier(Modifier::DIM),
    )));
    out
}

fn help_lines() -> Vec<Line<'static>> {
    let mut out = vec![Line::from(Span::styled(
        " 🧭 CHECKERZ · SHORTCUTS & CAPABILITY GUIDE",
        Style::default().add_modifier(Modifier::BOLD),
    ))];
    for (keys, desc) in [
        ("j / k, ↓ / ↑", "Move cursor through models"),
        ("n / p, ] / [", "Next / Previous page (or PgDn / PgUp)"),
        ("g / G, Home/End", "Jump to top / bottom"),
        ("Enter / Space", "Open Capability Breakdown Drawer"),
        ("R", "Top-50 Role Distribution & Archetypes"),
        ("d", "Side-by-side Capability Diff vs Baseline"),
        ("b", "Pin highlighted model as Baseline [B]"),
        ("e", "Toggle Tri-Verified (3/3) vs All Evaluated"),
        ("P", "Toggle Pareto Frontier filter (⭐ only)"),
        ("/", "Live Search by name/provider/alias (Esc cancels)"),
        ("Tab / 1-6", "Filter by pool (ALL, AGY, CLD, OCG, FRT, API)"),
        ("Esc", "Clear search or reset filters + sort"),
        ("c / r / s", "Sort by Coding / Reasoning / Speed"),
        ("x / $ / v", "Sort by Context / Price $/M / AVI"),
        ("S", "Cycle through all sort criteria"),
        ("m / h", "Export Markdown / HTML to docs/reports/"),
        ("q", "Quit back to terminal"),
    ] {
        out.push(Line::from(vec![
            Span::styled(format!("{keys:<16}"), Style::default().add_modifier(Modifier::BOLD)),
            Span::raw(format!("• {desc}")),
        ]));
    }
    out.push(Line::from(Span::styled(
        "Press [Esc], [q], or [?] to close",
        Style::default().add_modifier(Modifier::DIM),
    )));
    out
}

/// Plain-text fallback table for non-TTY stdout (parity with the Python
/// `run_tui` non-tty path, which printed the one-shot CLI table).
pub fn render_text(app: &App) -> String {
    let mut out = vec![format!(
        "CHECKERZ · ONE-SHOT CAPABILITIES — {} models{}",
        app.filtered.len(),
        if app.stale_note.is_empty() { String::new() } else { format!(" · ⚠ {}", app.stale_note) }
    )];
    out.push(format!(
        "{:<5} {:<32} {:<5} {:<6} {:>6} {:>7} {:>7} {:>8} {:>6} {:>11} {}",
        "Rank", "Model", "Pool", "Conf", "Q", "Reason", "Coding", "Speed", "Ctx", "Price", "Best Role"
    ));
    for (g, &mi) in app.filtered.iter().enumerate() {
        let m = &app.all[mi];
        let p = pillars(m);
        let mut rank = format!("#{}", g + 1);
        if app.is_pareto_idx(g) {
            rank = format!("⭐{rank}");
        }
        out.push(format!(
            "{:<5} {:<32} {:<5} {:<6} {:>6} {:>7} {:>7} {:>8} {:>6} {:>11} {}",
            rank,
            format!("{}{}", if m.is_new { "+" } else { "" }, m.display.chars().take(31).collect::<String>()),
            pool4(&m.pool),
            conf_badge(p.coverage_count),
            m.quality().map(|q| format!("{q:.1}")).unwrap_or("—".into()),
            p.reasoning.map(|v| format!("{v:.1}%")).unwrap_or("—".into()),
            p.coding.map(|v| format!("{v:.1}%")).unwrap_or("—".into()),
            p.speed.map(|v| format!("{v:.0}t/s")).unwrap_or("—".into()),
            format_ctx(p.context_length.map(|v| v as f64)),
            fmt_price_pair(m.price_in, m.price_out),
            p.best_role,
        ));
    }
    if app.unmatched_count > 0 {
        out.push(format!("Unmatched (no benchmark signals): {}", app.unmatched_count));
    }
    out.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn breakpoints_match_python_sets() {
        // Compact / standard / enhanced / pricing / full.
        assert_eq!(fixed_columns(70).1.len(), 3);
        assert_eq!(fixed_columns(80).1.len(), 6);
        assert_eq!(fixed_columns(100).1.len(), 7);
        assert_eq!(fixed_columns(120).1.len(), 8);
        assert_eq!(fixed_columns(140).1.len(), 9);
    }

    #[test]
    fn table_fits_terminal() {
        for w in [70, 80, 95, 115, 135, 160] {
            let cols = columns_for(w);
            assert!(table_width(&cols) <= w, "w={w}");
        }
    }

    #[test]
    fn pad_is_width_exact_with_emoji() {
        assert_eq!(disp_width(&pad("🥇#1", 6, Align::Center)), 6);
        assert_eq!(disp_width(&pad("⭐🥇#1 long name here", 6, Align::Left)), 6);
    }

    #[test]
    fn headless_frame_renders_header_rows_and_stale() {
        use crate::app::{partition_matched, App};
        use crate::model::{BaseMetrics, Livebench, Model};
        use ratatui::{backend::TestBackend, Terminal};
        let mk = |display: &str| Model {
            display: display.into(),
            model_id: Some(display.to_lowercase()),
            pool: "api".into(),
            capability_q: Some(90.0),
            effective_cost: Some(1.0),
            price_in: Some(1.0),
            price_out: Some(1.0),
            livebench: Some(Livebench {
                overall: Some(80.0),
                categories: [("Reasoning".into(), 90.0)].into_iter().collect(),
                ..Default::default()
            }),
            base_metrics: BaseMetrics {
                lm_elo: Some(1500.0),
                aa_quality: Some(45.0),
                speed_tps: Some(100.0),
                ..Default::default()
            },
            ..Default::default()
        };
        let (matched, unmatched) = partition_matched(vec![mk("Alpha"), mk("Beta")]);
        let mut app = App::new(matched, unmatched, true, 50, "TEST STALE".into());
        let backend = TestBackend::new(140, 40);
        let mut terminal = Terminal::new(backend).unwrap();
        terminal.draw(|f| draw(f, &mut app)).unwrap();
        let text: String = terminal.backend().buffer().content().iter().map(|c| c.symbol()).collect();
        assert!(text.contains("CHECKERZ"), "header missing");
        assert!(text.contains("Alpha"), "row missing");
        assert!(text.contains("Beta"), "row missing");
        assert!(text.contains("TEST STALE"), "stale note missing");
    }

    #[test]
    fn drawer_shows_all_benchmark_data() {
        use crate::app::{partition_matched, App};
        use crate::model::{BaseMetrics, Livebench, Model};
        let m = Model {
            display: "Rich Model".into(),
            model_id: Some("rich-model".into()),
            provider: "Test".into(),
            pool: "api".into(),
            tier: "Flagship".into(),
            sub_cost: Some("Pro Plan".into()),
            price_in: Some(1.0),
            price_out: Some(2.0),
            blended_price: Some(1.2),
            effective_cost: Some(1.4),
            token_multiplier: Some(1.14),
            capability_q: Some(90.0),
            p_success: Some(80.0),
            avi_score: Some(300.0),
            bfi_score: Some(9.9),
            fgi_score: Some(70.0),
            is_new: true,
            aa_live_quality: Some(46.0),
            aa_live_coding: Some(61.0),
            context_length: Some(200000.0),
            live_aliases: vec!["rich-live-id".into()],
            lm_aliases: vec!["rich-arena-id".into()],
            aa_aliases: vec!["rich-aa-id".into()],
            livebench: Some(Livebench {
                model: Some("upstream-rich-id".into()),
                overall: Some(80.0),
                categories: [
                    ("Reasoning".into(), 90.0),
                    ("Coding".into(), 80.0),
                    ("Data Analysis".into(), 75.0),
                    ("Language".into(), 88.0),
                ]
                .into_iter()
                .collect(),
                ..Default::default()
            }),
            base_metrics: BaseMetrics {
                speed_tps: Some(100.0),
                lm_elo: Some(1500.0),
                lm_coding: Some(1480.0),
                aa_quality: Some(45.0),
                aa_coding: Some(60.0),
                ..Default::default()
            },
            ..Default::default()
        };
        let (matched, unmatched) = partition_matched(vec![m, rich_peer()]);
        let app = App::new(matched, unmatched, true, 50, String::new());
        let text: String = drawer_lines(&app, &app.all[app.filtered[0]], 88)
            .iter()
            .map(|l| l.spans.iter().map(|s| s.content.as_ref()).collect::<Vec<_>>().join(""))
            .collect::<Vec<_>>()
            .join("\n");
        for want in [
            "Data Analysis: 75.0%",
            "Language: 88.0%",
            "BFI: 9.9",
            "Blended: $1.20",
            "TMult: ×1.14",
            "Pro Plan",
            "upstream-rich-id",
            "rich-live-id",
            "rich-arena-id",
            "rich-aa-id",
            "(live)",
            "+NEW",
            "1480",
        ] {
            assert!(text.contains(want), "drawer missing {want}:\n{text}");
        }
    }

    fn rich_peer() -> crate::model::Model {
        use crate::model::{BaseMetrics, Livebench, Model};
        Model {
            display: "Peer".into(),
            capability_q: Some(70.0),
            effective_cost: Some(0.5),
            price_in: Some(0.5),
            price_out: Some(0.5),
            livebench: Some(Livebench {
                overall: Some(60.0),
                ..Default::default()
            }),
            base_metrics: BaseMetrics {
                lm_elo: Some(1300.0),
                aa_quality: Some(30.0),
                speed_tps: Some(50.0),
                ..Default::default()
            },
            ..Default::default()
        }
    }
}
