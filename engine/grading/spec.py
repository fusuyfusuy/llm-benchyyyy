from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import markdown as md

_RUBRIC_TITLE_RE = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*", re.MULTILINE)
_THRESHOLD_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_BOLD_NUMBER_RE = re.compile(r"\*\*([0-9][0-9,]*)\*\*")


@dataclass
class GradingSpec:
    id: str
    path: Path
    method: str  # "unit-test" | "state-check" | "exact-match" | "judge-ensemble"
    seed_files: list[tuple[str, str]] = field(default_factory=list)
    check_script: str | None = None
    expected_value: str | None = None
    automatic_gate: str | None = None
    rubric_text: str | None = None
    rubric_item_titles: list[str] = field(default_factory=list)
    pass_threshold: tuple[int, int] | None = None


def _classify_method(method_raw: str, path: Path) -> str:
    m = method_raw.lower()
    if "exact match" in m:
        return "exact-match"
    if "unit test" in m:
        return "unit-test"
    if "state check" in m:
        return "state-check"
    if "judge" in m:
        return "judge-ensemble"
    raise ValueError(f"{path}: unrecognized grading method {method_raw!r}")


def parse_grading_spec(path: Path) -> GradingSpec:
    text = path.read_text()
    method_raw = md.extract_bold_field(text, "grading method") or ""
    method = _classify_method(method_raw, path)

    held_out = md.extract_section(text, "Held-out test suite") or ""
    seed_files = md.extract_seed_files(held_out)

    check_section = md.extract_section(text, "Check")
    check_script = md.first_bash_block(check_section) if check_section else None
    if method in ("unit-test", "state-check") and not check_script:
        raise ValueError(f"{path}: {method} grading requires a '## Check' bash block")

    expected_value = None
    if method == "exact-match":
        pass_section = md.extract_section(text, "Pass criteria") or ""
        m = _BOLD_NUMBER_RE.search(pass_section)
        expected_value = m.group(1).replace(",", "") if m else None
        if expected_value is None:
            raise ValueError(
                f"{path}: exact-match grading requires a bold number in '## Pass criteria'"
            )

    automatic_gate = None
    gate_section = md.extract_section(text, "Automatic gate")
    if gate_section:
        automatic_gate = gate_section.strip()

    rubric_text = None
    rubric_item_titles: list[str] = []
    rubric_section = md.extract_section(text, "Rubric")
    if rubric_section:
        rubric_text = rubric_section.strip()
        rubric_item_titles = [m.group(1).strip() for m in _RUBRIC_TITLE_RE.finditer(rubric_section)]

    pass_threshold = None
    if method == "judge-ensemble":
        pass_section = md.extract_section(text, "Pass criteria") or ""
        m = _THRESHOLD_RE.search(pass_section)
        if m:
            pass_threshold = (int(m.group(1)), int(m.group(2)))

    return GradingSpec(
        id=path.stem,
        path=path,
        method=method,
        seed_files=seed_files,
        check_script=check_script,
        expected_value=expected_value,
        automatic_gate=automatic_gate,
        rubric_text=rubric_text,
        rubric_item_titles=rubric_item_titles,
        pass_threshold=pass_threshold,
    )
