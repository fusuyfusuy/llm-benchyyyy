from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

RESULTS_PATH = Path("results/runs.jsonl")


@dataclass
class RunRecord:
    """One row per attempt, fields matching metrics.md exactly."""

    task_id: str
    model: str
    harness: str
    harness_version: str
    tool_access: str
    scaffold_notes: str
    trial_number: int
    result: str  # pass | fail | partial
    grading_method: str
    constraint_violations: str
    wall_clock_seconds: float
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    cost_usd: float | None
    tool_call_count: int | None


def append(record: RunRecord, path: Path = RESULTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(asdict(record)) + "\n")


def load_all(path: Path = RESULTS_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]
