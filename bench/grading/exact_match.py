from __future__ import annotations

import re
from dataclasses import dataclass

from .spec import GradingSpec

_NUMBER_RE = re.compile(r"-?\d[\d,]*")


@dataclass
class ExactMatchResult:
    passed: bool
    extracted: str | None
    expected: str


def grade(spec: GradingSpec, response_text: str) -> ExactMatchResult:
    if spec.expected_value is None:
        raise ValueError(f"{spec.path}: exact-match grading but no expected value found")
    # Last number wins: models often restate given figures in prose before the
    # final answer ("480 - 120 = 360, so 368 remain"), and the final answer is
    # conventionally last.
    matches = _NUMBER_RE.findall(response_text)
    extracted = matches[-1].replace(",", "") if matches else None
    return ExactMatchResult(
        passed=extracted == spec.expected_value,
        extracted=extracted,
        expected=spec.expected_value,
    )
