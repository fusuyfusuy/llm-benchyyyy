//! App state: filters, sorting, pagination, modal flags.
//!
//! Ports `TUIState` (`checkers/benchmark_tui.py`) with three deliberate fixes:
//! - Pareto membership via [`crate::scoring::is_pareto`] (all stable-id legs),
//!   never display-only (audit §1.9).
//! - Price sort keys on `effective_cost` (else `price_in`), unknown → `999.0`
//!   like the bcheck CLI — not `price_in`-only `9999.0` (seams S6).
//! - Search also matches alias legs; Esc during search restores the
//!   pre-search query (audit §4.2a); main-loop Esc also resets sort and says so.

use crate::model::{pillars, Model};
use crate::scoring::{compute_priced_pareto_frontier, compute_role_recommendations, is_pareto, RoleRecs};
use std::collections::HashSet;

pub const POOLS: [&str; 6] = ["all", "agy", "claude", "ocgo", "frontier", "api"];

pub fn pool_label(pool: &str) -> String {
    match pool {
        "all" => "ALL".to_string(),
        "agy" => "AGY (Gemini)".to_string(),
        "claude" => "CLAUDE".to_string(),
        "ocgo" => "OPENCODE".to_string(),
        "frontier" => "FRONTIER".to_string(),
        "api" => "API".to_string(),
        other => other.to_uppercase(),
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortKey {
    Composite,
    Coding,
    Reasoning,
    Speed,
    Ctx,
    Price,
    Avi,
}

impl SortKey {
    pub fn label(self) -> &'static str {
        match self {
            SortKey::Composite => "COMPOSITE",
            SortKey::Coding => "CODING",
            SortKey::Reasoning => "REASONING",
            SortKey::Speed => "SPEED",
            SortKey::Ctx => "CTX",
            SortKey::Price => "PRICE",
            SortKey::Avi => "AVI",
        }
    }

    pub fn cycle_next(self) -> SortKey {
        match self {
            SortKey::Composite => SortKey::Coding,
            SortKey::Coding => SortKey::Reasoning,
            SortKey::Reasoning => SortKey::Speed,
            SortKey::Speed => SortKey::Ctx,
            SortKey::Ctx => SortKey::Price,
            SortKey::Price => SortKey::Avi,
            SortKey::Avi => SortKey::Composite,
        }
    }
}

/// Sort value for one row. Price uses the effective-cost basis (else blended,
/// else prompt rate), unknown sinks to 999.0; every other key sinks missing to 0.0.
pub fn sort_value(m: &Model, key: SortKey) -> f64 {
    let p = pillars(m);
    let finite_or = |v: Option<f64>, dflt: f64| v.filter(|x| x.is_finite()).unwrap_or(dflt);
    match key {
        SortKey::Composite => finite_or(m.quality(), 0.0),
        SortKey::Coding => finite_or(p.coding, 0.0),
        SortKey::Reasoning => finite_or(p.reasoning, 0.0),
        SortKey::Speed => finite_or(p.speed, 0.0),
        SortKey::Ctx => p.context_length.map(|v| v as f64).unwrap_or(0.0),
        SortKey::Price => m
            .effective_cost
            .filter(|v| v.is_finite())
            .or_else(|| m.blended_price.filter(|v| v.is_finite()))
            .or_else(|| m.price_in.filter(|v| v.is_finite()))
            .unwrap_or(999.0),
        SortKey::Avi => finite_or(m.avi_score, 0.0),
    }
}

fn matches_search(m: &Model, q: &str) -> bool {
    if q.is_empty() {
        return true;
    }
    let hit = |s: &str| s.to_lowercase().contains(q);
    if hit(&m.display) || hit(&m.provider) {
        return true;
    }
    if m.model_id.as_deref().is_some_and(|s| hit(s)) {
        return true;
    }
    m.aa_aliases.iter().chain(&m.lm_aliases).chain(&m.live_aliases).any(|a| hit(a))
}

pub struct App {
    pub all: Vec<Model>,
    pub unmatched_count: usize,
    pub filtered: Vec<usize>,
    pub pareto: HashSet<String>,
    pub roles: Option<RoleRecs>,
    pub cursor: usize,
    pub page: usize,
    pub page_size: usize,
    pub sort_key: SortKey,
    /// `true` = descending (ascending for Price — same inversion as Python).
    pub sort_desc: bool,
    pub pool: String,
    pub tri_only: bool,
    pub top_limit: usize, // 0 = unlimited
    pub pareto_only: bool,
    pub query: String,
    pub searching: bool,
    pub search_backup: String,
    pub inspecting: bool,
    pub showing_roles: bool,
    pub showing_diff: bool,
    pub baseline: usize,
    pub showing_help: bool,
    pub status: String,
    pub stale_note: String,
}

impl App {
    pub fn new(
        all: Vec<Model>,
        unmatched_count: usize,
        tri_only: bool,
        top_limit: usize,
        stale_note: String,
    ) -> Self {
        let mut app = Self {
            all,
            unmatched_count,
            filtered: Vec::new(),
            pareto: HashSet::new(),
            roles: None,
            cursor: 0,
            page: 0,
            page_size: 15,
            sort_key: SortKey::Composite,
            sort_desc: true,
            pool: "all".to_string(),
            tri_only,
            top_limit,
            pareto_only: false,
            query: String::new(),
            searching: false,
            search_backup: String::new(),
            inspecting: false,
            showing_roles: false,
            showing_diff: false,
            baseline: 0,
            showing_help: false,
            status: String::new(),
            stale_note,
        };
        app.apply_filters();
        app
    }

    pub fn total_pages(&self) -> usize {
        if self.filtered.is_empty() {
            1
        } else {
            self.filtered.len().div_ceil(self.page_size)
        }
    }

    pub fn any_modal(&self) -> bool {
        self.inspecting || self.showing_roles || self.showing_diff || self.showing_help
    }

    pub fn close_modals(&mut self) {
        self.inspecting = false;
        self.showing_roles = false;
        self.showing_diff = false;
        self.showing_help = false;
    }

    pub fn apply_filters(&mut self) {
        let mut rows: Vec<usize> = (0..self.all.len()).collect();

        if self.tri_only {
            rows.retain(|&i| pillars(&self.all[i]).coverage_count == 3);
        }
        if self.pool != "all" {
            rows.retain(|&i| self.all[i].pool.to_lowercase() == self.pool);
        }
        let q = self.query.trim().to_lowercase();
        if !q.is_empty() {
            rows.retain(|&i| matches_search(&self.all[i], &q));
        }

        let key = self.sort_key;
        let desc = self.sort_desc;
        rows.sort_by(|&a, &b| {
            let (va, vb) = (sort_value(&self.all[a], key), sort_value(&self.all[b], key));
            let ord = va.total_cmp(&vb);
            if key == SortKey::Price {
                if desc { ord } else { ord.reverse() }
            } else if desc {
                ord.reverse()
            } else {
                ord
            }
        });

        if self.pareto_only {
            let tmp: Vec<Model> = rows.iter().map(|&i| self.all[i].clone()).collect();
            let set = compute_priced_pareto_frontier(&tmp);
            rows.retain(|&i| is_pareto(&self.all[i], &set));
        }

        if self.top_limit > 0 && rows.len() > self.top_limit {
            rows.truncate(self.top_limit);
        }
        self.filtered = rows;

        let cohort: Vec<Model> = self.filtered.iter().map(|&i| self.all[i].clone()).collect();
        self.pareto = compute_priced_pareto_frontier(&cohort);
        self.roles = if cohort.len() >= 2 {
            compute_role_recommendations(&cohort)
        } else {
            None
        };

        if self.baseline >= self.filtered.len() {
            self.baseline = 0;
        }
        if self.filtered.is_empty() {
            self.cursor = 0;
            self.page = 0;
        } else {
            self.cursor = self.cursor.min(self.filtered.len() - 1);
            self.page = self.cursor / self.page_size;
        }
    }

    pub fn move_cursor(&mut self, delta: isize) {
        if self.filtered.is_empty() {
            return;
        }
        let next = (self.cursor as isize + delta)
            .clamp(0, self.filtered.len() as isize - 1) as usize;
        self.cursor = next;
        self.page = self.cursor / self.page_size;
    }

    pub fn next_page(&mut self) {
        if self.page + 1 < self.total_pages() {
            self.page += 1;
            self.cursor = (self.page * self.page_size).min(self.filtered.len() - 1);
            self.status = format!("Page {} of {}", self.page + 1, self.total_pages());
        }
    }

    pub fn prev_page(&mut self) {
        if self.page > 0 {
            self.page -= 1;
            self.cursor = self.page * self.page_size;
            self.status = format!("Page {} of {}", self.page + 1, self.total_pages());
        }
    }

    pub fn cycle_pool(&mut self) {
        let idx = POOLS.iter().position(|&p| p == self.pool).unwrap_or(0);
        self.pool = POOLS[(idx + 1) % POOLS.len()].to_string();
        self.page = 0;
        self.cursor = 0;
        self.apply_filters();
        self.status = format!("Filtered pool: {}", pool_label(&self.pool));
    }

    pub fn toggle_tri(&mut self) {
        self.tri_only = !self.tri_only;
        self.page = 0;
        self.cursor = 0;
        self.apply_filters();
        self.status = if self.tri_only {
            "Coverage Filter: Tri-Verified (3/3 Only)".to_string()
        } else {
            "Coverage Filter: All Evaluated Models (3/3 · 2/3 · 1/3*)".to_string()
        };
    }

    pub fn toggle_pareto(&mut self) {
        self.pareto_only = !self.pareto_only;
        self.page = 0;
        self.cursor = 0;
        self.apply_filters();
        self.status = if self.pareto_only {
            "Focus: Pareto Frontier Only".to_string()
        } else {
            "Focus: All Cohort Models".to_string()
        };
    }

    pub fn set_sort(&mut self, key: SortKey) {
        if self.sort_key == key {
            self.sort_desc = !self.sort_desc;
        } else {
            self.sort_key = key;
            self.sort_desc = true;
        }
        self.page = 0;
        self.cursor = 0;
        self.apply_filters();
        let dir = if self.sort_desc { "▼" } else { "▲" };
        self.status = format!("Sorted by {} {dir}", self.sort_key.label());
    }

    pub fn cycle_sort(&mut self) {
        let next = self.sort_key.cycle_next();
        self.set_sort(next);
    }

    pub fn pin_baseline(&mut self) {
        if let Some(&mi) = self.filtered.get(self.cursor) {
            self.baseline = self.cursor;
            let disp: String = self.all[mi].display.chars().take(22).collect();
            self.status = format!("Pinned diff baseline: #{} {disp}", self.cursor + 1);
        }
    }

    pub fn enter_search(&mut self) {
        self.search_backup = self.query.clone();
        self.searching = true;
        self.status.clear();
    }

    pub fn commit_search(&mut self) {
        self.searching = false;
        self.apply_filters();
    }

    /// Esc during search: discard the in-progress query, restore the
    /// pre-search filter (Python kept the half-typed filter — §4.2a).
    pub fn cancel_search(&mut self) {
        self.query = std::mem::take(&mut self.search_backup);
        self.searching = false;
        self.apply_filters();
        self.status = "Search cancelled.".to_string();
    }

    pub fn push_search_char(&mut self, c: char) {
        self.query.push(c);
        self.apply_filters();
    }

    pub fn pop_search_char(&mut self) {
        self.query.pop();
        self.apply_filters();
    }

    /// Main-loop Esc: reset query + pool + pareto + sort, and say exactly that.
    pub fn reset_filters(&mut self) {
        self.query.clear();
        self.pool = "all".to_string();
        self.pareto_only = false;
        self.sort_key = SortKey::Composite;
        self.sort_desc = true;
        self.status = "Filters + sort reset.".to_string();
        self.apply_filters();
    }

    pub fn current(&self) -> Option<&Model> {
        self.filtered.get(self.cursor).map(|&i| &self.all[i])
    }

    pub fn baseline_model(&self) -> Option<&Model> {
        self.filtered.get(self.baseline).map(|&i| &self.all[i])
    }

    pub fn coverage_label(&self) -> &'static str {
        if self.tri_only { "[3/3 Only]" } else { "[All Models]" }
    }

    pub fn is_pareto_idx(&self, filtered_pos: usize) -> bool {
        self.filtered
            .get(filtered_pos)
            .is_some_and(|&i| is_pareto(&self.all[i], &self.pareto))
    }
}

