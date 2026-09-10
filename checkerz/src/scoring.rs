//! Scoring: priced Pareto frontier, None-passthrough z-scores, role recommendations.
//!
//! Ports `compute_pareto_frontier`, `compute_priced_pareto_frontier`,
//! `z_scores_none`, `compute_role_recommendations`
//! (`checkers/benchmark_common.py`). One deliberate deviation: Python's
//! `m.get("effective_cost") or …` fallback chain eats a real `0.0` free tier
//! (falsy) so free rows score cost-neutral; here the first `Some` wins and a
//! real `0.0` becomes the `0.0001` log-safe marker the comment intends.

use crate::model::{is_num, Model};
use std::collections::HashSet;

pub const Q_TOL: f64 = 3.2;
pub const COST_TOL: f64 = 0.20;
pub const COST_EPS: f64 = 0.01;
pub const UNKNOWN_COST: f64 = 999.0;

/// Effective cost, else prompt+completion sum, else unknown sentinel.
/// A real `0.0` (free tier) is a genuine cost and dominates the frontier.
pub fn row_cost(m: &Model) -> f64 {
    if let Some(c) = m.effective_cost {
        if c.is_finite() {
            return c;
        }
    }
    let mut sum = 0.0;
    let mut n = 0;
    for p in [m.price_in, m.price_out] {
        if let Some(v) = p {
            if v.is_finite() {
                sum += v;
                n += 1;
            }
        }
    }
    if n > 0 { sum } else { UNKNOWN_COST }
}

pub fn row_quality(m: &Model) -> f64 {
    match m.capability_q {
        Some(q) if is_num(Some(q)) => q,
        _ => 0.0,
    }
}

pub fn pareto_dominated(
    a_cost: f64,
    a_q: f64,
    candidates: &[(f64, f64)],
    q_tol: f64,
    cost_tol: f64,
) -> bool {
    for &(b_cost, b_q) in candidates {
        if b_cost <= a_cost && b_q >= a_q {
            let cost_diff = (a_cost - b_cost) / COST_EPS.max(a_cost);
            let q_diff = b_q - a_q;
            if cost_diff > cost_tol || q_diff > q_tol {
                return true;
            }
        }
    }
    false
}

/// Pareto-optimal set over all rows (stable-id universe: display, slugs, aliases).
pub fn compute_pareto_frontier(models: &[Model]) -> HashSet<String> {
    compute_pareto_frontier_with(models, Q_TOL, COST_TOL)
}

fn compute_pareto_frontier_with(models: &[Model], q_tol: f64, cost_tol: f64) -> HashSet<String> {
    let costs: Vec<f64> = models.iter().map(row_cost).collect();
    let quals: Vec<f64> = models.iter().map(row_quality).collect();
    let mut out = HashSet::new();
    for (i, m) in models.iter().enumerate() {
        let candidates: Vec<(f64, f64)> = costs
            .iter()
            .zip(quals.iter())
            .enumerate()
            .filter(|(j, _)| *j != i)
            .map(|(_, (&c, &q))| (c, q))
            .collect();
        if !pareto_dominated(costs[i], quals[i], &candidates, q_tol, cost_tol) {
            out.extend(m.stable_ids().iter().map(|s| s.to_string()));
        }
    }
    out
}

/// Pareto frontier over priced rows only. Unpriced high-Q rows must never
/// claim "cheapest at quality X"; free (`0.0`) stays eligible.
pub fn compute_priced_pareto_frontier(models: &[Model]) -> HashSet<String> {
    let priced: Vec<Model> = models
        .iter()
        .filter(|m| m.effective_cost.is_some())
        .cloned()
        .collect();
    if priced.is_empty() {
        return HashSet::new();
    }
    compute_pareto_frontier(&priced)
}

/// Shared membership predicate — every render path must use this, never a
/// bare `display in set` check (audit §1.9: renamed displays lose their ⭐).
pub fn is_pareto(m: &Model, set: &HashSet<String>) -> bool {
    m.stable_ids().iter().any(|id| set.contains(*id))
}

