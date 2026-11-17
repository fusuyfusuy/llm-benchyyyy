//! Data contract: `docs/data/benchmarks.json` rows + 7-authority capability pillars.
//!
//! Consumes precomputed shrunk axes and task roles from `checkers/benchmark_common.py`
//! and `checkers/llm_benchmark_aggregator.py` (single Python scoring authority).

use serde::Deserialize;
use std::collections::HashMap;

/// Real number for scoring: finite, never NaN/Inf (mirrors `_is_num`).
pub fn is_num(v: Option<f64>) -> bool {
    matches!(v, Some(x) if x.is_finite())
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct Axes {
    #[serde(default)]
    pub reasoning: Option<f64>,
    #[serde(default)]
    pub coding: Option<f64>,
    #[serde(default)]
    pub design: Option<f64>,
    #[serde(default)]
    pub research: Option<f64>,
    #[serde(default)]
    pub economics: Option<f64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct Roles {
    #[serde(default)]
    pub architecture: Option<f64>,
    #[serde(default)]
    pub software_dev: Option<f64>,
    #[serde(default)]
    pub design: Option<f64>,
    #[serde(default)]
    pub research: Option<f64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct BaseMetrics {
    #[serde(default)]
    pub speed_tps: Option<f64>,
    #[serde(default)]
    pub lm_elo: Option<f64>,
    #[serde(default)]
    pub lm_coding: Option<f64>,
    #[serde(default)]
    pub lm_webdev_elo: Option<f64>,
    #[serde(default)]
    pub aa_quality: Option<f64>,
    #[serde(default)]
    pub aa_coding: Option<f64>,
    #[serde(default)]
    pub aa_reasoning: Option<f64>,
    #[serde(default)]
    pub aa_hle: Option<f64>,
    #[serde(default)]
    pub aa_critpt: Option<f64>,
    #[serde(default)]
    pub aa_tb4: Option<f64>,
    #[serde(default)]
    pub aa_lcr: Option<f64>,
    #[serde(default)]
    pub aa_non_halluc: Option<f64>,
    #[serde(default)]
    pub aa_ifbench: Option<f64>,
    #[serde(default)]
    pub aa_gpqa: Option<f64>,
    #[serde(default)]
    pub fc2_score: Option<f64>,
    #[serde(default)]
    pub fc2_cost: Option<f64>,
    #[serde(default)]
    pub fswe_overall: Option<f64>,
    #[serde(default)]
    pub fswe_impl: Option<f64>,
    #[serde(default)]
    pub fswe_perf: Option<f64>,
    #[serde(default)]
    pub fswe_research: Option<f64>,
    #[serde(default)]
    pub cursor_score: Option<f64>,
    #[serde(default)]
    pub cursor_cost: Option<f64>,
    #[serde(default)]
    pub cursor_steps: Option<f64>,
    #[serde(default)]
    pub context_length: Option<f64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct Livebench {
    #[serde(default)]
    pub model: Option<String>,
    #[serde(default)]
    pub overall: Option<f64>,
    #[serde(default)]
    pub coding: Option<f64>,
    #[serde(default)]
    pub reasoning: Option<f64>,
    #[serde(default)]
    pub categories: HashMap<String, f64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct Model {
    #[serde(default)]
    pub display: String,
    #[serde(default)]
    pub effort: Option<String>,
    #[serde(default)]
    pub provider: String,
    #[serde(default)]
    pub pool: String,
    #[serde(default)]
    pub tier: String,
    #[serde(default)]
    pub sub_cost: Option<String>,
    #[serde(default)]
    pub price_in: Option<f64>,
    #[serde(default)]
    pub price_out: Option<f64>,
    #[serde(default)]
    pub live_aliases: Vec<String>,
    #[serde(default)]
    pub lm_aliases: Vec<String>,
    #[serde(default)]
    pub aa_aliases: Vec<String>,
    #[serde(default)]
    pub model_id: Option<String>,
    #[serde(default)]
    pub signal_mirror_of: Option<String>,
    #[serde(default)]
    pub base_metrics: BaseMetrics,
    #[serde(default)]
    pub livebench: Option<Livebench>,
    #[serde(default)]
    pub aa_live_quality: Option<f64>,
    #[serde(default)]
    pub aa_live_coding: Option<f64>,
    #[serde(default)]
    pub vals_overall: Option<f64>,
    #[serde(default)]
    pub vals_coding: Option<f64>,
    #[serde(default)]
    pub vals_terminal: Option<f64>,
    #[serde(default)]
    pub context_length: Option<f64>,
    #[serde(default)]
    pub capability_q: Option<f64>,
    #[serde(default)]
    pub composite_score: Option<f64>,
    #[serde(default)]
    pub axes: Axes,
    #[serde(default)]
    pub roles: Roles,
    #[serde(default)]
    pub best_role: Option<String>,
    #[serde(default)]
    pub empirical_cost: Option<f64>,
    #[serde(default)]
    pub effective_cost: Option<f64>,
    #[serde(default)]
    pub blended_price: Option<f64>,
    #[serde(default)]
    pub avi_score: Option<f64>,
    #[serde(default)]
    pub is_new: bool,
    #[serde(default)]
    pub unmatched: bool,
}

impl Model {
    /// Every stable identity leg this row can match on (display + model_id + aliases).
    pub fn stable_ids(&self) -> Vec<&str> {
        let mut ids = Vec::with_capacity(8);
        if !self.display.is_empty() {
            ids.push(self.display.as_str());
        }
        if let Some(id) = self.model_id.as_deref().filter(|s| !s.is_empty()) {
            ids.push(id);
        }
        for a in self
            .aa_aliases
            .iter()
            .chain(self.lm_aliases.iter())
            .chain(self.live_aliases.iter())
        {
            if !a.is_empty() {
                ids.push(a.as_str());
            }
        }
        ids
    }

    pub fn quality(&self) -> Option<f64> {
        self.capability_q
            .filter(|v| v.is_finite())
            .or_else(|| self.composite_score.filter(|v| v.is_finite()))
    }

    /// Empirical agentic $/task when available, else blended effective cost.
    pub fn task_cost(&self) -> Option<f64> {
        self.empirical_cost
            .filter(|v| v.is_finite())
            .or_else(|| self.effective_cost.filter(|v| v.is_finite()))
    }
}

#[derive(Debug, Clone)]
pub struct Pillars {
    pub reasoning: Option<f64>,
    pub coding: Option<f64>,
    pub design: Option<f64>,
    pub research: Option<f64>,
    pub economics: Option<f64>,
    pub coding_elo: Option<i64>,
    pub speed: Option<f64>,
    pub context_length: Option<i64>,
    pub coverage_count: u8,
    pub has_arena: bool,
    pub has_aa: bool,
    pub has_vals: bool,
    pub has_live: bool,
    pub has_fc2: bool,
    pub has_fswe: bool,
    pub has_cursor: bool,
    pub best_role: String,
}

fn infer_best_role(m: &Model, coverage_count: u8) -> String {
    if let Some(r) = m.best_role.as_deref().filter(|s| !s.is_empty()) {
        return r.to_string();
    }
    let candidates = [
        (m.roles.architecture, "🏗️ Architect"),
        (m.roles.software_dev, "💻 Soft Dev"),
        (m.roles.design, "🎨 Design"),
        (m.roles.research, "🔬 Research"),
    ];
    let mut best: Option<(f64, &str)> = None;
    for (val, label) in candidates {
        if let Some(v) = val.filter(|x| x.is_finite()) {
            if best.is_none_or(|(bv, _)| v > bv) {
                best = Some((v, label));
            }
        }
    }
    if let Some((_, label)) = best {
        return label.to_string();
    }
    match m.quality() {
        None if coverage_count == 0 => "—".to_string(),
        Some(q) if q >= 84.0 => "🏗️ Architect".to_string(),
        Some(q) if q >= 75.0 => "💻 Soft Dev".to_string(),
        Some(_) => "⚡ Lightweight".to_string(),
        None => "—".to_string(),
    }
}

/// Normalized capability dimensions across all 7 upstream authorities:
/// AA, Vals, LMArena, LiveBench, FrontierCode 2.0, FrontierSWE, CursorBench 4.0.
pub fn pillars(m: &Model) -> Pillars {
    let live = m.livebench.as_ref();
    let bm = &m.base_metrics;

    let reasoning = m
        .axes
        .reasoning
        .filter(|v| v.is_finite())
        .or_else(|| m.aa_live_quality.filter(|v| v.is_finite()))
        .or_else(|| bm.aa_quality.filter(|v| v.is_finite()))
        .or_else(|| bm.aa_reasoning.filter(|v| v.is_finite()))
        .or_else(|| live.and_then(|l| l.reasoning).filter(|v| v.is_finite()));

    let coding = m
        .axes
        .coding
        .filter(|v| v.is_finite())
        .or_else(|| bm.cursor_score.filter(|v| v.is_finite()))
        .or_else(|| bm.fc2_score.filter(|v| v.is_finite()))
        .or_else(|| bm.fswe_overall.filter(|v| v.is_finite()))
        .or_else(|| m.aa_live_coding.filter(|v| v.is_finite()))
        .or_else(|| bm.aa_coding.filter(|v| v.is_finite()))
        .or_else(|| live.and_then(|l| l.coding).filter(|v| v.is_finite()));

    let design = m.axes.design.filter(|v| v.is_finite());
    let research = m.axes.research.filter(|v| v.is_finite());
    let economics = m.axes.economics.filter(|v| v.is_finite());

    let coding_elo = bm.lm_coding.filter(|v| v.is_finite()).map(|v| v.round() as i64);
    let speed = bm.speed_tps.filter(|v| v.is_finite());
    let ctx = m
        .context_length
        .or(bm.context_length)
        .filter(|v| v.is_finite() && *v > 0.0)
        .map(|v| v as i64);

    let has_arena = [bm.lm_elo, bm.lm_coding, bm.lm_webdev_elo]
        .into_iter()
        .any(|v| v.is_some_and(|x| x.is_finite()));
    let has_aa = [
        m.aa_live_quality,
        bm.aa_quality,
        bm.aa_hle,
        bm.aa_critpt,
        bm.aa_tb4,
        bm.aa_ifbench,
        bm.aa_gpqa,
        bm.aa_lcr,
        bm.aa_non_halluc,
    ]
    .into_iter()
    .any(|v| v.is_some_and(|x| x.is_finite()));
    let has_vals = [m.vals_overall, m.vals_coding, m.vals_terminal]
        .into_iter()
        .any(|v| v.is_some_and(|x| x.is_finite()));
    let has_live = live.is_some_and(|l| {
        [l.overall, l.coding, l.reasoning]
            .into_iter()
            .any(|v| v.is_some_and(|x| x.is_finite()))
    });
    let has_fc2 = bm.fc2_score.is_some_and(|x| x.is_finite());
    let has_fswe = bm.fswe_overall.is_some_and(|x| x.is_finite());
    let has_cursor = bm.cursor_score.is_some_and(|x| x.is_finite());

    let coverage_count = [
        has_arena, has_aa, has_vals, has_live, has_fc2, has_fswe, has_cursor,
    ]
    .into_iter()
    .filter(|&b| b)
    .count() as u8;

    let best_role = infer_best_role(m, coverage_count);

    Pillars {
        reasoning,
        coding,
        design,
        research,
        economics,
        coding_elo,
        speed,
        context_length: ctx,
        coverage_count,
        has_arena,
        has_aa,
        has_vals,
        has_live,
        has_fc2,
        has_fswe,
        has_cursor,
        best_role,
    }
}

/// `[7/7]` .. `[2/7]` / `[1/7]*` / `[0/7]` coverage badge.
pub fn conf_badge(coverage: u8) -> &'static str {
    match coverage {
        7.. => "[7/7]",
        6 => "[6/7]",
        5 => "[5/7]",
        4 => "[4/7]",
        3 => "[3/7]",
        2 => "[2/7]",
        1 => "[1/7]*",
        0 => "[0/7]",
    }
}

/// Compact token count (`1.0M`, `200k`, `—`).
pub fn format_ctx(tokens: Option<f64>) -> String {
    match tokens {
        Some(t) if t.is_finite() && t > 0.0 => {
            let t = t as i64;
            if t >= 1_000_000 {
                let v = t as f64 / 1_000_000.0;
                if v.fract() != 0.0 {
                    format!("{v:.1}M")
                } else {
                    format!("{}M", v as i64)
                }
            } else if t >= 1000 {
                format!("{}k", t / 1000)
            } else {
                format!("{t}")
            }
        }
        _ => "—".to_string(),
    }
}

fn fmt_price_one(p: f64) -> String {
    if p > 0.0 && p < 1.0 {
        format!("${p:.2}")
    } else {
        format!("${p:.1}")
    }
}

pub fn fmt_price_pair(pin: Option<f64>, pout: Option<f64>) -> String {
    match (pin, pout) {
        (Some(a), Some(b)) if a.is_finite() && b.is_finite() => {
            format!("{}/{}", fmt_price_one(a), fmt_price_one(b))
        }
        _ => "—".to_string(),
    }
}

pub fn fmt_task_cost(cost: Option<f64>) -> String {
    match cost {
        Some(0.0) => "$0.00".to_string(),
        Some(c) if c.is_finite() && c < 1.0 => format!("${c:.2}"),
        Some(c) if c.is_finite() && c < 100.0 => format!("${c:.2}"),
        Some(c) if c.is_finite() => format!("${c:.0}"),
        _ => "—".to_string(),
    }
}

pub fn load_snapshot(path: &std::path::Path) -> anyhow::Result<Vec<Model>> {
    let text = std::fs::read_to_string(path).map_err(|e| anyhow::anyhow!("{path:?}: {e}"))?;
    let v: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| anyhow::anyhow!("{path:?}: {e}"))?;
    let models = match &v {
        serde_json::Value::Array(a) => serde_json::from_value(serde_json::Value::Array(a.clone()))?,
        serde_json::Value::Object(map) => match map.get("models") {
            Some(val) if !val.is_null() => serde_json::from_value(val.clone())?,
            _ => Vec::new(),
        },
        _ => Vec::new(),
    };
    Ok(models)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn m(display: &str, q: Option<f64>, live: bool, elo: bool, aa: bool) -> Model {
        Model {
            display: display.into(),
            capability_q: q,
            livebench: live.then(|| Livebench {
                overall: Some(80.0),
                categories: [("Reasoning".into(), 90.0), ("Coding".into(), 80.0)]
                    .into_iter()
                    .collect(),
                ..Default::default()
            }),
            base_metrics: BaseMetrics {
                lm_elo: elo.then_some(1500.0),
                aa_quality: aa.then_some(45.0),
                speed_tps: Some(100.0),
                ..Default::default()
            },
            ..Default::default()
        }
    }

    #[test]
    fn tri_coverage_counts_three_of_seven() {
        assert_eq!(pillars(&m("a", Some(90.0), true, true, true)).coverage_count, 3);
        assert_eq!(conf_badge(3), "[3/7]");
    }

    #[test]
    fn seven_authority_coverage_counts_all_seven() {
        let mut model = m("a", Some(90.0), true, true, true);
        model.vals_overall = Some(55.0);
        model.base_metrics.fc2_score = Some(42.6);
        model.base_metrics.fswe_overall = Some(61.2);
        model.base_metrics.cursor_score = Some(60.4);
        assert_eq!(pillars(&model).coverage_count, 7);
        assert_eq!(conf_badge(7), "[7/7]");
        assert_eq!(conf_badge(1), "[1/7]*");
    }

    #[test]
    fn single_aa_coverage_is_one() {
        let p = pillars(&m("a", Some(90.0), false, false, true));
        assert_eq!(p.coverage_count, 1);
    }

    #[test]
    fn first_some_wins_over_zero_eating_or_chain() {
        let zero_q = Model {
            capability_q: Some(0.0),
            composite_score: Some(91.0),
            ..Default::default()
        };
        assert_eq!(zero_q.quality(), Some(0.0));
        let p = pillars(&Model {
            axes: Axes {
                reasoning: Some(0.0),
                ..Default::default()
            },
            aa_live_quality: Some(91.0),
            ..Default::default()
        });
        assert_eq!(p.reasoning, Some(0.0));
    }

    #[test]
    fn load_snapshot_handles_empty_object_and_subdime_price() {
        let dir = std::env::temp_dir().join(format!("checkerz_model_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("empty.json");
        std::fs::write(&p, "{}").unwrap();
        assert!(load_snapshot(&p).unwrap().is_empty());
        assert_eq!(fmt_price_pair(Some(0.05), Some(0.15)), "$0.05/$0.15");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn ctx_formats() {
        assert_eq!(format_ctx(Some(1_000_000.0)), "1M");
        assert_eq!(format_ctx(Some(1_500_000.0)), "1.5M");
        assert_eq!(format_ctx(Some(200_000.0)), "200k");
        assert_eq!(format_ctx(None), "—");
    }
}
