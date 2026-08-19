"""Anthropic-only LLM-judge ensemble, per expected/grading-methodology.md.

Implements: rubric-based (not free-form) grading, an ensemble of N_JUDGES
independent calls with majority/median voting, and model-identity hiding (the
prompt never says which system/model produced the response). Cross-model
judging is satisfied trivially in v1 since the judge model (JUDGE_MODEL) is
fixed regardless of which model/harness produced the response under grading.

ponytail: swap-and-average (bias mitigation for *pairwise* A/B judging) is not
implemented -- v1's `bench run` grades one response against a rubric in
isolation, it never compares two systems head-to-head, so there is no pair to
swap yet. Upgrade path: add a `bench compare` command for pairwise runs and
apply swap-and-average there per grading-methodology.md's guidance.
"""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field

from .spec import GradingSpec

JUDGE_MODEL = "claude-sonnet-5"
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


def _client():
    import anthropic  # imported lazily so parsing/report code doesn't need the SDK installed

    return anthropic.Anthropic()


def _call_judge(prompt: str) -> dict:
    client = _client()
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    m = _JSON_OBJ_RE.search(text)
    if not m:
        raise ValueError(f"judge did not return JSON: {text!r}")
    return json.loads(m.group(0))


def grade(spec: GradingSpec, response_text: str) -> JudgeVerdict:
    total_items = len(spec.rubric_item_titles) or 1
    raw_votes: list[dict] = []

    if spec.automatic_gate:
        gate_votes = [_call_judge(_GATE_PROMPT.format(gate=spec.automatic_gate, response=response_text)) for _ in range(N_JUDGES)]
        raw_votes += gate_votes
        gate_failed = sum(1 for v in gate_votes if v.get("gate_failed")) > N_JUDGES // 2
        if gate_failed:
            return JudgeVerdict(passed=False, score=0, total=total_items, gate_failed=True, raw_votes=raw_votes)
    else:
        gate_failed = False

    if not spec.rubric_text:
        raise ValueError(f"{spec.path}: judge-ensemble grading but no '## Rubric' section")

    votes = [_call_judge(_RUBRIC_PROMPT.format(rubric=spec.rubric_text, response=response_text)) for _ in range(N_JUDGES)]
    raw_votes += votes
    scores = [v.get("total_score", 0) for v in votes]
    maxes = [v.get("max_score", total_items) for v in votes]
    median_score = int(statistics.median(scores)) if scores else 0
    total = maxes[0] if maxes else total_items
    needed, _denom = spec.pass_threshold or (total, total)
    passed = median_score >= needed

    return JudgeVerdict(passed=passed, score=median_score, total=total, gate_failed=gate_failed, raw_votes=raw_votes)
