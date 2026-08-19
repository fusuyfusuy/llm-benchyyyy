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
    m = _NUMBER_RE.search(response_text)
    extracted = m.group(0).replace(",", "") if m else None
    return ExactMatchResult(
        passed=extracted == spec.expected_value,
        extracted=extracted,
        expected=spec.expected_value,
    )
