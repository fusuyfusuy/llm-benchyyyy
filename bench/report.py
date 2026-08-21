from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from . import results as results_mod

GROUP_KEYS = ("task_id", "model", "harness", "tool_access")
TABLE_HEADERS = (
    "task_id",
    "model",
    "harness",
    "tool_access",
    "trials",
    "pass_rate",
    "cost_per_success_usd",
    "time_per_success_seconds",
    "cost_per_trial_usd",
    "time_per_trial_seconds",
)


def aggregate(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = tuple(r[k] for k in GROUP_KEYS)
        groups[key].append(r)

    out = []
    for key, rs in groups.items():
        n = len(rs)
        passes = [r for r in rs if r["result"] == "pass"]
        pass_rate = len(passes) / n if n else 0.0
        total_cost = sum(r.get("cost_usd") or 0 for r in rs)
        total_time = sum(r.get("wall_clock_seconds") or 0 for r in rs)
        cost_per_success = (total_cost / len(passes)) if passes else None
        time_per_success = (total_time / len(passes)) if passes else None
        row = dict(zip(GROUP_KEYS, key))
        row.update(
            trials=n,
            pass_rate=pass_rate,
            cost_per_success_usd=cost_per_success,
            time_per_success_seconds=time_per_success,
            total_cost_usd=total_cost,
            # Dispersion companions: per-trial means make a run of N=1 look
            # like what it is next to an N=3 group with the same totals.
            cost_per_trial_usd=(total_cost / n) if n else None,
            time_per_trial_seconds=(total_time / n) if n else None,
        )
        out.append(row)
    out.sort(key=lambda r: tuple(str(r[k]) for k in GROUP_KEYS))
    return out


def format_table(rows: list[dict]) -> str:
    lines = [" | ".join(TABLE_HEADERS), " | ".join("-" * len(h) for h in TABLE_HEADERS)]
    for r in rows:
        cells = []
        for h in TABLE_HEADERS:
            v = r.get(h)
            if isinstance(v, float):
                v = f"{v:.4f}"
            cells.append("-" if v is None else str(v))
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def write_report(
    out_path: Path = Path("results/report.md"),
    results_path: Path = results_mod.RESULTS_PATH,
) -> str:
    rows = results_mod.load_all(results_path)
    agg = aggregate(rows)
    table = format_table(agg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("# Benchmark report\n\n" + table + "\n")
    return table
