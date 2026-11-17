//! Ratatui rendering: elastic columns, zebra rows, pareto gold, modals.

use crate::app::App;
use crate::model::{conf_badge, fmt_price_pair, fmt_task_cost, format_ctx, pillars, Model};
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

/// Pad/truncate to exactly `w` display columns using full-string display width
/// so multi-scalar emoji sequences (e.g. `🏗️`) never misalign borders.
pub fn pad(s: &str, w: usize, align: Align) -> String {
    let mut out = String::new();
    for ch in s.chars() {
        out.push(ch);
        if disp_width(&out) > w {
            out.pop();
            break;
        }
    }
    let width = disp_width(&out);
    if width >= w {
        return out;
    }
    let rem = w - width;
    match align {
        Align::Left => format!("{out}{}", " ".repeat(rem)),
        Align::Right => format!("{}{out}", " ".repeat(rem)),
        Align::Center => {
            let left = rem / 2;
            let right = rem - left;
            format!("{}{out}{}", " ".repeat(left), " ".repeat(right))
        }
    }
}

/// Fixed columns for a terminal width (before the elastic Model column).
pub fn fixed_columns(max_table_w: usize) -> (Vec<Column>, Vec<Column>) {
    let c = |name: &'static str, width: usize, align: Align| Column { name, width, align };
    if max_table_w < 78 {
        (
            vec![c("Rank", 6, Align::Center)],
            vec![
                c("Conf", 6, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("$/Task", 6, Align::Right),
            ],
        )
    } else if max_table_w < 92 {
        (
            vec![c("Rank", 6, Align::Center)],
            vec![
                c("Pool", 5, Align::Center),
                c("Conf", 6, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Arch", 6, Align::Right),
                c("Dev", 6, Align::Right),
                c("$/Task", 6, Align::Right),
            ],
        )
    } else if max_table_w < 112 {
        (
            vec![c("Rank", 6, Align::Center)],
            vec![
                c("Pool", 5, Align::Center),
                c("Conf", 6, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Arch", 6, Align::Right),
                c("Dev", 6, Align::Right),
                c("Rsch", 6, Align::Right),
                c("$/Task", 6, Align::Right),
            ],
        )
    } else if max_table_w < 132 {
        (
            vec![c("Rank", 6, Align::Center)],
            vec![
                c("Pool", 5, Align::Center),
                c("Conf", 6, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Arch", 6, Align::Right),
                c("Dev", 6, Align::Right),
                c("Rsch", 6, Align::Right),
                c("$/Task", 6, Align::Right),
                c("Price", 11, Align::Right),
            ],
        )
    } else {
        (
            vec![c("Rank", 6, Align::Center)],
            vec![
                c("Pool", 5, Align::Center),
                c("Conf", 6, Align::Center),
                c("Q(Cap)", 6, Align::Right),
                c("Arch", 6, Align::Right),
                c("Dev", 6, Align::Right),
                c("Dsgn", 6, Align::Right),
                c("Rsch", 6, Align::Right),
                c("$/Task", 6, Align::Right),
                c("Price", 11, Align::Right),
                c("Best Role", 14, Align::Left),
            ],
        )
    }
}

/// Full column list including the elastic Model column for `term_w`.
pub fn columns_for(term_w: usize) -> Vec<Column> {
    let margin = usize::from(term_w >= 90);
    let max_table_w = term_w.saturating_sub(margin * 2 + 1);
    let (before, after) = fixed_columns(max_table_w);
    let n_cols = before.len() + 1 + after.len();
    let sep_w = 3 * n_cols + 1;
    let fixed_w: usize = before.iter().chain(after.iter()).map(|c| c.width).sum();
    let mut model_w = max_table_w.saturating_sub(sep_w + fixed_w).max(14);
    if term_w >= 155 {
        model_w = model_w.min(46);
    }
    let mut cols = before;
    cols.push(Column {
        name: "Model",
        width: model_w,
        align: Align::Left,
    });
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

fn f1(v: Option<f64>) -> String {
    v.filter(|x| x.is_finite())
        .map(|x| format!("{x:.1}"))
        .unwrap_or_else(|| "—".into())
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
        "Q(Cap)" => f1(m.quality()),
        "Arch" => f1(m.roles.architecture.or(p.reasoning)),
        "Dev" => f1(m.roles.software_dev.or(p.coding)),
        "Dsgn" => f1(m.roles.design.or(p.design)),
        "Rsch" => f1(m.roles.research.or(p.research)),
        "$/Task" => fmt_task_cost(m.task_cost()),
        "Speed" => p
            .speed
            .map(|v| format!("{v:.0}t/s"))
            .unwrap_or_else(|| "—".into()),
        "Ctx" => format_ctx(p.context_length.map(|v| v as f64)),
        "Price" => fmt_price_pair(m.price_in, m.price_out),
        "Best Role" => p.best_role,
        _ => "—".to_string(),
    }
}

fn row_style(selected: bool, pareto: bool, odd: bool) -> Style {
    if selected {
        if pareto {
            Style::default()
                .fg(Color::Black)
                .bg(Color::Yellow)
                .add_modifier(Modifier::BOLD)
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
    let start = if total == 0 {
        0
    } else {
        app.page * app.page_size + 1
    };
    let end = ((app.page + 1) * app.page_size).min(total);
    let title = "⚡ CHECKERZ · 5-AXIS & 4-ROLE RADAR".to_string();
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
    let q = if app.query.is_empty() {
        "None ([/] filter)".to_string()
    } else {
        format!("\"{}\"", app.query)
    };
    let pareto = if app.pareto_only { " [⭐ PARETO ONLY]" } else { "" };
    let mut s = format!(
        " Filter: {q}{pareto} │ 7 Authorities: AA · Vals · Arena · LiveBench · FrontierCode · FrontierSWE · CursorBench"
    );
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
        Style::default()
            .fg(Color::Black)
            .bg(Color::Cyan)
            .add_modifier(Modifier::BOLD),
    )));

    if app.searching {
        lines.push(Line::from(Span::styled(
            pad(
                &format!(
                    " 🔍 Search: {}█  ({} matches)  — [Enter] commit, [Esc] cancel",
                    app.query,
                    app.filtered.len()
                ),
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
    lines.push(Line::from(Span::styled(
        format!("{indent}┌{}┐", "─".repeat(inner)),
        Style::default().add_modifier(Modifier::DIM),
    )));
    let hdr_cells: Vec<String> = cols.iter().map(|c| pad(c.name, c.width, c.align)).collect();
    lines.push(Line::from(Span::styled(
        format!("{indent}│ {} │", hdr_cells.join(" │ ")),
        Style::default().add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(Span::styled(
        format!("{indent}├{}┤", "─".repeat(inner)),
        Style::default().add_modifier(Modifier::DIM),
    )));

    let page_start = app.page * app.page_size;
    for r in 0..app.page_size {
        if page_start + r >= app.filtered.len() {
            if r == 0 && app.filtered.is_empty() {
                let msg = pad(
                    " No models match current filter/pool. Press [Esc] to reset.",
                    inner,
                    Align::Left,
                );
                lines.push(Line::from(Span::styled(
                    format!("{indent}│{msg}│"),
                    Style::default()
                        .fg(Color::Yellow)
                        .add_modifier(Modifier::BOLD),
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
        let cells: Vec<String> = cols
            .iter()
            .map(|c| pad(&cell_value(c.name, m, &rank), c.width, c.align))
            .collect();
        let mark = if g == app.cursor { "▶" } else { "│" };
        lines.push(Line::from(Span::styled(
            format!("{indent}{mark} {} │", cells.join(" │ ")),
            row_style(g == app.cursor, pareto, r % 2 == 1),
        )));
    }
    lines.push(Line::from(Span::styled(
        format!("{indent}└{}┘", "─".repeat(inner)),
        Style::default().add_modifier(Modifier::DIM),
    )));

    if !app.status.is_empty() {
        lines.push(Line::from(Span::styled(
            pad(&format!(" 🔔 {}", app.status), w.saturating_sub(1), Align::Left),
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        )));
    } else {
        lines.push(Line::from(Span::styled(
            format!(
                " [j/k] Move  [n/p] Page {}/{}  [Enter] Drawer  [R]oles  [d]iff  [P]areto  [e] 3+/7  [a/c/u/r/$] Sort  [?] Help  [q]uit",
                app.page + 1,
                app.total_pages()
            ),
            Style::default().fg(Color::Black).bg(Color::Cyan),
        )));
    }

    lines.truncate(h);
    f.render_widget(Paragraph::new(lines), area);

    if app.inspecting {
        if let Some(m) = app.current() {
            let rect = modal_rect(area, 94, 34);
            let inner_w = rect.width.saturating_sub(4) as usize;
            draw_modal(f, rect, drawer_lines(app, m, inner_w));
        }
    } else if app.showing_roles {
        draw_modal(f, modal_rect(area, 88, 23), roles_lines(app));
    } else if app.showing_diff {
        draw_modal(f, modal_rect(area, 86, 23), diff_lines(app));
    } else if app.showing_help {
        draw_modal(f, modal_rect(area, 86, 24), help_lines());
    }
}

fn modal_rect(area: Rect, max_w: u16, max_h: u16) -> Rect {
    let w = max_w
        .min(area.width.saturating_sub(4))
        .max(area.width.min(56));
    let h = max_h
        .min(area.height.saturating_sub(2))
        .max(area.height.min(8));
    Rect {
        x: area.x + area.width.saturating_sub(w) / 2,
        y: area.y + area.height.saturating_sub(h) / 2,
        width: w,
        height: h,
    }
}

fn draw_modal(f: &mut Frame, rect: Rect, lines: Vec<Line<'static>>) {
    f.render_widget(Clear, rect);
    let block = Block::default().borders(Borders::ALL);
    let inner = block.inner(rect);
    f.render_widget(block, rect);
    let max_rows = inner.height as usize;
    let mut clipped = lines;
    clipped.truncate(max_rows);
    f.render_widget(Paragraph::new(clipped), inner);
}

fn wrap_cells(cells: &[String], inner_w: usize) -> Vec<String> {
    let mut rows = Vec::new();
    let mut cur = String::new();
    for c in cells {
        let piece = if cur.is_empty() {
            c.clone()
        } else {
            format!(" │ {c}")
        };
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
    if s.chars().count() > n {
        format!("{t}…")
    } else {
        t
    }
}

#[allow(clippy::too_many_lines)]
fn drawer_lines(app: &App, m: &Model, inner_w: usize) -> Vec<Line<'static>> {
    let p = pillars(m);
    let bm = &m.base_metrics;
    let wide = inner_w >= 76;
    let fmt_s = |v: Option<f64>, suffix: &str| {
        v.filter(|x| x.is_finite())
            .map(|x| format!("{x:.1}{suffix}"))
            .unwrap_or_else(|| "—".into())
    };
    let disp = if m.display.is_empty() {
        "Unknown".to_string()
    } else {
        m.display.clone()
    };
    let mut title = format!(" 🔍 {disp} [{}/{}]", app.cursor + 1, app.filtered.len());
    if let Some(eff) = m.effort.as_deref().filter(|s| !s.is_empty()) {
        title.push_str(&format!(" · Thinking: {}", eff.to_uppercase()));
    }
    if m.is_new {
        title.push_str(" +NEW");
    }
    title.push_str(&format!(" {}", conf_badge(p.coverage_count)));
    let mut out = vec![Line::from(Span::styled(
        title,
        Style::default().add_modifier(Modifier::BOLD),
    ))];

    out.push(Line::from(format!(
        "Provider: {} │ Pool: [{}] │ Tier: {}",
        if m.provider.is_empty() {
            "Unknown"
        } else {
            &m.provider
        },
        pool4(&m.pool),
        if m.tier.is_empty() { "—" } else { &m.tier },
    )));
    if let Some(sub) = m.sub_cost.as_deref().filter(|s| !s.is_empty()) {
        out.push(Line::from(format!("Sub: {sub}")));
    }
    if wide {
        out.push(Line::from(format!(
            "Ctx: {} │ Speed: {} │ In/Out: {} │ Blended: {} │ $/Task: {}",
            format_ctx(p.context_length.map(|v| v as f64)),
            p.speed
                .map(|v| format!("{v:.0} t/s"))
                .unwrap_or_else(|| "—".into()),
            fmt_price_pair(m.price_in, m.price_out),
            m.blended_price
                .map(|v| format!("${v:.2}"))
                .unwrap_or_else(|| "—".into()),
            fmt_task_cost(m.task_cost()),
        )));
    } else {
        out.push(Line::from(format!(
            "Ctx: {} │ Spd: {} │ $/Task: {} │ $/M: {}",
            format_ctx(p.context_length.map(|v| v as f64)),
            p.speed
                .map(|v| format!("{v:.0}t/s"))
                .unwrap_or_else(|| "—".into()),
            fmt_task_cost(m.task_cost()),
            fmt_price_pair(m.price_in, m.price_out),
        )));
    }

    let active_auths: Vec<&str> = [
        (p.has_aa, "AA"),
        (p.has_vals, "Vals"),
        (p.has_arena, "Arena"),
        (p.has_live, "LiveBench"),
        (p.has_fc2, "FrontierCode"),
        (p.has_fswe, "FrontierSWE"),
        (p.has_cursor, "CursorBench"),
    ]
    .into_iter()
    .filter_map(|(ok, label)| ok.then_some(label))
    .collect();
    out.push(Line::from(Span::styled(
        format!(
            "📊 7-AUTHORITY EVALUATIONS ({})",
            if active_auths.is_empty() {
                "none".to_string()
            } else {
                active_auths.join(" · ")
            }
        ),
        Style::default().add_modifier(Modifier::BOLD),
    )));
    out.push(Line::from(format!(
        "• CursorBench 4.0: {} (Cost: {}, Steps: {}) │ FrontierCode 2.0: {} (Cost: {})",
        fmt_s(bm.cursor_score, "%"),
        fmt_task_cost(bm.cursor_cost),
        fmt_s(bm.cursor_steps, ""),
        fmt_s(bm.fc2_score, "%"),
        fmt_task_cost(bm.fc2_cost),
    )));
    out.push(Line::from(format!(
        "• FrontierSWE: {} (Impl: {}, Perf: {}, Rsch: {})",
        fmt_s(bm.fswe_overall, "%"),
        fmt_s(bm.fswe_impl, "%"),
        fmt_s(bm.fswe_perf, "%"),
        fmt_s(bm.fswe_research, "%"),
    )));

    let aa_q = m
        .aa_live_quality
        .filter(|v| v.is_finite())
        .map(|v| format!("{v:.1} (live)"))
        .or_else(|| {
            bm.aa_quality
                .filter(|v| v.is_finite())
                .map(|v| format!("{v:.1} (static)"))
        })
        .unwrap_or_else(|| "—".into());
    out.push(Line::from(format!(
        "• AA v5: {aa_q} │ HLE: {} │ CritPt: {} │ TB-4: {} │ Non-Halluc: {} │ LCR: {}",
        fmt_s(bm.aa_hle, "%"),
        fmt_s(bm.aa_critpt, "%"),
        fmt_s(bm.aa_tb4, "%"),
        fmt_s(bm.aa_non_halluc, "%"),
        fmt_s(bm.aa_lcr, "%"),
    )));
    out.push(Line::from(format!(
        "• Vals Index: {} (Code: {}, Term: {}) │ Arena Elo: {} (Code: {}, WebDev: {})",
        fmt_s(m.vals_overall, "%"),
        fmt_s(m.vals_coding, "%"),
        fmt_s(m.vals_terminal, "%"),
        bm.lm_elo
            .map(|v| format!("{v:.0}"))
            .unwrap_or_else(|| "—".into()),
        p.coding_elo
            .map(|v| format!("{v}"))
            .unwrap_or_else(|| "—".into()),
        bm.lm_webdev_elo
            .map(|v| format!("{v:.0}"))
            .unwrap_or_else(|| "—".into()),
    )));

    let lb = m.livebench.as_ref();
    let ov = lb
        .and_then(|l| l.overall)
        .map(|v| format!("{v:.1}%"))
        .unwrap_or_else(|| "—".into());
    let lb_id = lb.and_then(|l| l.model.clone()).unwrap_or_else(|| "—".into());
    out.push(Line::from(format!(
        "• LiveBench Overall: {ov} │ id: {}",
        short_id(&lb_id, 40)
    )));
    if let Some(l) = lb {
        if !l.categories.is_empty() {
            let mut cats: Vec<(&String, &f64)> = l.categories.iter().collect();
            cats.sort_by(|a, b| a.0.cmp(b.0));
            let cells: Vec<String> = cats.iter().map(|(k, v)| format!("{k}: {v:.1}%")).collect();
            for row in wrap_cells(&cells, inner_w.saturating_sub(2)) {
                out.push(Line::from(format!("  {row}")));
            }
        }
    }

    out.push(Line::from(Span::styled(
        "🧭 5 SHRUNK AXES & 4 TASK ROLES",
        Style::default().add_modifier(Modifier::BOLD),
    )));
    out.push(Line::from(format!(
        "• Q: {} │ Axes -> Reason: {} │ Coding: {} │ Design: {} │ Research: {} │ Econ: {}",
        fmt_s(m.quality(), ""),
        fmt_s(p.reasoning, ""),
        fmt_s(p.coding, ""),
        fmt_s(p.design, ""),
        fmt_s(p.research, ""),
        fmt_s(p.economics, ""),
    )));
    out.push(Line::from(format!(
        "• Roles -> 🏗️ Arch: {} │ 💻 Dev: {} │ 🎨 Dsgn: {} │ 🔬 Rsch: {} │ Best: {}",
        fmt_s(m.roles.architecture, ""),
        fmt_s(m.roles.software_dev, ""),
        fmt_s(m.roles.design, ""),
        fmt_s(m.roles.research, ""),
        p.best_role,
    )));

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
        out.push(Line::from(Span::styled(
            "🔗 MATCHED UPSTREAM IDS",
            Style::default().add_modifier(Modifier::BOLD),
        )));
        for row in wrap_cells(&legs, inner_w.saturating_sub(2)) {
            out.push(Line::from(format!("  {row}")));
        }
    }

    let pareto = app.is_pareto_idx(app.cursor);
    out.push(Line::from(Span::styled(
        format!(
            "• Frontier Status: {}",
            if pareto {
                "⭐ UNDEFEATED (On Priced $/Task Pareto Frontier)"
            } else {
                "Standard Efficiency Curve"
            }
        ),
        if pareto {
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD)
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
        format!(" 🏆 TOP {} TASK-ROLE RECOMMENDATIONS", app.filtered.len()),
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    ))];
    if let Some(r) = &app.roles {
        for role in [&r.architecture, &r.software_dev, &r.design, &r.research] {
            out.push(Line::from(Span::styled(
                format!("{} {}", role.icon, role.title),
                Style::default().add_modifier(Modifier::BOLD),
            )));
            out.push(Line::from(format!(
                "  🥇 Top: {} {} ({:.1}, Q{:.0}) │ 🥈 Run: {} ({:.1})",
                role.winner.name,
                role.winner.pool,
                role.winner.score,
                role.winner.q,
                role.runner_up.name,
                role.runner_up.score
            )));
            out.push(Line::from(Span::styled(
                role.desc,
                Style::default().add_modifier(Modifier::DIM),
            )));
        }
    } else {
        out.push(Line::from(
            "Not enough scored models for role recommendations.",
        ));
    }
    let cohort: Vec<&Model> = app.filtered.iter().map(|&i| &app.all[i]).collect();
    let (avg_q, med, par) = cohort_summary(&cohort, &app.pareto);
    out.push(Line::from(Span::styled(
        format!("📊 TOP {} COHORT SUMMARY", app.filtered.len()),
        Style::default().add_modifier(Modifier::BOLD),
    )));
    out.push(Line::from(format!(
        "• Avg Q: {avg_q:.1} │ Median TPS: {med:.0} │ Pareto: {par} models │ Filter: {}",
        if app.multi_only {
            "Multi-Source (3+/7)"
        } else {
            "All Models"
        }
    )));
    out.push(Line::from(Span::styled(
        "Press [Esc], [q], or [R] to close",
        Style::default().add_modifier(Modifier::DIM),
    )));
    out
}

fn diff_lines(app: &App) -> Vec<Line<'static>> {
    let mut out = vec![Line::from(Span::styled(
        " ⚔️ SIDE-BY-SIDE CAPABILITY & ROLE DIFF",
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
        (
            "Role: Architecture",
            cur.roles.architecture.or(pc.reasoning),
            base.roles.architecture.or(pb.reasoning),
            false,
        ),
        (
            "Role: Software Dev",
            cur.roles.software_dev.or(pc.coding),
            base.roles.software_dev.or(pb.coding),
            false,
        ),
        (
            "Role: Design",
            cur.roles.design.or(pc.design),
            base.roles.design.or(pb.design),
            false,
        ),
        (
            "Role: Research",
            cur.roles.research.or(pc.research),
            base.roles.research.or(pb.research),
            false,
        ),
        (
            "CursorBench 4.0 %",
            cur.base_metrics.cursor_score,
            base.base_metrics.cursor_score,
            false,
        ),
        (
            "FrontierCode 2.0 %",
            cur.base_metrics.fc2_score,
            base.base_metrics.fc2_score,
            false,
        ),
        ("Speed TPS", pc.speed, pb.speed, false),
        ("Empirical $/Task", cur.task_cost(), base.task_cost(), true),
        ("Prompt Price $/M", cur.price_in, base.price_in, true),
    ];
    for (label, vc, vb, lower_better) in rows {
        let (sc, sb) = (
            vc.map(|v| format!("{v:.2}")).unwrap_or_else(|| "—".into()),
            vb.map(|v| format!("{v:.2}")).unwrap_or_else(|| "—".into()),
        );
        let (adv, style) = match (vc, vb) {
            (Some(c), Some(b)) if c.is_finite() && b.is_finite() => {
                let d = c - b;
                if d.abs() < 0.01 {
                    ("Tied".to_string(), Style::default().add_modifier(Modifier::DIM))
                } else if (d > 0.0) != lower_better {
                    (
                        format!("+{:.2} (Sel)", d.abs()),
                        Style::default()
                            .fg(Color::Green)
                            .add_modifier(Modifier::BOLD),
                    )
                } else {
                    (
                        format!("+{:.2} (Base)", d.abs()),
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
        " 🧭 CHECKERZ · SHORTCUTS & 7-AUTHORITY GUIDE",
        Style::default().add_modifier(Modifier::BOLD),
    ))];
    for (keys, desc) in [
        ("j / k, ↓ / ↑", "Move cursor through models"),
        ("n / p, ] / [", "Next / Previous page (or PgDn / PgUp)"),
        ("g / G, Home/End", "Jump to top / bottom"),
        ("Enter / Space", "Open 7-Authority & 5-Axis Drawer"),
        ("R", "Task-Role Recommendations (Arch, Dev, Design, Research)"),
        ("d / b", "Side-by-side Diff vs Baseline / Pin Baseline [B]"),
        ("e", "Toggle Multi-Source (3+/7) vs All Evaluated"),
        ("P", "Toggle Priced $/Task Pareto Frontier filter (⭐ only)"),
        ("/", "Live Search by name/effort/provider/alias (Esc cancels)"),
        ("Tab / 1-8", "Filter by pool (ALL, AGY, CLD, OCG, FRT, API, HTZ, NVD)"),
        ("Esc", "Clear search or reset filters + sort"),
        ("a / c / u / r", "Sort by Arch / Soft Dev / Design / Research"),
        ("$ / s / x / v", "Sort by $/Task / Speed / Context / AVI"),
        ("S / o", "Cycle through all sort criteria (incl. Cursor & FC2)"),
        ("m / h", "Export Markdown / HTML to docs/reports/"),
        ("q", "Quit back to terminal"),
    ] {
        out.push(Line::from(vec![
            Span::styled(
                format!("{keys:<16}"),
                Style::default().add_modifier(Modifier::BOLD),
            ),
            Span::raw(format!("• {desc}")),
        ]));
    }
    out.push(Line::from(Span::styled(
        "Press [Esc], [q], or [?] to close",
        Style::default().add_modifier(Modifier::DIM),
    )));
    out
}

/// Plain-text fallback table for non-TTY stdout.
pub fn render_text(app: &App) -> String {
    let mut out = vec![format!(
        "CHECKERZ · 5-AXIS & 4-ROLE RADAR — {} models{}",
        app.filtered.len(),
        if app.stale_note.is_empty() {
            String::new()
        } else {
            format!(" · ⚠ {}", app.stale_note)
        }
    )];
    out.push(format!(
        "{:<6} {:<30} {:<5} {:<6} {:>6} {:>6} {:>6} {:>6} {:>6} {:>8} {:>11} {}",
        "Rank",
        "Model",
        "Pool",
        "Conf",
        "Q",
        "Arch",
        "Dev",
        "Dsgn",
        "Rsch",
        "$/Task",
        "Price",
        "Best Role"
    ));
    for (g, &mi) in app.filtered.iter().enumerate() {
        let m = &app.all[mi];
        let p = pillars(m);
        let mut rank = format!("#{}", g + 1);
        if app.is_pareto_idx(g) {
            rank = format!("⭐{rank}");
        }
        out.push(format!(
            "{} {:<30} {:<5} {:<6} {:>6} {:>6} {:>6} {:>6} {:>6} {:>8} {:>11} {}",
            pad(&rank, 6, Align::Left),
            format!(
                "{}{}",
                if m.is_new { "+" } else { "" },
                m.display.chars().take(29).collect::<String>()
            ),
            pool4(&m.pool),
            conf_badge(p.coverage_count),
            f1(m.quality()),
            f1(m.roles.architecture.or(p.reasoning)),
            f1(m.roles.software_dev.or(p.coding)),
            f1(m.roles.design.or(p.design)),
            f1(m.roles.research.or(p.research)),
            fmt_task_cost(m.task_cost()),
            fmt_price_pair(m.price_in, m.price_out),
            p.best_role,
        ));
    }
    if app.unmatched_count > 0 {
        out.push(format!(
            "Unmatched (no benchmark signals): {}",
            app.unmatched_count
        ));
    }
    out.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn breakpoints_match_responsive_sets() {
        assert_eq!(fixed_columns(70).1.len(), 3);
        assert_eq!(fixed_columns(80).1.len(), 6);
        assert_eq!(fixed_columns(100).1.len(), 7);
        assert_eq!(fixed_columns(120).1.len(), 8);
        assert_eq!(fixed_columns(140).1.len(), 10);
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
        assert_eq!(disp_width(&pad("🏗️ Architect", 14, Align::Left)), 14);
        assert_eq!(pad("⭐🥇#1", 6, Align::Center), "⭐🥇#1");
    }

    #[test]
    fn modal_rect_fits_minimum_terminal() {
        let small = Rect::new(0, 0, 60, 12);
        let r = modal_rect(small, 92, 32);
        assert!(r.height <= small.height);
        assert!(r.width <= small.width);
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
        let text: String = terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|c| c.symbol())
            .collect();
        assert!(text.contains("CHECKERZ"), "header missing");
        assert!(text.contains("Alpha"), "row missing");
        assert!(text.contains("Beta"), "row missing");
        assert!(text.contains("TEST STALE"), "stale note missing");
    }

    #[test]
    fn drawer_shows_seven_authorities_and_roles() {
        use crate::app::{partition_matched, App};
        use crate::model::{Axes, BaseMetrics, Livebench, Model, Roles};
        let m = Model {
            display: "Gemini 4 Carbon (High)".into(),
            effort: Some("high".into()),
            model_id: Some("gemini-4-carbon-high".into()),
            provider: "Google".into(),
            pool: "agy".into(),
            tier: "Flagship".into(),
            sub_cost: Some("AGY Plan".into()),
            price_in: Some(4.0),
            price_out: Some(20.0),
            blended_price: Some(7.2),
            empirical_cost: Some(7.2),
            effective_cost: Some(7.2),
            capability_q: Some(88.9),
            axes: Axes {
                reasoning: Some(94.8),
                coding: Some(89.7),
                design: Some(91.4),
                research: Some(87.0),
                economics: Some(71.2),
            },
            roles: Roles {
                architecture: Some(90.1),
                software_dev: Some(85.4),
                design: Some(87.1),
                research: Some(88.7),
            },
            best_role: Some("🏗️ Architect".into()),
            is_new: true,
            aa_live_quality: Some(60.0),
            context_length: Some(1_000_000.0),
            live_aliases: vec!["rich-live-id".into()],
            lm_aliases: vec!["rich-arena-id".into()],
            aa_aliases: vec!["rich-aa-id".into()],
            livebench: Some(Livebench {
                model: Some("upstream-rich-id".into()),
                overall: Some(80.0),
                categories: [("Reasoning".into(), 90.0), ("Data Analysis".into(), 75.0)]
                    .into_iter()
                    .collect(),
                ..Default::default()
            }),
            base_metrics: BaseMetrics {
                speed_tps: Some(66.0),
                lm_elo: Some(1768.0),
                lm_coding: Some(1792.0),
                cursor_score: Some(60.4),
                cursor_cost: Some(9.22),
                fc2_score: Some(42.6),
                fc2_cost: Some(5.06),
                fswe_overall: Some(61.2),
                aa_hle: Some(69.1),
                ..Default::default()
            },
            ..Default::default()
        };
        let (matched, unmatched) = partition_matched(vec![m, rich_peer()]);
        let app = App::new(matched, unmatched, true, 50, String::new());
        let text: String = drawer_lines(&app, &app.all[app.filtered[0]], 90)
            .iter()
            .map(|l| {
                l.spans
                    .iter()
                    .map(|s| s.content.as_ref())
                    .collect::<Vec<_>>()
                    .join("")
            })
            .collect::<Vec<_>>()
            .join("\n");
        for want in [
            "Thinking: HIGH",
            "CursorBench 4.0: 60.4%",
            "FrontierCode 2.0: 42.6%",
            "FrontierSWE: 61.2%",
            "HLE: 69.1%",
            "Data Analysis: 75.0%",
            "Arch: 90.1",
            "Dev: 85.4",
            "AGY Plan",
            "upstream-rich-id",
            "rich-live-id",
            "+NEW",
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