/// Z-scores with `None` passthrough (population std). Missing stays missing —
/// callers skip `None` legs and renormalize instead of banking the mean.
pub fn z_scores_none(values: &[Option<f64>]) -> Vec<Option<f64>> {
    let valid: Vec<f64> = values.iter().filter_map(|v| *v).filter(|v| v.is_finite()).collect();
    if valid.len() < 2 {
        return values
            .iter()
            .map(|v| match v {
                Some(x) if x.is_finite() => Some(0.0),
                _ => None,
            })
            .collect();
    }
    let mean = valid.iter().sum::<f64>() / valid.len() as f64;
    let var = valid.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / valid.len() as f64;
    let mut std = var.sqrt();
    if std == 0.0 {
        std = 1.0;
    }
    values
        .iter()
        .map(|v| match v {
            Some(x) if x.is_finite() => Some((x - mean) / std),
            _ => None,
        })
        .collect()
}

/// Round-half-even to 1 decimal (matches Python `round(x, 1)` banker's rounding).
fn round1(x: f64) -> f64 {
    let t = x * 10.0;
    let f = t.floor();
    let d = t - f;
    let r = if d < 0.5 {
        f
    } else if d > 0.5 {
        f + 1.0
    } else if (f as i64) % 2 == 0 {
        f
    } else {
        f + 1.0
    };
    r / 10.0
}

fn clamp_score(raw: f64) -> f64 {
    round1((80.0 + raw * 7.0).clamp(50.0, 99.9))
}

fn strip_parens(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'(' {
            while out.ends_with(' ') {
                out.pop();
            }
            while i < bytes.len() && bytes[i] != b')' {
                i += 1;
            }
            i += 1; // consume ')'
        } else {
            out.push(s[i..].chars().next().unwrap());
            i += s[i..].chars().next().unwrap().len_utf8();
        }
    }
    out.trim().to_string()
}

fn pool_str(pool: &str) -> String {
    match pool.to_uppercase().as_str() {
        "CLAUDE" => "[CLD]".to_string(),
        "AGY" => "[AGY]".to_string(),
        "OCGO" => "[OCG]".to_string(),
        "FRONTIER" => "[FRT]".to_string(),
        p if p.is_empty() => "[API]".to_string(),
        p => format!("[{}]", &p[..p.len().min(3)]),
    }
}

struct Feat {
    name: String,
    pool: String,
    q: f64,
    fgi: Option<f64>,
    avi: Option<f64>,
    bfi: Option<f64>,
    psucc: Option<f64>,
    eff_cost: Option<f64>,
    coding: Option<f64>,
    reasoning: Option<f64>,
    speed: Option<f64>,
}

fn features(m: &Model) -> Option<Feat> {
    let raw = if m.display.is_empty() {
        "Unknown".to_string()
    } else {
        m.display.clone()
    };
    let q = m.quality()?;
    if !q.is_finite() {
        return None;
    }
    let finite = |v: Option<f64>| v.filter(|x| x.is_finite());
    let mut eff = finite(m.effective_cost);
    if eff == Some(0.0) {
        eff = Some(0.0001);
    }
    let lb = m.livebench.as_ref();
    Some(Feat {
        name: strip_parens(&raw),
        pool: pool_str(&m.pool),
        q,
        fgi: finite(m.fgi_score),
        avi: finite(m.avi_score),
        bfi: finite(m.bfi_score),
        psucc: finite(m.p_success),
        eff_cost: eff,
        coding: finite(m.base_metrics.lm_coding).or_else(|| lb.and_then(|l| l.coding)),
        reasoning: finite(m.base_metrics.aa_reasoning)
            .or_else(|| lb.and_then(|l| l.reasoning)),
        speed: finite(m.base_metrics.speed_tps),
    })
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
    pub pair_programming: Role,
    pub daily_driver: Role,
    pub boilerplate: Role,
}

fn wsum(pairs: &[(f64, Option<f64>)]) -> f64 {
    let (mut num, mut den) = (0.0, 0.0);
    for (w, z) in pairs {
        if let Some(z) = z {
            num += w * z;
            den += w;
        }
    }
    if den > 0.0 { num / den } else { 0.0 }
}

