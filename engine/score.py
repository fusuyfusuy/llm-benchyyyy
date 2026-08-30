"""100-point categorical leaderboard over results/runs.jsonl.

Groups on the single shared comparability contract (report.GROUP_KEYS:
task_id, model, harness, harness_version, tool_access) — a third
grouping convention is not allowed; metrics.md:14-16 and memory.md rule 3.
"""
import collections
import json
from pathlib import Path

from .report import GROUP_KEYS

# The 20 tasks map exactly to 3 distinct categories based on their directory
CATEGORIES = {
    "agentic": [
        "ci-pipeline-recovery", "environment-pivot-recovery", "needle-in-file-haystack",
        "policy-adherence-pressure", "recover-from-wrong-command", "silent-failure-self-correction"
    ],
    "coding": [
        "add-csv-export-endpoint", "cross-file-interaction-bug", "fix-off-by-one-pagination",
        "hotpath-quadratic-bottleneck", "jsonpatch-rfc6902-hardened", "security-idor-vulnerability",
        "strangler-fig-refactoring", "streaming-memory-optimization", "ttl-cache-concurrency-audit",
        "wal-torn-write-recovery"
    ],
    "reasoning": [
        "custom-assembly-interpreter", "long-horizon-context-puzzle",
        "multi-step-inventory-word-problem", "nested-bracket-parser"
    ]
}

MIN_TRIALS = 3  # memory.md rule 3: pass_rate needs N>=3 samples


def get_category(task_id: str) -> str:
    for cat, tasks in CATEGORIES.items():
        if task_id in tasks:
            return cat
    return "unknown"


def group_trials(rows: list[dict]) -> dict[tuple, dict[int, bool]]:
    """GROUP_KEYS-comparable groups -> {trial_number: passed}.

    Repeated trial_number within a group is a re-run correction, not an
    extra sample: keep the last row seen (file order = append order)."""
    groups: dict[tuple, dict[int, bool]] = collections.defaultdict(dict)
    for run in rows:
        key = tuple(run[k] for k in GROUP_KEYS)
        groups[key][run["trial_number"]] = run.get("result") == "pass"
    return groups


def score_groups(rows: list[dict]) -> list[dict]:
    """One scoring row per 5-key group: pass_rate, 5-pt task points, and an
    under-trialed flag — a 1-trial pass must never look like a settled
    2/3-proportional score."""
    out = []
    for key, trials in group_trials(rows).items():
        group = dict(zip(GROUP_KEYS, key))
        n = len(trials)
        passes = sum(trials.values())
        pass_rate = passes / n if n else 0.0
        group.update(
            trials=n,
            passes=passes,
            pass_rate=pass_rate,
            points=pass_rate * 5.0,
            under_trialed=n < MIN_TRIALS,
        )
        out.append(group)
    return out


def main():
    runs_file = Path("results/runs.jsonl")
    if not runs_file.exists():
        # Fall back to archived runs file if provided or default archive
        archives = sorted(Path("results").glob("archive_*"))
        if archives:
            runs_file = archives[-1] / "runs.jsonl"
        else:
            print("No results/runs.jsonl found.")
            return

    with open(runs_file, "r") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    # One leaderboard line per (harness, harness_version, tool_access, model):
    # runs differing on any group key are not comparable and must not share
    # one pass_rate (F-07 / SEAM M2).
    board: dict[tuple, dict[str, dict]] = collections.defaultdict(dict)
    for g in score_groups(rows):
        if get_category(g["task_id"]) == "unknown":
            continue
        line_key = (g["harness"], g["harness_version"], g["tool_access"], g["model"])
        board[line_key][g["task_id"]] = g

    width = 110
    print(f"\n{'🏆 Leaderboard (100-Point Scale)':^{width}}")
    print("=" * (width + 2))
    print(f"{'Harness':<14} | {'Version':<21} | {'Tool access':<15} | {'Model':<25} | "
          f"{'Overall':<7} | {'Agentic':<7} | {'Coding':<7} | {'Reasoning':<7} | U")
    print("-" * (width + 2))

    for (harness, hversion, tool_access, model), tasks in board.items():
        cat_scores = {"agentic": 0.0, "coding": 0.0, "reasoning": 0.0}
        cat_max = {"agentic": len(CATEGORIES["agentic"]) * 5,
                   "coding": len(CATEGORIES["coding"]) * 5,
                   "reasoning": len(CATEGORIES["reasoning"]) * 5}

        total_score = 0.0
        for task_id, g in tasks.items():
            cat = get_category(task_id)
            cat_scores[cat] += g["points"]
            total_score += g["points"]
        under = sum(1 for g in tasks.values() if g["under_trialed"])

        agentic_pct = (cat_scores["agentic"] / cat_max["agentic"]) * 100 if cat_max["agentic"] else 0
        coding_pct = (cat_scores["coding"] / cat_max["coding"]) * 100 if cat_max["coding"] else 0
        reasoning_pct = (cat_scores["reasoning"] / cat_max["reasoning"]) * 100 if cat_max["reasoning"] else 0

        print(f"{harness:<14} | {hversion:<21} | {tool_access:<15} | {model:<25} | "
              f"{total_score:>5.1f}/100 | {agentic_pct:>4.0f}%   | {coding_pct:>4.0f}%   | "
              f"{reasoning_pct:>4.0f}%   | {under}")

    print("=" * (width + 2))
    print("* Each of the 20 tasks is worth exactly 5.0 points (100 points total).")
    print("* Points are awarded proportionally based on trial pass rates (e.g. 2/3 passes = 3.33 points).")
    print(f"* U = count of 'under-trialed' task groups with <{MIN_TRIALS} distinct trials:")
    print("  their points carry no non-determinism margin (memory.md rule 3) — do not rank on them.")
    print(f"* Reading data from: {runs_file}\n")


if __name__ == "__main__":
    main()
