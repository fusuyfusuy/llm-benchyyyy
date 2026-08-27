import json
import collections
from pathlib import Path
import sys

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

def get_category(task_id: str) -> str:
    for cat, tasks in CATEGORIES.items():
        if task_id in tasks:
            return cat
    return "unknown"

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

    # Track results: data[harness][model][task_id] = [True, False, True]
    data = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))

    with open(runs_file, "r") as f:
        for line in f:
            if not line.strip(): continue
            run = json.loads(line)
            is_pass = run.get("result") == "pass"
            data[run["harness"]][run["model"]][run["task_id"]].append(is_pass)

    print(f"\n{'🏆 Leaderboard (100-Point Scale)':^80}")
    print("=" * 82)
    print(f"{'Harness':<15} | {'Model':<25} | {'Overall':<7} | {'Agentic':<7} | {'Coding':<7} | {'Reasoning':<7}")
    print("-" * 82)

    for harness, models in data.items():
        for model, tasks in models.items():
            cat_scores = {"agentic": 0.0, "coding": 0.0, "reasoning": 0.0}
            cat_max = {"agentic": len(CATEGORIES["agentic"]) * 5, 
                       "coding": len(CATEGORIES["coding"]) * 5, 
                       "reasoning": len(CATEGORIES["reasoning"]) * 5}
            
            total_score = 0.0
            
            for task_id, trials in tasks.items():
                cat = get_category(task_id)
                if cat == "unknown": continue
                
                pass_rate = sum(trials) / len(trials)
                points = pass_rate * 5.0  # 5 points per task
                
                cat_scores[cat] += points
                total_score += points
                
            agentic_pct = (cat_scores["agentic"] / cat_max["agentic"]) * 100 if cat_max["agentic"] else 0
            coding_pct = (cat_scores["coding"] / cat_max["coding"]) * 100 if cat_max["coding"] else 0
            reasoning_pct = (cat_scores["reasoning"] / cat_max["reasoning"]) * 100 if cat_max["reasoning"] else 0
            
            print(f"{harness:<15} | {model:<25} | {total_score:>5.1f}/100 | {agentic_pct:>4.0f}%   | {coding_pct:>4.0f}%   | {reasoning_pct:>4.0f}%")
            
    print("=" * 82)
    print("* Each of the 20 tasks is worth exactly 5.0 points (100 points total).")
    print("* Points are awarded proportionally based on trial pass rates (e.g. 2/3 passes = 3.33 points).")
    print(f"* Reading data from: {runs_file}\n")

if __name__ == "__main__":
    main()