fn pack(
    scored: &[(f64, usize)],
    feats: &[Feat],
    title: &'static str,
    icon: &'static str,
    desc: &'static str,
) -> Role {
    let pick = |idx: usize| {
        let (score, fi) = scored.get(idx).copied().unwrap_or((0.0, 0));
        let f = &feats[fi];
        RolePick {
            name: f.name.clone(),
            pool: f.pool.clone(),
            score,
            q: f.q,
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

pub fn compute_role_recommendations(models: &[Model]) -> Option<RoleRecs> {
    let feats: Vec<Feat> = models.iter().filter_map(features).collect();
    if feats.len() < 2 {
        return None;
    }
    let z_q = z_scores_none(&feats.iter().map(|f| Some(f.q)).collect::<Vec<_>>());
    let z_fgi = z_scores_none(&feats.iter().map(|f| f.fgi).collect::<Vec<_>>());
    let z_avi = z_scores_none(&feats.iter().map(|f| f.avi).collect::<Vec<_>>());
    let z_bfi = z_scores_none(&feats.iter().map(|f| f.bfi).collect::<Vec<_>>());
    let z_psucc = z_scores_none(&feats.iter().map(|f| f.psucc).collect::<Vec<_>>());
    let z_speed = z_scores_none(&feats.iter().map(|f| f.speed).collect::<Vec<_>>());
    let inv_log: Vec<Option<f64>> = feats
        .iter()
        .map(|f| {
            f.eff_cost
                .map(|c| -c.max(0.00001).log10())
                .filter(|x| x.is_finite())
        })
        .collect();
    let z_cost = z_scores_none(&inv_log);
    let z_coding = z_scores_none(
        &feats
            .iter()
            .map(|f| Some(f.coding.unwrap_or(f.q)))
            .collect::<Vec<_>>(),
    );
    let z_reasoning = z_scores_none(
        &feats
            .iter()
            .map(|f| Some(f.reasoning.unwrap_or(f.q)))
            .collect::<Vec<_>>(),
    );

    let mut arch = Vec::with_capacity(feats.len());
    let mut pair = Vec::with_capacity(feats.len());
    let mut driver = Vec::with_capacity(feats.len());
    let mut boiler = Vec::with_capacity(feats.len());
    for (i, f) in feats.iter().enumerate() {
        arch.push((clamp_score(wsum(&[(0.40, z_fgi[i]), (0.30, z_q[i]), (0.30, z_reasoning[i])])), i));
        pair.push((
            clamp_score(wsum(&[
                (0.35, z_coding[i]),
                (0.30, z_q[i]),
                (0.20, z_avi[i]),
                (0.15, z_psucc[i]),
            ])),
            i,
        ));
        driver.push((
            clamp_score(wsum(&[(0.50, z_avi[i]), (0.30, z_q[i]), (0.20, z_cost[i])])),
            i,
        ));
        if f.q >= 64.0 {
            boiler.push((
                clamp_score(wsum(&[(0.45, z_bfi[i]), (0.30, z_speed[i]), (0.25, z_cost[i])])),
                i,
            ));
        } else {
            boiler.push((45.0, i));
        }
    }
    for v in [&mut arch, &mut pair, &mut driver, &mut boiler] {
        v.sort_by(|a, b| b.0.total_cmp(&a.0));
    }
    Some(RoleRecs {
        architecture: pack(
            &arch,
            &feats,
            "System Architecture & Complex Design",
            "🏗",
            "Deep reasoning & high FGI gates. Use for contracts, spec lock, and hard debugging.",
        ),
        pair_programming: pack(
            &pair,
            &feats,
            "Pair Programming & Code Editing",
            "💻",
            "Surgical diffs, coding Elo & multi-turn alignment without drift.",
        ),
        daily_driver: pack(
            &driver,
            &feats,
            "Daily Driver (High ROI Workhorse)",
            "🔄",
            "Top AVI & cost-efficiency. Autonomous loops without token explosion.",
        ),
        boilerplate: pack(
            &boiler,
            &feats,
            "Fast Boilerplate & Mechanical Fill",
            "⚡",
            "High throughput (TPS/BFI) for mechanical generation and test scaffolding.",
        ),
    })
}

pub fn cohort_summary(models: &[Model], pareto: &HashSet<String>) -> (f64, f64, usize) {
    let qs: Vec<f64> = models
        .iter()
        .filter_map(|m| m.capability_q)
        .filter(|q| q.is_finite())
        .collect();
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
    use crate::model::{BaseMetrics, Livebench};

    fn priced(display: &str, id: &str, q: f64, eff: Option<f64>) -> Model {
        Model {
            display: display.into(),
            model_id: Some(id.into()),
            capability_q: Some(q),
            effective_cost: eff,
            price_in: Some(1.0),
            price_out: Some(2.0),
            ..Default::default()
        }
    }

    #[test]
    fn priced_pareto_excludes_unpriced_high_q() {
        let rows = vec![
            priced("Priced Good", "a", 85.0, Some(1.0)),
            priced("Free Good", "b", 80.0, Some(0.0)),
            priced("Unpriced Great", "c", 99.0, None),
        ];
        let set = compute_priced_pareto_frontier(&rows);
        assert!(is_pareto(&rows[0], &set));
        assert!(is_pareto(&rows[1], &set)); // 0.0 is a real cost
        assert!(!is_pareto(&rows[2], &set));
    }

    #[test]
    fn round1_is_bankers() {
        assert_eq!(round1(2.25), 2.2); // 22.5 ties to even
        assert_eq!(round1(2.75), 2.8); // 27.5 ties away from even
        assert_eq!(round1(80.06), 80.1); // non-tie rounds normally
        assert_eq!(round1(80.0), 80.0);
    }

    #[test]
    fn membership_survives_display_rename() {
        let a = priced("Upstream Renamed Display", "stable-id-a", 90.0, Some(1.0));
        let b = priced("Other Model", "stable-id-b", 70.0, Some(5.0));
        let set = compute_priced_pareto_frontier(&[a.clone(), b]);
        // Display leg removed from the set: stable id still matches.
        let without_display: HashSet<String> =
            set.iter().filter(|s| *s != "Upstream Renamed Display").cloned().collect();
        assert!(!without_display.contains("Upstream Renamed Display"));
        assert!(is_pareto(&a, &without_display));
    }

    #[test]
    fn z_none_passthrough_and_constant_cohort() {
        assert_eq!(z_scores_none(&[]), vec![]);
        assert_eq!(z_scores_none(&[None, None]), vec![None, None]);
        assert_eq!(z_scores_none(&[Some(5.0)]), vec![Some(0.0)]);
        assert_eq!(
            z_scores_none(&[Some(5.0), Some(5.0), None]),
            vec![Some(0.0), Some(0.0), None]
        );
        let zs = z_scores_none(&[Some(1.0), Some(2.0), Some(3.0)]);
        assert!((zs[0].unwrap() + 1.2247).abs() < 1e-3);
        assert!(zs[1].unwrap().abs() < 1e-9);
    }


    #[test]
    fn roles_need_two_scored_models() {
        assert!(compute_role_recommendations(&[]).is_none());
        assert!(compute_role_recommendations(&[priced("Solo", "s", 90.0, Some(1.0))]).is_none());
        let rows = vec![
            priced("Alpha Model", "a", 95.0, Some(9.0)),
            priced("Beta Model", "b", 85.0, Some(1.0)),
            priced("Gamma Model", "c", 75.0, Some(0.5)),
        ];
        let recs = compute_role_recommendations(&rows).unwrap();
        for r in [&recs.architecture, &recs.pair_programming, &recs.daily_driver, &recs.boilerplate] {
            assert!(!r.winner.name.is_empty() && r.winner.name != "—");
        }
    }

    #[test]
    fn strip_parens_basename() {
        assert_eq!(strip_parens("Claude Opus 5 (Thinking)"), "Claude Opus 5");
        let rows = vec![
            priced("Alpha (Thinking)", "a", 95.0, Some(9.0)),
            priced("Beta (Fast)", "b", 85.0, Some(1.0)),
        ];
        let recs = compute_role_recommendations(&rows).unwrap();
        assert!(!recs.architecture.winner.name.contains('('));
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
            base_metrics: BaseMetrics { lm_elo: Some(1500.0), ..Default::default() },
            livebench: Some(lb),
            ..Default::default()
        };
        assert!(crate::model::pillars(&m).has_arena);
    }
}
