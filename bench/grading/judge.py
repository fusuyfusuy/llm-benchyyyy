"""LLM-judge ensemble via a user-configured CLI harness, per expected/grading-methodology.md.

No API key needed: judge calls go through one of the harness CLIs (pi-agent by
default) using whatever subscription that CLI is already logged into.

Implements: rubric-based (not free-form) grading, an ensemble of N_JUDGES
independent calls with majority/median voting, and model-identity hiding (the
prompt never says which system/model produced the response).

ponytail: each "judge" is a separate CLI invocation of the same underlying
model -- votes are not independent across judges in the strict ensemble sense.
Acceptable v1 ceiling; upgrade path is judging with different harnesses/models.

ponytail: swap-and-average (bias mitigation for *pairwise* A/B judging) is not
implemented -- v1's `bench run` grades one response against a rubric in
isolation, it never compares two systems head-to-head, so there is no pair to
swap yet. Upgrade path: add a `bench compare` command for pairwise runs and
apply swap-and-average there per grading-methodology.md's guidance.
"""
from __future__ import annotations

import json
import os
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..harness import cli_adapter
from ..harness import configs as harness_configs
from .spec import GradingSpec

# Harness whose CLI casts the judge votes; override with BENCH_JUDGE_HARNESS
# env var or `bench run --judge-harness <name>`.
JUDGE_HARNESS = os.environ.get("BENCH_JUDGE_HARNESS", "pi-agent")
# Provider-scoped model the judge votes with (e.g. anthropic/claude-opus-5);
# override with BENCH_JUDGE_MODEL env var or `bench run --judge-model <id>`.
# Empty -> the harness CLI's own default model. Pin it when the judge would
# otherwise be the same model as the system under test (self-grading bias).
JUDGE_MODEL = os.environ.get("BENCH_JUDGE_MODEL") or None
N_JUDGES = 3

_GATE_PROMPT = """You are a strict binary gate-checker. Read the rule and the response below. \
Answer with a single JSON object: {{"gate_failed": true or false, "reason": "..."}}. \
gate_failed=true means the response violates the rule.

Rule:
{gate}

Response to check (the system that produced it is intentionally unidentified):
{response}
"""

_RUBRIC_PROMPT = """You are grading a response against a rubric. Score each numbered rubric \
item 0 or 1, strictly per its literal wording -- do not let response length or tone \
influence you beyond what the item itself asks. The system that produced this response \
is intentionally unidentified; grade only the content.

Rubric:
{rubric}

Response being graded:
{response}

Respond with a single JSON object: \
{{"scores": {{"<item title>": 0 or 1, ...}}, "total_score": <int>, "max_score": <int>}}.
"""

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class JudgeVerdict:
    passed: bool
    score: int
    total: int
    gate_failed: bool
    raw_votes: list[dict] = field(default_factory=list)


def _fetch_response(prompt: str) -> str:
    """Transport: one CLI call. Module-level so selfcheck can patch it."""
    config = harness_configs.REGISTRY.get(JUDGE_HARNESS)
    if config is None:
        raise ValueError(
            f"judge harness {JUDGE_HARNESS!r} not in REGISTRY; "
            f"pick one of {sorted(harness_configs.REGISTRY)}"
        )
    return cli_adapter.run_host_text(config, prompt, model=JUDGE_MODEL)


def _call_judge(prompt: str) -> dict:
    text = _fetch_response(prompt)
    m = _JSON_OBJ_RE.search(text)
    if not m:
        raise ValueError(f"judge did not return JSON: {text[:500]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"judge returned malformed JSON: {text[:500]!r}") from e


def _call_judges(prompt: str, n: int) -> list[dict]:
    # Independent calls, no shared state -- thread pool is all they need.
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(lambda _: _call_judge(prompt), range(n)))


def grade(spec: GradingSpec, response_text: str) -> JudgeVerdict:
    total_items = len(spec.rubric_item_titles) or 1
    raw_votes: list[dict] = []

    if spec.automatic_gate:
        gate_votes = _call_judges(_GATE_PROMPT.format(gate=spec.automatic_gate, response=response_text), N_JUDGES)
        raw_votes += gate_votes
        gate_failed = sum(1 for v in gate_votes if v.get("gate_failed")) > N_JUDGES // 2
        if gate_failed:
            return JudgeVerdict(passed=False, score=0, total=total_items, gate_failed=True, raw_votes=raw_votes)
    else:
        gate_failed = False

    if not spec.rubric_text:
        raise ValueError(f"{spec.path}: judge-ensemble grading but no '## Rubric' section")

    votes = _call_judges(_RUBRIC_PROMPT.format(rubric=spec.rubric_text, response=response_text), N_JUDGES)
    raw_votes += votes
    def _score_of(vote: dict) -> float:
        # Judge votes are untrusted LLM output -- coerce, don't trust.
        val = vote.get("total_score", 0)
        return val if isinstance(val, (int, float)) and not isinstance(val, bool) else 0

    scores = [_score_of(v) for v in votes]
    maxes = {v.get("max_score") for v in votes}
    # Judges must agree on the scale; if they don't, fall back to the rubric's
    # own item count rather than trusting one arbitrary vote.
    total = total_items
    if len(maxes) == 1 and None not in maxes:
        only = next(iter(maxes))
        if isinstance(only, int) and not isinstance(only, bool):
            total = only
    median_score = int(statistics.median(scores)) if scores else 0
    threshold = spec.pass_threshold or (total, total)
    needed = threshold[0]
    passed = median_score >= needed

    return JudgeVerdict(passed=passed, score=median_score, total=total, gate_failed=gate_failed, raw_votes=raw_votes)
