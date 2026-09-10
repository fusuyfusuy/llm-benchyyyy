//! Cache staleness: filename-date ages and newest-snapshot ranking.
//!
//! Ports `snapshot_date_str`, `snapshot_age_hours`, `newest_snapshot_age_h`,
//! `cache_staleness_note` (`checkers/benchmark_common.py`,
//! `checkers/llm_benchmark_aggregator.py`). Std-only civil-date math —
//! the filename date is authoritative (mtime lies after a fresh clone).

use std::path::{Path, PathBuf};
use std::time::SystemTime;

pub const CACHE_TTL_H: f64 = 24.0;

/// Days since civil 1970-01-01 (Howard Hinnant's algorithm).
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

fn unix_days_now() -> i64 {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| (d.as_secs() / 86400) as i64)
        .unwrap_or(0)
}

fn valid_date(y: i64, m: i64, d: i64) -> bool {
    if !(1..=12).contains(&m) || d < 1 {
        return false;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let dim = match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        _ => {
            if leap {
                29
            } else {
                28
            }
        }
    };
    d <= dim
}

/// `YYYYMMDD` embedded as `_########` before a simple alphanumeric extension.
pub fn snapshot_date_str(file_name: &str) -> Option<String> {
    let (stem, ext) = file_name.rsplit_once('.')?;
    if ext.is_empty() || !ext.bytes().all(|b| b.is_ascii_alphanumeric()) {
        return None;
    }
    let digits = stem.rsplit_once('_')?.1;
    if digits.len() != 8 || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let y: i64 = digits[0..4].parse().ok()?;
    let m: i64 = digits[4..6].parse().ok()?;
    let d: i64 = digits[6..8].parse().ok()?;
    valid_date(y, m, d).then(|| digits.to_string())
}

fn mtime_secs(path: &Path) -> Option<u64> {
    path.metadata()
        .ok()?
        .modified()
        .ok()?
        .duration_since(SystemTime::UNIX_EPOCH)
        .ok()
        .map(|d| d.as_secs())
}

fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Age in hours from the filename date (day boundary), else mtime. `None` when unknowable.
pub fn snapshot_age_hours(path: &Path, now_days: i64) -> Option<f64> {
    if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
        if let Some(ds) = snapshot_date_str(name) {
            let y: i64 = ds[0..4].parse().ok()?;
            let m: i64 = ds[4..6].parse().ok()?;
            let d: i64 = ds[6..8].parse().ok()?;
            let midnight = days_from_civil(y, m, d) * 86400;
            let age = (now_secs() as i64 - midnight).max(0) as f64 / 3600.0;
            return Some(age);
        }
    }
    let mtime_days = mtime_secs(path)? as i64 / 86400;
    Some((now_days - mtime_days).max(0) as f64 * 24.0)
}

/// Newest snapshot whose filename contains `part` (+`20` year marker),
/// ranked by embedded date first, mtime second.
pub fn newest_matching(raw_dir: &Path, part: &str) -> Option<PathBuf> {
    let entries = std::fs::read_dir(raw_dir).ok()?;
    let mut best: Option<(Option<String>, u64, PathBuf)> = None;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !name.contains(part) || !name.contains("20") {
            continue;
        }
        let date = snapshot_date_str(&name);
        let mtime = mtime_secs(&entry.path()).unwrap_or(0);
        let rank = (date.clone(), mtime);
        let is_better = match &best {
            None => true,
            Some((bd, bm, _)) => rank > (bd.clone(), *bm),
        };
        if is_better {
            best = Some((date, mtime, entry.path()));
        }
    }
    best.map(|(_, _, p)| p)
}

/// Offline-run staleness warning; empty when every source is fresh.
pub fn cache_staleness_note(raw_dir: &Path) -> String {
    let now = unix_days_now();
    let mut parts = Vec::new();
    for (name, part) in [
        ("LiveBench", "livebench"),
        ("LMArena", "lmarena"),
        ("Artificial Analysis", "artificial_analysis"),
    ] {
        match newest_matching(raw_dir, part).and_then(|p| snapshot_age_hours(&p, now)) {
            None => parts.push(format!("{name} missing")),
            Some(age) if age > CACHE_TTL_H => parts.push(format!("{name} {age:.0}h old")),
            Some(_) => {}
        }
    }
    if parts.is_empty() {
        String::new()
    } else {
        format!("cached responses >24h — run with --fetch: {}", parts.join(", "))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn date_parsing() {
        assert_eq!(
            snapshot_date_str("livebench_20260909.csv"),
            Some("20260909".to_string())
        );
        assert_eq!(snapshot_date_str("livebench_2026.csv"), None);
        assert_eq!(snapshot_date_str("livebench_20261301.csv"), None);
        assert_eq!(snapshot_date_str("livebench_20260230.csv"), None);
        assert_eq!(snapshot_date_str("livebench_20240229.csv"), Some("20240229".to_string()));
        assert_eq!(snapshot_date_str("no_date.csv"), None);
        assert_eq!(snapshot_date_str("livebench_20260909.tar.gz"), None); // dotted ext
    }

    #[test]
    fn age_math_from_filename() {
        let now_days = unix_days_now();
        let p = Path::new("livebench_20260909.csv");
        let age = snapshot_age_hours(p, now_days).unwrap();
        let midnight = days_from_civil(2026, 9, 9) * 86400;
        let expected = (now_secs() as i64 - midnight).max(0) as f64 / 3600.0;
        assert!((age - expected).abs() < 0.01, "age={age} expected={expected}");
        let future = Path::new("livebench_29990101.csv");
        assert_eq!(snapshot_age_hours(future, now_days), Some(0.0));
    }

    #[test]
    fn note_reports_missing_and_old() {
        let dir = std::env::temp_dir().join(format!("checkerz_stale_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("livebench_20200101.csv"), "a").unwrap();
        let note = cache_staleness_note(&dir);
        assert!(note.contains("LiveBench"), "{note}");
        assert!(note.contains("LMArena missing"), "{note}");
        assert!(note.contains("Artificial Analysis missing"), "{note}");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
