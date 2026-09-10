//! Data contract: `docs/data/benchmarks.json` rows + capability pillars.
//!
//! Ports `extract_capability_pillars` / `format_context_window`
//! (`checkers/benchmark_common.py`). One deliberate deviation: the Python
//! `or`-chains eat real `0.0` scores (audit P3); here the first `Some` wins.

use serde::Deserialize;
use std::collections::HashMap;

/// Real number for scoring: finite, never NaN/Inf (mirrors `_is_num`).
pub fn is_num(v: Option<f64>) -> bool {
    matches!(v, Some(x) if x.is_finite())
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
    pub aa_quality: Option<f64>,
    #[serde(default)]
    pub aa_coding: Option<f64>,
    #[serde(default)]
    pub aa_reasoning: Option<f64>,
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
    // Forward-compatible stable-id legs (aggregator 5-key checks).
    #[serde(default)]
    pub model_id: Option<String>,
    #[serde(default)]
    pub or_slug: Option<String>,
    #[serde(default)]
    pub aa_slug: Option<String>,
    #[serde(default)]
    pub lm_slug: Option<String>,
    #[serde(default)]
    pub base_metrics: BaseMetrics,
    #[serde(default)]
    pub livebench: Option<Livebench>,
    #[serde(default)]
    pub aa_live_quality: Option<f64>,
    #[serde(default)]
    pub aa_live_coding: Option<f64>,
    #[serde(default)]
    pub context_length: Option<f64>,
    #[serde(default)]
    pub capability_q: Option<f64>,
    #[serde(default)]
    pub token_multiplier: Option<f64>,
    #[serde(default)]
    pub composite_score: Option<f64>,
    #[serde(default)]
    pub p_success: Option<f64>,
    #[serde(default)]
    pub effective_cost: Option<f64>,
    #[serde(default)]
    pub blended_price: Option<f64>,
    #[serde(default)]
    pub avi_score: Option<f64>,
    #[serde(default)]
    pub bfi_score: Option<f64>,
    #[serde(default)]
    pub fgi_score: Option<f64>,
    #[serde(default)]
    pub is_new: bool,
    #[serde(default)]
    pub unmatched: bool,
}

