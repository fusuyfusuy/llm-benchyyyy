from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from . import results as results_mod

# The single shared comparability contract (metrics.md:14-16, memory.md rule
# "layer attribution"); score.py imports this constant, no second convention.
GROUP_KEYS = ("task_id", "model", "harness", "harness_version", "tool_access")
TABLE_HEADERS = (
    "task_id",
    "model",
    "harness",
    "harness_version",
    "tool_access",
    "trials",
    "pass_rate",
    "cost_per_success_usd",
    "time_per_success_seconds",
    "cost_per_trial_usd",
    "time_per_trial_seconds",
    "avg_input_tokens",
    "avg_output_tokens",
    "total_tokens",
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
        # A null cost means "unpriced harness", not "$0 spent" -- the old
        # `or 0` coercion reported benchmark-spend groups as free. All-null
        # aggregates to null; mixed sums only the known ones and counts the
        # rest so the renderer can annotate them.
        costs = [r.get("cost_usd") for r in rs]
        known_costs = [c for c in costs if c is not None]
        total_cost = sum(known_costs) if known_costs else None
        cost_unpriced = len(costs) - len(known_costs)
        total_time = sum(r.get("wall_clock_seconds") or 0 for r in rs)
        total_in_tokens = sum(r.get("input_tokens") or 0 for r in rs)
        total_out_tokens = sum(r.get("output_tokens") or 0 for r in rs)
        total_tokens = total_in_tokens + total_out_tokens
        cost_per_success = (
            (total_cost / len(passes)) if passes and total_cost is not None else None
        )
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
            cost_per_trial_usd=(total_cost / n) if (n and total_cost is not None) else None,
            time_per_trial_seconds=(total_time / n) if n else None,
            avg_input_tokens=(total_in_tokens / n) if n else 0,
            avg_output_tokens=(total_out_tokens / n) if n else 0,
            total_tokens=total_tokens,
            cost_unpriced=cost_unpriced,
        )
        out.append(row)
    out.sort(key=lambda r: tuple(str(r[k]) for k in GROUP_KEYS))
    return out


COST_COLUMNS = ("cost_per_success_usd", "total_cost_usd", "cost_per_trial_usd")


def _fmt_cost(v: float | None, r: dict) -> str:
    """Render None as 'unpriced' (never $0); partially-known spend is the
    sum of the known rows annotated with how many trials lack a price."""
    unpriced = r.get("cost_unpriced", 0)
    if v is None:
        return "unpriced" if unpriced and r.get("total_cost_usd") is None else "-"
    return f"{v:.4f} ({unpriced} unpriced)" if unpriced else f"{v:.4f}"


def format_table(rows: list[dict]) -> str:
    lines = [" | ".join(TABLE_HEADERS), " | ".join("-" * len(h) for h in TABLE_HEADERS)]
    for r in rows:
        cells = []
        for h in TABLE_HEADERS:
            v = r.get(h)
            if h in COST_COLUMNS:
                cells.append(_fmt_cost(v, r))
                continue
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
