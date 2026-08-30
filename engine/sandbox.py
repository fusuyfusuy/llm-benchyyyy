"""Docker sandbox: a bind-mounted temp dir + `docker run --rm` per command.

Deliberately not per-run image builds and not a long-lived container -- the temp
dir on the host is what persists state between the setup script, the harness
run, and the grading check, so a fresh container per `run()` call is simpler
and just as correct.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import task as task_mod

BASE_IMAGE = "llm-bench-harness"

# Host config/credential dirs bind-mounted into the container READ-ONLY so CLI
# harnesses reuse the host's existing login instead of re-authenticating
# (ADR 2026-08-19). Nothing here is host-writable: an rw bind of a credential
# tree lets model-controlled bash rewrite host state -- the old rw
# ~/.pi/agent mount let a task agent edit settings.json, whose `packages`
# list pi auto-installs on next launch (host code execution). pi does need a
# writable ~/.pi/agent for its lock/session files; it gets a per-run
# throwaway overlay instead of the host dir (see _make_pi_overlay).
# .gemini is mounted ro: the antigravity CLI only reads its login state.
CREDENTIAL_MOUNTS = [
    ".claude",
    ".claude.json",
    ".gemini",
    ".config/opencode",
    ".codex",
]

# pi state files copied into the throwaway overlay (plain files only).
_PI_OVERLAY_FILES = ("settings.json", "models-store.json")


@dataclass
class Sandbox:
    workdir: Path
    container_env: dict = field(default_factory=dict)
    pi_overlay: Path | None = None


def _make_pi_overlay() -> Path | None:
    """Per-run throwaway replacement for host ~/.pi/agent.

    pi writes settings.json.lock and session files, so its $HOME dir must be
    writable; mounting the host dir rw exposed host config to agent code.
    The overlay carries only the plain state files pi needs to be logged in;
    the host npm extension tree is bound read-only over <overlay>/npm by
    _docker_run_args, and everything the container writes dies in cleanup().
    """
    host_pi = Path.home() / ".pi" / "agent"
    if not host_pi.is_dir():
        return None
    overlay = Path(tempfile.mkdtemp(prefix="llm-bench-pi-"))
    for name in _PI_OVERLAY_FILES:
        src = host_pi / name
        if src.is_file() and not src.is_symlink():
            shutil.copy2(src, overlay / name)
    if (host_pi / "npm").is_dir():
        # placeholder mount point; the real npm tree ro-binds here at run()
        (overlay / "npm").mkdir()
    return overlay


def create(
    seed_files: list[task_mod.SeedFile],
    setup_script: str | None,
    env: dict | None = None,
) -> Sandbox:
    tmp = Path(tempfile.mkdtemp(prefix="llm-bench-"))
    sb = Sandbox(workdir=tmp, container_env=env or {}, pi_overlay=_make_pi_overlay())
    for f in seed_files:
        write_file_to(tmp, f.path, f.content)
    if setup_script:
        result = run(sb, setup_script, network=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"task setup script failed (exit {result.returncode}): {result.stderr}"
            )
    return sb


def _contained_target(base: Path, rel_path: str) -> Path:
    """Sandbox-containment guard shared by task-seed and grading-seed writes.

    Mirrors harness/raw_api._resolve_in_sandbox, hardened for the case that
    file has to assume (an earlier agent phase may have planted symlinks
    inside the workdir): rejects absolute paths and any '..' component, then
    requires the nearest existing ancestor of the target to resolve inside
    the base -- so a symlinked parent (or an already-symlinked target) cannot
    pivot the write outside. The final component is additionally opened with
    O_NOFOLLOW in write_file_to.
    """
    p = Path(rel_path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"seed path must be sandbox-relative without '..': {rel_path!r}")
    resolved_base = base.resolve()
    target = resolved_base / p
    anchor = target
    while not anchor.exists():
        anchor = anchor.parent
    if not anchor.resolve().is_relative_to(resolved_base):
        raise PermissionError(f"seed path escapes the sandbox: {rel_path!r}")
    return target


def write_file_to(base: Path, rel_path: str, content: str) -> None:
    target = _contained_target(base, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # O_NOFOLLOW: if the final component is (or raced into) a symlink, fail
    # loudly instead of writing through it to an attacker-chosen host path.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(content)


def write_file(sb: Sandbox, rel_path: str, content: str) -> None:
    write_file_to(sb.workdir, rel_path, content)


def _docker_run_args(
    sb: Sandbox, extra_env: dict | None = None, network: bool = True
) -> list[str]:
    home = Path.home()
    args = [
        "docker",
        "run",
        "--rm",
        "--init",
        # lets run() `docker kill` the daemon-side container if the client
        # times out (killing the client alone does NOT stop the container)
        "--cidfile",
        str(sb.workdir / "cid"),
        "-v",
        f"{sb.workdir}:/workspace",
        "-w",
        "/workspace",
    ]
    if not network:
        # setup/grading phases run task-authored bash that never needs egress
        # (verified: 0 network commands in tasks/ + expected/ scripts). Cuts
        # credential exfiltration from model-reachable code. Harness runs keep
        # the network: the CLIs must reach their providers.
        args += ["--network", "none"]
    for rel in CREDENTIAL_MOUNTS:
        host_path = home / rel
        if host_path.exists():
            args += ["-v", f"{host_path}:/home/ubuntu/{rel}:ro"]
    if sb.pi_overlay is not None:
        # rw, but the writable tree is throwaway (cleanup rmtree's it)
        args += ["-v", f"{sb.pi_overlay}:/home/ubuntu/.pi/agent"]
        if (sb.pi_overlay / "npm").is_dir():
            args += ["-v", f"{home / '.pi' / 'agent' / 'npm'}:/home/ubuntu/.pi/agent/npm:ro"]
    merged_env = {**sb.container_env, **(extra_env or {})}
    for k, v in merged_env.items():
        args += ["-e", f"{k}={v}"]
    args.append(BASE_IMAGE)
    return args


def _kill_timed_out_container(cidfile: Path) -> None:
    """Best-effort `docker kill` for the container started by a timed-out run.

    subprocess.run's timeout only SIGKILLs the local docker client; without
    this the orphaned container keeps executing agent code (with credential
    mounts and network) indefinitely past every timeout bound. Never raises:
    the caller still returns the rc-124 data point.
    """
    try:
        cid = cidfile.read_text().strip()
    except OSError:
        return  # client died before the daemon wrote the id: no orphan to kill
    if not cid:
        return
    try:
        subprocess.run(
            ["docker", "kill", cid], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        # debug note, not a failure: we cannot do more without the daemon
        print(f"bench: debug: docker kill {cid[:12]} failed: {type(e).__name__}: {e}")


def run(
    sb: Sandbox,
    command: str,
    extra_env: dict | None = None,
    timeout: int = 600,
    network: bool = True,
) -> subprocess.CompletedProcess:
    """network=False (--network none) for task setup + grading phases: their
    agent/task-authored bash has no legitimate egress; harness runs need it."""
    cidfile = sb.workdir / "cid"
    cidfile.unlink(missing_ok=True)  # docker refuses an existing --cidfile
    args = _docker_run_args(sb, extra_env, network) + ["bash", "-lc", command]
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        _kill_timed_out_container(cidfile)
        # A hung harness run is a data point (exit 124 = timeout convention),
        # not a reason to crash the batch.
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return subprocess.CompletedProcess(
            args, returncode=124, stdout=out,
            stderr=f"{err}\nbench: timed out after {timeout}s",
        )


def exec_in(
    sb: Sandbox, command: str, timeout: int = 300, network: bool = True
) -> subprocess.CompletedProcess:
    return run(sb, command, timeout=timeout, network=network)


def cleanup(sb: Sandbox) -> None:
    shutil.rmtree(sb.workdir, ignore_errors=True)
    if sb.pi_overlay is not None:
        shutil.rmtree(sb.pi_overlay, ignore_errors=True)
