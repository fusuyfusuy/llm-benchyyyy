//! Scoring consumer: priced Pareto frontier & cohort role recommendations.
//!
//! All James-Stein shrunk z-score math lives exclusively in Python
//! (`checkers/benchmark_common.py:score_five_axes_and_roles`). Here we read the
//! precomputed `Model.roles` (`architecture`, `software_dev`, `design`, `research`)
//! and `Model.task_cost()` (`empirical_cost` -> `effective_cost`) so cohort
//! filters (e.g. `[AGY]`, `[CLAUDE]`) re-rank cleanly without duplicating math.

use crate::model::{is_num, Model};
use std::collections::HashSet;

const Q_TOL: f64 = 3.2;
const COST_TOL: f64 = 0.20;
const COST_EPS: f64 = 0.01;

fn row_quality(m: &Model) -> f64 {
    match m.quality() {
        Some(q) if is_num(Some(q)) => q,
        _ => 0.0,
    }
}

fn is_dominated(idx: usize, points: &[(f64, f64)]) -> bool {
    let (a_cost, a_q) = points[idx];
    for (j, &(b_cost, b_q)) in points.iter().enumerate() {
        if j != idx && b_cost <= a_cost && b_q >= a_q {
            let cost_diff = (a_cost - b_cost) / COST_EPS.max(a_cost);
            let q_diff = b_q - a_q;
            if cost_diff > COST_TOL || q_diff > Q_TOL {
                return true;
            }
        }
    }
    false
}

/// Pareto frontier over priced rows only (`empirical_cost` else `effective_cost`).
/// Unpriced high-Q rows never claim "cheapest at quality X"; free (`0.0`) stays eligible.
pub fn compute_priced_pareto_frontier(models: &[&Model]) -> HashSet<String> {
    let mut priced: Vec<&Model> = Vec::with_capacity(models.len());
    let mut points: Vec<(f64, f64)> = Vec::with_capacity(models.len());
    for &m in models {
        if let Some(c) = m.task_cost() {
            priced.push(m);
            points.push((c, row_quality(m)));
        }
    }
    let mut out = HashSet::new();
    for (i, m) in priced.iter().enumerate() {
        if !is_dominated(i, &points) {
            out.extend(m.stable_ids().iter().map(|s| s.to_string()));
        }
    }
    out
}

/// Shared membership predicate across all stable-id legs.
pub fn is_pareto(m: &Model, set: &HashSet<String>) -> bool {
    m.stable_ids().iter().any(|id| set.contains(*id))
}

fn pool_str(pool: &str) -> String {
    match pool.to_uppercase().as_str() {
        "CLAUDE" => "[CLD]".to_string(),
        "AGY" => "[AGY]".to_string(),
        "OCGO" => "[OCG]".to_string(),
        "FRONTIER" => "[FRT]".to_string(),
        "HETZNER" => "[HTZ]".to_string(),
        "NVIDIA" => "[NVD]".to_string(),
        "" => "[API]".to_string(),
        p => format!("[{}]", &p[..p.len().min(3)]),
    }
}

#[derive(Debug, Clone)]
pub struct RolePick {
    pub name: String,
    pub pool: String,
    pub score: f64,
    pub q: f64,
}

#[derive(Debug, Clone)]
pub struct Role {
    pub title: &'static str,
    pub icon: &'static str,
    pub desc: &'static str,
    pub winner: RolePick,
    pub runner_up: RolePick,
}

#[derive(Debug, Clone)]
pub struct RoleRecs {
    pub architecture: Role,
    pub software_dev: Role,
    pub design: Role,
    pub research: Role,
}

fn build_role<F>(
    eligible: &[&Model],
    score_fn: F,
    title: &'static str,
    icon: &'static str,
    desc: &'static str,
) -> Role
where
    F: Fn(&Model) -> f64,
{
    let mut ranked: Vec<(f64, f64, usize)> = eligible
        .iter()
        .enumerate()
        .map(|(i, m)| (score_fn(m), m.quality().unwrap_or(0.0), i))
        .collect();
    ranked.sort_by(|a, b| b.0.total_cmp(&a.0).then_with(|| b.1.total_cmp(&a.1)));

    let pick = |idx: usize| {
        let (score, q, mi) = ranked.get(idx).copied().unwrap_or((0.0, 0.0, 0));
        let m = eligible[mi];
        RolePick {
            name: if m.display.is_empty() {
                "Unknown".to_string()
            } else {
                m.display.clone()
            },
            pool: pool_str(&m.pool),
            score,
            q,
        }
    };

    Role {
        title,
        icon,
        desc,
        winner: pick(0),
        runner_up: pick(1),
    }
}

