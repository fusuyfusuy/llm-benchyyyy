"""Docker sandbox: a bind-mounted temp dir + `docker run --rm` per command.

Deliberately not per-run image builds and not a long-lived container -- the temp
dir on the host is what persists state between the setup script, the harness
run, and the grading check, so a fresh container per `run()` call is simpler
and just as correct.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import task as task_mod

BASE_IMAGE = "llm-bench-harness"

# Host config/credential dirs bind-mounted into the container so CLI
# harnesses reuse the host's existing login instead of re-authenticating.
# pi reads/writes auth, model-registry cache, settings, and session locks all
# over ~/.pi/agent/, so that one is mounted READ-WRITE as a directory
# (individual ro file mounts leave the root-owned parent unwritable ->
# EACCES on settings.json.lock, and the registry cache never loads).
# Everything else stays read-only.
CREDENTIAL_MOUNTS = [
    ".claude",
    ".claude.json",
    ".gemini",
    ".config/opencode",
    ".codex",
    ".pi/agent",
]

# Subset of CREDENTIAL_MOUNTS mounted read-write (see comment above).
RW_MOUNTS = {".pi/agent", ".gemini"}


@dataclass
class Sandbox:
    workdir: Path
    container_env: dict = field(default_factory=dict)


def create(
    seed_files: list[task_mod.SeedFile],
    setup_script: str | None,
    env: dict | None = None,
) -> Sandbox:
    tmp = Path(tempfile.mkdtemp(prefix="llm-bench-"))
    for f in seed_files:
        write_file_to(tmp, f.path, f.content)
    sb = Sandbox(workdir=tmp, container_env=env or {})
    if setup_script:
        result = run(sb, setup_script)
        if result.returncode != 0:
            raise RuntimeError(
                f"task setup script failed (exit {result.returncode}): {result.stderr}"
            )
    return sb


def write_file_to(base: Path, rel_path: str, content: str) -> None:
    target = base / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def write_file(sb: Sandbox, rel_path: str, content: str) -> None:
    write_file_to(sb.workdir, rel_path, content)


def _docker_run_args(sb: Sandbox, extra_env: dict | None = None) -> list[str]:
    home = Path.home()
    args = [
        "docker",
        "run",
        "--rm",
        "--init",
        "-v",
        f"{sb.workdir}:/workspace",
        "-w",
        "/workspace",
    ]
    for rel in CREDENTIAL_MOUNTS:
        host_path = home / rel
        if host_path.exists():
            suffix = "" if rel in RW_MOUNTS else ":ro"
            args += ["-v", f"{host_path}:/home/ubuntu/{rel}{suffix}"]
    merged_env = {**sb.container_env, **(extra_env or {})}
    for k, v in merged_env.items():
        args += ["-e", f"{k}={v}"]
    args.append(BASE_IMAGE)
    return args


def run(
    sb: Sandbox,
    command: str,
    extra_env: dict | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    args = _docker_run_args(sb, extra_env) + ["bash", "-lc", command]
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        # A hung harness run is a data point (exit 124 = timeout convention),
        # not a reason to crash the batch.
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return subprocess.CompletedProcess(
            args, returncode=124, stdout=out,
            stderr=f"{err}\nbench: timed out after {timeout}s",
        )


def exec_in(sb: Sandbox, command: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return run(sb, command, timeout=timeout)


def cleanup(sb: Sandbox) -> None:
    shutil.rmtree(sb.workdir, ignore_errors=True)
