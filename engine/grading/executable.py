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
    proc = sandbox_mod.exec_in(sb, spec.check_script, network=False)
    if proc.returncode in (125, 126):
        # docker client errors: 125 = container never started (daemon down,
        # image missing, bad flags), 126 = found but not executable. These
        # are infrastructure failures, not model failures -- raise so cmd_run
        # counts the trial errored instead of appending a clean-looking
        # "fail" RunRecord that poisons the pass-rate aggregates.
        raise RuntimeError(
            f"grading container did not run (docker rc={proc.returncode}): "
            f"{proc.stderr[-500:]}"
        )
    return ExecResult(
        passed=proc.returncode == 0,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
