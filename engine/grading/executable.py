from __future__ import annotations

from dataclasses import dataclass

from .. import sandbox as sandbox_mod
from .spec import GradingSpec


@dataclass
class ExecResult:
    passed: bool
    exit_code: int
    stdout: str
    stderr: str


def grade(spec: GradingSpec, sb: sandbox_mod.Sandbox) -> ExecResult:
    for filename, content in spec.seed_files:
        sandbox_mod.write_file(sb, filename, content)
    if not spec.check_script:
        raise ValueError(f"{spec.path}: executable grading but no '## Check' script")
    proc = sandbox_mod.exec_in(sb, spec.check_script)
    return ExecResult(
        passed=proc.returncode == 0,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