pub fn compute_role_recommendations(models: &[&Model]) -> Option<RoleRecs> {
    let eligible: Vec<&Model> = models
        .iter()
        .copied()
        .filter(|m| m.signal_mirror_of.is_none() && m.quality().is_some())
        .collect();
    if eligible.len() < 2 {
        return None;
    }

    let role_or_q = |v: Option<f64>, m: &Model| {
        v.filter(|x| x.is_finite())
            .or_else(|| m.quality())
            .unwrap_or(0.0)
    };

    Some(RoleRecs {
        architecture: build_role(
            &eligible,
            |m| role_or_q(m.roles.architecture, m),
            "System Architecture & Complex Reasoning",
            "🏗️",
            "Deep reasoning & spec lock for contracts, multi-service seams, and root-cause debugging.",
        ),
        software_dev: build_role(
            &eligible,
            |m| role_or_q(m.roles.software_dev, m),
            "Software Development & Agentic Coding",
            "💻",
            "Multi-file repo coding, CLI execution & empirical $/task efficiency (Cursor, FC2, FSWE).",
        ),
        design: build_role(
            &eligible,
            |m| role_or_q(m.roles.design, m),
            "UI/UX Design & Interactive Craft",
            "🎨",
            "React/CSS layout craft, WebDev Arena quality & strict instruction fidelity (IFBench).",
        ),
        research: build_role(
            &eligible,
            |m| role_or_q(m.roles.research, m),
            "Academic & Technical Research",
            "🔬",
            "High epistemic honesty (non-hallucination), long-context synthesis & scientific rigor.",
        ),
    })
}

pub fn cohort_summary(models: &[&Model], pareto: &HashSet<String>) -> (f64, f64, usize) {
    let qs: Vec<f64> = models.iter().filter_map(|m| m.quality()).collect();
    let avg = if qs.is_empty() {
        0.0
    } else {
        qs.iter().sum::<f64>() / qs.len() as f64
    };
    let mut speeds: Vec<f64> = models
        .iter()
        .filter_map(|m| m.base_metrics.speed_tps)
        .filter(|s| s.is_finite())
        .collect();
    speeds.sort_by(|a, b| a.total_cmp(b));
    let med = speeds.get(speeds.len() / 2).copied().unwrap_or(0.0);
    let par = models.iter().filter(|m| is_pareto(m, pareto)).count();
    (avg, med, par)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{BaseMetrics, Livebench, Roles};

    fn priced(display: &str, id: &str, q: f64, eff: Option<f64>) -> Model {
        Model {
            display: display.into(),
            model_id: Some(id.into()),
            capability_q: Some(q),
            effective_cost: eff,
            roles: Roles {
                architecture: Some(q + 1.0),
                software_dev: Some(q),
                design: Some(q - 0.5),
                research: Some(q + 0.5),
            },
            price_in: Some(1.0),
            price_out: Some(2.0),
            ..Default::default()
        }
    }

    #[test]
    fn priced_pareto_excludes_unpriced_high_q() {
        let rows = [
            priced("Priced Good", "a", 85.0, Some(1.0)),
            priced("Free Good", "b", 80.0, Some(0.0)),
            priced("Unpriced Great", "c", 99.0, None),
        ];
        let refs: Vec<&Model> = rows.iter().collect();
        let set = compute_priced_pareto_frontier(&refs);
        assert!(is_pareto(&rows[0], &set));
        assert!(is_pareto(&rows[1], &set));
        assert!(!is_pareto(&rows[2], &set));
    }

    #[test]
    fn membership_survives_display_rename() {
        let a = priced("Upstream Renamed Display", "stable-id-a", 90.0, Some(1.0));
        let b = priced("Other Model", "stable-id-b", 70.0, Some(5.0));
        let set = compute_priced_pareto_frontier(&[&a, &b]);
        let without_display: HashSet<String> = set
            .iter()
            .filter(|s| *s != "Upstream Renamed Display")
            .cloned()
            .collect();
        assert!(!without_display.contains("Upstream Renamed Display"));
        assert!(is_pareto(&a, &without_display));
    }

    #[test]
    fn roles_preserve_distinct_thinking_levels_and_exclude_mirrors() {
        assert!(compute_role_recommendations(&[]).is_none());
        let solo = priced("Solo", "s", 90.0, Some(1.0));
        assert!(compute_role_recommendations(&[&solo]).is_none());
        let a = priced("Gemini 4 Carbon (High)", "a", 88.9, Some(7.2));
        let b = priced("Gemini 4 Carbon (Medium)", "b", 88.2, Some(5.6));
        let mut mirror = priced("Mirror Model", "m", 99.0, Some(0.1));
        mirror.signal_mirror_of = Some("Gemini 4 Carbon (High)".into());
        let recs = compute_role_recommendations(&[&a, &b, &mirror]).unwrap();
        assert_eq!(recs.architecture.winner.name, "Gemini 4 Carbon (High)");
        assert_eq!(recs.architecture.runner_up.name, "Gemini 4 Carbon (Medium)");
        for r in [
            &recs.architecture,
            &recs.software_dev,
            &recs.design,
            &recs.research,
        ] {
            assert_ne!(r.winner.name, "Mirror Model");
        }
    }

    #[test]
    fn is_num_rejects_nan_inf() {
        assert!(!is_num(Some(f64::NAN)));
        assert!(!is_num(Some(f64::INFINITY)));
        assert!(!is_num(None));
        assert!(is_num(Some(0.0)));
    }

    #[test]
    fn livebench_helpers_used() {
        let lb = Livebench {
            overall: Some(80.0),
            ..Default::default()
        };
        let m = Model {
            base_metrics: BaseMetrics {
                lm_elo: Some(1500.0),
                ..Default::default()
            },
            livebench: Some(lb),
            ..Default::default()
        };
        assert!(crate::model::pillars(&m).has_arena);
    }
}