/// Split loaded rows into matched (any benchmark signal) + unmatched count.
/// Honors a precomputed `unmatched` flag, else mirrors bcheck `main()`.
pub fn partition_matched(models: Vec<Model>) -> (Vec<Model>, usize) {
    let mut matched = Vec::with_capacity(models.len());
    let mut unmatched = 0;
    for m in models {
        if m.unmatched {
            unmatched += 1;
            continue;
        }
        let p = pillars(&m);
        if p.has_live || p.has_arena || p.has_aa {
            matched.push(m);
        } else {
            unmatched += 1;
        }
    }
    (matched, unmatched)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{BaseMetrics, Livebench};

    fn tri(display: &str, q: f64, eff: f64, pool: &str) -> Model {
        Model {
            display: display.into(),
            model_id: Some(display.to_lowercase().replace(' ', "-")),
            provider: "Test".into(),
            pool: pool.into(),
            capability_q: Some(q),
            effective_cost: Some(eff),
            price_in: Some(eff),
            price_out: Some(eff),
            livebench: Some(Livebench {
                overall: Some(80.0),
                categories: [("Reasoning".into(), 90.0), ("Coding".into(), 80.0)]
                    .into_iter()
                    .collect(),
                ..Default::default()
            }),
            base_metrics: BaseMetrics {
                lm_elo: Some(1500.0),
                aa_quality: Some(45.0),
                speed_tps: Some(100.0),
                ..Default::default()
            },
            ..Default::default()
        }
    }

    fn partial(display: &str) -> Model {
        Model {
            display: display.into(),
            capability_q: Some(70.0),
            aa_live_quality: Some(25.0),
            ..Default::default()
        }
    }

    fn app() -> App {
        let models = vec![
            tri("Alpha", 95.0, 9.0, "claude"),
            tri("Beta", 85.0, 1.0, "agy"),
            tri("Gamma", 75.0, 0.0, "ocgo"),
            partial("Partial Pete"),
        ];
        let (matched, unmatched) = partition_matched(models);
        App::new(matched, unmatched, true, 50, String::new())
    }

    #[test]
    fn tri_default_excludes_partial() {
        let a = app();
        assert_eq!(a.filtered.len(), 3);
        assert_eq!(a.unmatched_count, 0); // single-signal row is matched (count==1), just not tri
        assert!(a.filtered.iter().all(|&i| pillars(&a.all[i]).coverage_count == 3));
    }

    #[test]
    fn partition_counts_signal_less_rows() {
        let models = vec![
            tri("Alpha", 95.0, 9.0, "claude"),
            Model { display: "Ghost".into(), ..Default::default() },
        ];
        let (matched, unmatched) = partition_matched(models);
        assert_eq!(matched.len(), 1);
        assert_eq!(unmatched, 1);
    }

    #[test]
    fn toggle_tri_includes_partial() {
        let mut a = app();
        a.toggle_tri();
        assert_eq!(a.filtered.len(), 4);
    }

    #[test]
    fn pool_filter_and_cycle() {
        let mut a = app();
        a.pool = "agy".into();
        a.apply_filters();
        assert_eq!(a.filtered.len(), 1);
        a.pool = "all".into();
        a.apply_filters();
        a.cycle_pool();
        assert_eq!(a.pool, "agy");
    }

    #[test]
    fn search_matches_alias_and_cancel_restores() {
        let mut models = vec![tri("Alpha", 95.0, 9.0, "claude"), tri("Beta", 85.0, 1.0, "agy")];
        models[0].aa_aliases = vec!["secret-alias-xyz".into()];
        let (matched, _) = partition_matched(models);
        let mut a = App::new(matched, 0, true, 50, String::new());
        a.enter_search();
        a.query = "secret-alias".into();
        a.apply_filters();
        assert_eq!(a.filtered.len(), 1);
        a.cancel_search();
        assert_eq!(a.query, "");
        assert_eq!(a.filtered.len(), 2);
        assert_eq!(a.status, "Search cancelled.");
    }

    #[test]
    fn reset_clears_sort_too() {
        let mut a = app();
        a.set_sort(SortKey::Price);
        a.pool = "agy".into();
        a.query = "beta".into();
        a.reset_filters();
        assert_eq!(a.query, "");
        assert_eq!(a.pool, "all");
        assert!(!a.pareto_only);
        assert_eq!(a.sort_key, SortKey::Composite);
        assert!(a.sort_desc);
    }

    #[test]
    fn price_sort_unknown_sinks() {
        let mut models = vec![tri("Cheap", 80.0, 0.5, "api"), tri("Mystery", 90.0, 1.0, "api")];
        models[1].effective_cost = None;
        models[1].price_in = None;
        models[1].price_out = None;
        let (matched, _) = partition_matched(models);
        let mut a = App::new(matched, 0, true, 50, String::new());
        a.set_sort(SortKey::Price); // desc=true => ascending for price
        let first = a.filtered[0];
        assert_eq!(a.all[first].display, "Cheap");
    }

    #[test]
    fn pareto_only_is_subset_of_pareto() {
        let mut a = app();
        a.toggle_pareto();
        assert!(a.pareto_only);
        for &i in &a.filtered {
            assert!(is_pareto(&a.all[i], &a.pareto));
        }
    }

    #[test]
    fn top_limit_bounds() {
        let (matched, _) = partition_matched(vec![
            tri("A", 95.0, 9.0, "api"),
            tri("B", 85.0, 1.0, "api"),
            tri("C", 75.0, 0.5, "api"),
        ]);
        let a = App::new(matched, 0, true, 2, String::new());
        assert_eq!(a.filtered.len(), 2);
    }
}
