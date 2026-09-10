//! Markdown/HTML export of the active cohort (the `m` / `h` keys).

use crate::app::App;
use crate::model::{conf_badge, fmt_price_pair, format_ctx, pillars};
use std::path::Path;

fn esc_html(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for ch in s.chars() {
        match ch {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            _ => out.push(ch),
        }
    }
    out
}

pub fn render_markdown(app: &App) -> String {
    let mut lines = vec![
        "# Checkerz Capability Report".to_string(),
        String::new(),
        format!(
            "{} models ({}){}.",
            app.filtered.len(),
            if app.tri_only { "tri-verified 3/3" } else { "all evaluated" },
            if app.stale_note.is_empty() { String::new() } else { format!(" · ⚠ {}", app.stale_note) }
        ),
        String::new(),
        "| Model | Pool | Conf | Q | Reason | Coding | Speed | Ctx | Price | Role |".to_string(),
        "| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |".to_string(),
    ];
    for (g, &mi) in app.filtered.iter().enumerate() {
        let m = &app.all[mi];
        let p = pillars(m);
        let star = if app.is_pareto_idx(g) { "⭐ " } else { "" };
        let disp = m.display.replace('|', "\\|");
        lines.push(format!(
            "| {star}{disp} | {} | {} | {} | {} | {} | {} | {} | {} | {} |",
            m.pool.to_uppercase(),
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
        lines.push(String::new());
        lines.push(format!("Unmatched (no benchmark signals): {}.", app.unmatched_count));
    }
    lines.join("\n") + "\n"
}

pub fn render_html(app: &App) -> String {
    let mut rows = String::new();
    for (g, &mi) in app.filtered.iter().enumerate() {
        let m = &app.all[mi];
        let p = pillars(m);
        let cls = if app.is_pareto_idx(g) { " class=\"pareto\"" } else { "" };
        let star = if app.is_pareto_idx(g) { "⭐ " } else { "" };
        rows.push_str(&format!(
            "<tr{cls}><td>{}</td><td>{star}{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>\n",
            g + 1,
            esc_html(&m.display),
            esc_html(&m.pool.to_uppercase()),
            conf_badge(p.coverage_count),
            m.quality().map(|q| format!("{q:.1}")).unwrap_or("—".into()),
            p.reasoning.map(|v| format!("{v:.1}%")).unwrap_or("—".into()),
            p.coding.map(|v| format!("{v:.1}%")).unwrap_or("—".into()),
            p.speed.map(|v| format!("{v:.0}t/s")).unwrap_or("—".into()),
            format_ctx(p.context_length.map(|v| v as f64)),
            fmt_price_pair(m.price_in, m.price_out),
            esc_html(&p.best_role),
        ));
    }
    format!(
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<title>Checkerz Capability Report</title>\n\
        <style>body{{font-family:system-ui,sans-serif;margin:2rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:4px 8px}}.pareto td{{background:#fff8e1;font-weight:600}}.legend{{color:#555}}</style>\n\
        </head>\n<body>\n<h1>Checkerz Capability Report</h1>\n\
        <p class=\"legend\">{} models ({}){}</p>\n\
        <table>\n<thead><tr><th>#</th><th>Model</th><th>Pool</th><th>Conf</th><th>Q</th><th>Reason</th><th>Coding</th><th>Speed</th><th>Ctx</th><th>Price</th><th>Role</th></tr></thead>\n<tbody>\n{rows}</tbody>\n</table>\n</body>\n</html>\n",
        app.filtered.len(),
        if app.tri_only { "tri-verified 3/3" } else { "all evaluated" },
        if app.stale_note.is_empty() {
            String::new()
        } else {
            format!(" · ⚠ {}", esc_html(&app.stale_note))
        },
    )
}

/// Atomic write: temp file + rename, so a crash never leaves a half report.
pub fn atomic_write(path: &Path, content: &str) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension(format!(
        "{}.tmp",
        path.extension().and_then(|e| e.to_str()).unwrap_or("out")
    ));
    std::fs::write(&tmp, content)?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{BaseMetrics, Livebench, Model};

    fn app_with_two() -> App {
        let mk = |display: &str, q: f64, eff: f64| Model {
            display: display.into(),
            model_id: Some(display.to_lowercase()),
            pool: "api".into(),
            capability_q: Some(q),
            effective_cost: Some(eff),
            price_in: Some(eff),
            price_out: Some(eff),
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
        let models = vec![mk("Alpha <X>", 95.0, 9.0), mk("Beta", 75.0, 0.5)];
        let (matched, unmatched) = crate::app::partition_matched(models);
        App::new(matched, unmatched, true, 50, String::new())
    }

    #[test]
    fn markdown_has_rows_and_stars() {
        let a = app_with_two();
        let md = render_markdown(&a);
        assert!(md.contains("Alpha <X>") && md.contains("Beta"));
        assert!(md.contains('⭐'));
    }

    #[test]
    fn html_escapes_display() {
        let a = app_with_two();
        let html = render_html(&a);
        assert!(html.contains("Alpha &lt;X&gt;"));
        assert!(!html.contains("Alpha <X>"));
    }

    #[test]
    fn atomic_write_roundtrip() {
        let dir = std::env::temp_dir().join(format!("checkerz_exp_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let p = dir.join("r.md");
        atomic_write(&p, "hello").unwrap();
        assert_eq!(std::fs::read_to_string(&p).unwrap(), "hello");
        assert!(!p.with_extension("md.tmp").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