impl Model {
    /// Every stable identity leg this row can match on (aggregator pattern:
    /// display + slugs + every alias leg).
    pub fn stable_ids(&self) -> Vec<&str> {
        let mut ids = Vec::with_capacity(8);
        if !self.display.is_empty() {
            ids.push(self.display.as_str());
        }
        for opt in [&self.model_id, &self.or_slug, &self.aa_slug, &self.lm_slug] {
            if let Some(s) = opt {
                if !s.is_empty() {
                    ids.push(s.as_str());
                }
            }
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
        first_some(self.capability_q, self.composite_score)
    }
}

fn first_some(a: Option<f64>, b: Option<f64>) -> Option<f64> {
    if is_num(a) {
        a
    } else if is_num(b) {
        b
    } else {
        None
    }
}

#[derive(Debug, Clone)]
pub struct Pillars {
    pub reasoning: Option<f64>,
    pub coding: Option<f64>,
    pub coding_elo: Option<i64>,
    pub speed: Option<f64>,
    pub context_length: Option<i64>,
    pub coverage_count: u8,
    pub has_live: bool,
    pub has_arena: bool,
    pub has_aa: bool,
    pub best_role: String,
}

/// Normalized capability dimensions across LiveBench, LMSYS Arena, AA.
pub fn pillars(m: &Model) -> Pillars {
    let lb = m.livebench.as_ref();
    let cats = lb.map(|l| &l.categories);
    let cat = |k: &str| cats.and_then(|c| c.get(k)).copied().filter(|v| v.is_finite());

    let reasoning = cat("Reasoning")
        .or_else(|| lb.and_then(|l| l.reasoning).filter(|v| v.is_finite()))
        .or_else(|| m.base_metrics.aa_reasoning.filter(|v| v.is_finite()));
    let coding = cat("Coding")
        .or_else(|| lb.and_then(|l| l.coding).filter(|v| v.is_finite()))
        .or_else(|| m.base_metrics.aa_coding.filter(|v| v.is_finite()));
    let coding_elo = m
        .base_metrics
        .lm_coding
        .filter(|v| v.is_finite())
        .map(|v| v.round() as i64);
    let speed = m.base_metrics.speed_tps.filter(|v| v.is_finite());
    let ctx = m
        .context_length
        .or(m.base_metrics.context_length)
        .filter(|v| v.is_finite() && *v > 0.0)
        .map(|v| v as i64);

    let has_live = lb.and_then(|l| l.overall).is_some_and(|v| v.is_finite());
    let has_arena = m.base_metrics.lm_elo.is_some_and(|v| v.is_finite());
    let has_aa = m.aa_live_quality.is_some_and(|v| v.is_finite())
        || m.base_metrics.aa_quality.is_some_and(|v| v.is_finite());
    let coverage_count = [has_live, has_arena, has_aa]
        .iter()
        .filter(|&&b| b)
        .count() as u8;

    let q = m.quality();
    let fgi = m.fgi_score.filter(|v| v.is_finite());
    let avi = m.avi_score.filter(|v| v.is_finite());
    let best_role = if q.is_none() || coverage_count == 0 {
        "—".to_string()
    } else if fgi.is_some_and(|v| v >= 60.0) || reasoning.is_some_and(|v| v >= 88.0) {
        "🏗️ Architect".to_string()
    } else if coding.is_some_and(|v| v >= 78.0) || coding_elo.is_some_and(|v| v >= 1470) {
        "💻 Pair Coder".to_string()
    } else if speed.is_some_and(|v| v >= 180.0) {
        "⚡ Fast Fill".to_string()
    } else if avi.is_some_and(|v| v >= 250.0) {
        "🔄 Workhorse".to_string()
    } else if q.is_some_and(|v| v >= 75.0) {
        "💻 Generalist".to_string()
    } else {
        "⚡ Lightweight".to_string()
    };

    Pillars {
        reasoning,
        coding,
        coding_elo,
        speed,
        context_length: ctx,
        coverage_count,
        has_live,
        has_arena,
        has_aa,
        best_role,
    }
}

/// `[3/3]` / `[2/3]` / `[1/3]*` / `[0/3]` coverage badge.
pub fn conf_badge(coverage: u8) -> &'static str {
    match coverage {
        3 => "[3/3]",
        2 => "[2/3]",
        1 => "[1/3]*",
        _ => "[0/3]",
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

pub fn fmt_price_pair(pin: Option<f64>, pout: Option<f64>) -> String {
    match (pin, pout) {
        (Some(a), Some(b)) if a.is_finite() && b.is_finite() => format!("${a:.1}/${b:.1}"),
        _ => "—".to_string(),
    }
}

#[derive(Debug, Deserialize)]
pub struct Snapshot {
    #[serde(default)]
    pub models: Vec<Model>,
}

pub fn load_snapshot(path: &std::path::Path) -> anyhow::Result<Snapshot> {
    let text = std::fs::read_to_string(path).map_err(|e| anyhow::anyhow!("{path:?}: {e}"))?;
    let v: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| anyhow::anyhow!("{path:?}: {e}"))?;
    let models = match &v {
        serde_json::Value::Array(a) => serde_json::from_value(serde_json::Value::Array(a.clone()))?,
        serde_json::Value::Object(_) => serde_json::from_value(v.get("models").cloned().unwrap_or_default())?,
        _ => Vec::new(),
    };
    Ok(Snapshot { models })
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
    fn tri_coverage_counts_three() {
        assert_eq!(pillars(&m("a", Some(90.0), true, true, true)).coverage_count, 3);
    }

    #[test]
    fn empty_livebench_scores_zero_not_one() {
        // Python `lb or livebench is not None` marks `{}` live; we require overall.
        let p = pillars(&m("a", Some(90.0), false, true, true));
        assert!(!p.has_live);
        assert_eq!(p.coverage_count, 2);
    }

    #[test]
    fn first_some_wins_over_zero_eating_or_chain() {
        let lb = Livebench {
            categories: [("Reasoning".into(), 0.0)].into_iter().collect(),
            reasoning: Some(91.0),
            ..Default::default()
        };
        let p = pillars(&Model {
            livebench: Some(lb),
            ..Default::default()
        });
        assert_eq!(p.reasoning, Some(0.0));
    }

    #[test]
    fn ctx_formats() {
        assert_eq!(format_ctx(Some(1_000_000.0)), "1M");
        assert_eq!(format_ctx(Some(1_500_000.0)), "1.5M");
        assert_eq!(format_ctx(Some(200_000.0)), "200k");
        assert_eq!(format_ctx(None), "—");
    }
}
