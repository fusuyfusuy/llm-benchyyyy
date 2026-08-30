# Scope 4 — Engine Pipeline Audit

- **Auditor:** Scope4Engine
- **Date:** 2026-08-30
- **Files audited:** `engine/cli.py`, `engine/task.py`, `engine/markdown.py`, `engine/sandbox.py`, `engine/results.py`, `engine/report.py`, `engine/score.py`, `engine/selfcheck.py`, `engine/selfsolve.py`, `engine/grading/{spec,exact_match,executable,judge}.py`
- **Non-goals honored:** `engine/harness/*` (Scope 5); tasks↔expected content drift (Seam auditor). Docker and LLM calls: not executed. Static read + offline `python3` probes only.
- **Health score:** **4.5 / 10 (Critical band, <7)** — two Critical security findings in the sandbox boundary; the rest of the scope (timeouts, try/finally in `run_one`, selfcheck coverage, raw_api containment) is otherwise solid.

Severity distribution: **2 Critical · 5 Moderate · 5 Minor**

---

## Critical

### F-01 — Seed-file `# path` headers escape the sandbox: arbitrary host file write (proven)

- **Location:** `engine/sandbox.py:64-67` (`write_file_to`), reachable from `engine/sandbox.py:52-53` (`create` ← task md `## Environment/setup`, `engine/task.py:35-37`) and `engine/grading/executable.py:18-19` (expected md `## Held-out test suite`, executed *after* the agent has run). Filename extraction: `engine/markdown.py:12` (`^#\s*(\S+\.\w+)`).
- **Mechanism:** `target = base / rel_path` with **no `resolve()` check and no `is_relative_to` guard**. Python's `Path.__truediv__` discards `base` entirely when `rel_path` is absolute, and the kernel collapses `..` at `open()` time. The seed regex happily captures both: `# ../escaped.txt` → filename `../escaped.txt`; `# /tmp/x/evil.sh` → the absolute token itself (it needs only one `.`+word segment somewhere near the end). `mkdir(parents=True, exist_ok=True)` then creates the outside directory tree before writing.
- **Proof (benign local probe, this machine, no docker):**
  ```
  HEADER='# ../escaped.txt'                 filename='../escaped.txt'
    resolved=/tmp/escaped.txt  outside base? True  result=WROTE   (file existed; removed after)
  HEADER='# /tmp/…-ESCAPE/target.txt'       resolved==joined, outside base? True  result=WROTE
  HEADER='# ../../../../tmp/…/target.txt'   resolved outside base? True  result=WROTE
  ```
  A fourth variant (deep traversal ending `/.ssh`) resolves to `…/.ssh`, showing directory-creation and write both land wherever the benchmark user (`devhax`) has permission.
- **Aggravating factor — agent-side pivot:** even without any malicious task md, `executable.grade` writes held-out files into `sb.workdir` *after* the agent ran arbitrary bash inside a container whose `/workspace` is that same workdir (mounted **rw**, `engine/sandbox.py:80-82`). Agent code can leave a symlink (e.g. `test_paginate.py -> /home/devhax/.ssh/authorized_keys`) and the trusted grading seed is written *through* it (`write_text` follows symlinks; `mkdir(exist_ok=True)` on a symlinked parent also traverses). This scope already implements the correct guard elsewhere — `raw_api._resolve_in_sandbox` (`engine/harness/raw_api.py:62-66`, resolve + `is_relative_to`) — proving the omission in `write_file_to` is unintentional, not a design choice.
- **Fix:** route `write_file_to` through the same `_resolve_in_sandbox` logic (reject absolute paths, reject post-resolve escape, and use `os.open(..., O_NOFOLLOW)` / `Path.open("wx")` after an `lstat` check for the symlink pivot); optionally additionally restrict the seed regex to `^# ([A-Za-z0-9._/-]+\.\w+)$` rejecting any component equal to `..`.

### F-02 — Credential mounts expose host auth to agent-authored bash; `.gemini` writable without justification; network egress unrestricted

- **Location:** `engine/sandbox.py:20-37` (`CREDENTIAL_MOUNTS`, `RW_MOUNTS`), `engine/sandbox.py:86-90` (mount loop), absence of `--network`/`--read-only` in `_docker_run_args` (`engine/sandbox.py:74-95`). Image runs unprivileged (`docker/harness-base.Dockerfile:43` `USER ubuntu`), default bridge network.
- **Mechanism:** every `docker run` bind-mounts the host's `~/.claude`, `~/.claude.json`, `~/.gemini`, `~/.config/opencode`, `~/.codex`, `~/.pi/agent` at `/home/ubuntu/…` **into the same container that executes model-generated bash** (task setup scripts, the check scripts via `executable.grade`, and raw_api's `bash` tool). `:ro` prevents writes, not reads — every provider credential/token in those dirs is readable by untrusted code, and there is **no `--network none`/egress restriction**, so reading alone is sufficient for exfiltration. Worse, `RW_MOUNTS = {".pi/agent", ".gemini"}` (`:37`) makes two credential trees **host-writable from inside the container**: the in-code justification at `:22-26` is pi-specific ("pi reads/writes auth … session locks"); nothing in the comment explains why `.gemini` needs write access, so its rw flag contradicts the stated design line "Everything else stays read-only" (`:26`). An agent that writes into the mounted `~/.pi/agent` settings/model-registry (or `~/.gemini` oauth store) pivots the *host's* harness logins — full escape of the isolation boundary the module's docstring promises.
- **Related (informational):** the `-e KEY=VAL` passthrough (`sandbox.py:91-93`) would put secret values in `docker inspect` config and host `ps` argv. Today it is inert — `Sandbox.container_env` is populated only via `create(env=...)` and **no caller in `engine/cli.py`/`selfsolve.py` ever passes env** — but the mechanism should be switched to `--env-file` with a tmpfs-removed-after-start file if it is ever used.
- **Fix:** (1) drop `.gemini` from `RW_MOUNTS` unless a concrete lock-file need is documented; (2) mount a throwaway copy of only the specific auth files each CLI harness needs, not whole credential trees; (3) add `--network none` for setup/check phases (harnesses needing API egress are the only phase that should get a network, ideally via a proxy without host creds in-mount); (4) add `--read-only --tmpfs /tmp` for the agent-execution phases.

---

## Moderate

### F-03 — Invariant 2 breach: LLM judges are decommissioned but `judge-ensemble` remains fully dispatchable

- **Exact code path:** `engine/grading/spec.py:36-37` (`if "judge" in m: return "judge-ensemble"`) → `engine/cli.py:18` (import) → `engine/cli.py:32` (`GRADERS["judge-ensemble"] = … judge_grade.grade(spec, text)`) → `engine/cli.py:73` (`passed = GRADERS[spec.method](…)`) → `engine/grading/judge.py:grade` fires live CLI-harness LLM calls (`judge.py:_fetch_response` → `cli_adapter.run_host_text`). Second dispatch site: `engine/selfsolve.py:41-42`. The CLI additionally *maintains* the feature: `engine/cli.py:112-115` (mutates `JUDGE_HARNESS`/`JUDGE_MODEL` module globals) and `engine/cli.py:181-191` (`--judge-harness`/`--judge-model` flags with defaults read from the still-live env vars `BENCH_JUDGE_HARNESS`/`BENCH_JUDGE_MODEL`).
- **Current exposure:** verified all 20 `expected/**/*.md` "grading method" lines — none classify to judge (all contain "unit test"/"state check"/"exact match", matched first). So the breach is **latent, not firing on today's corpus** — but any new/renamed method string containing the substring "judge" (e.g. a future label "deterministic check (not judge)") silently routes to a 3× N_JUDGES live-LLM grading path (substring precedence at `spec.py:30-37` only protects labels that happen to include one of the three executable keywords).
- **Fix:** delete `GRADERS["judge-ensemble"]`, the `--judge-*` flags, `cli.py:112-115`, `selfsolve.py:41-42`, and make `_classify_method` raise on "judge" instead of returning; archive `judge.py` or gate it behind an explicit opt-out reversal.

### F-04 — `subprocess` timeout kills the `docker run` client, not the container: orphaned unbounded execution with credential mounts

- **Location:** `engine/sandbox.py:106-116`.
- **Mechanism:** `subprocess.run(..., timeout=…)` SIGKILLs the local `docker` CLI on expiry. Killing the client does **not** stop the daemon-side container; `--rm` only fires when the container eventually exits. The synthetic returncode-124 record returns control to the caller, `run_one` proceeds to grading (against a still-running agent process mutating `/workspace`) and then `cleanup()` `rmtree`s the host workdir — while the orphan container keeps running **indefinitely, with network egress and the F-02 credential mounts live**. A harness designed to hang (or an infinite-loop exfiltration payload) therefore escapes all time bounding.
- **Fix:** on `TimeoutExpired`, best-effort `docker ps -q --filter …`/track the container id (`--cidfile` in a per-run tmp) and `docker kill` it before returning the 124 result.

### F-05 — Infrastructure failures are recorded as model "fail", poisoning results.jsonl

- **Location:** `engine/grading/executable.py:22-24` (`passed = proc.returncode == 0`); `engine/cli.py:71-73` (grading result consumed with no infra distinction).
- **Mechanism:** if the docker daemon is down, the image is missing, or the container fails to start, `docker run` exits 125/126 — indistinguishable, under this code, from "tests failed". For tasks with a setup script, `create` raises (`sandbox.py:56-59`) and the run errors out (no record). For the far more common no-setup tasks, `create` never touches docker, the harness invocation surfaces a nonzero exit… but grading runs `exec_in` → rc 125 → `passed=False` → a clean-looking `"fail"` **RunRecord is appended** (`cli.py:88`). A daemon outage mid-suite silently writes up to 20×trials bogus failures instead of zero-count errors, and `score`/`report` blend them with real results. (Contrast: the timeout path at `sandbox.py:108-116` is deliberately treated as a data point — that's documented; daemon-down is not.)
- **Fix:** treat container-launch failures as errors: raise (skip the record) when rc ∈ {125} or stderr matches docker client errors, or capture `CompletedProcess` stderr in `ExecResult` and refuse to grade on infra exit codes.

### F-06 — `engine run` always exits 0 and writes nothing on failure; parallel wrapper cannot detect a dead batch

- **Location:** `engine/cli.py:132-138` (per-future `except Exception: print(...); continue`), `engine/cli.py:218-219` (`main` returns 0 unconditionally). Confirmed consumer: `run_suite_parallel.sh:36-42,47` backgrounds each `engine run` under `wait` and proceeds to `engine report` regardless.
- **Mechanism:** every per-run failure (bad task file, docker missing, harness crash) is printed to stdout but produces **no RunRecord and no nonzero exit**. A run where 100% of trials error still exits 0, and the suite script prints "✅ Done!" over an empty/partial results set. `selfsolve` gets this right (`selfsolve.py:96-97` `sys.exit(1)`); `run` should match: track error count and exit nonzero (and ideally record a `"error"` result row, since `RunRecord.result` already documents `pass | fail | partial` extensibility).

### F-07 — Invariant 3 tagging is written but discarded at aggregation: `harness_version` merged across versions

- **Location:** `engine/report.py:8` (`GROUP_KEYS = ("task_id","model","harness","tool_access")` — `harness_version` missing); `engine/score.py:49` (`data[harness][model][task_id]` — both `harness_version` and `tool_access` dropped).
- **Mechanism:** invariant 3's five fields *are* structurally enforced on write (`cli.py:76-92` builds a `RunRecord` whose dataclass requires model/harness/harness_version/tool_access/trial_number — `results.py:11-31`; append covers all records; N≥3 is driven by `TRIALS=3` in `run_suite_parallel.sh:16` and the "2/3 passes" scoring note in `score.py:88`). But a `pi-agent` harness version bump (cli_adapter updates `harness_version`) mid-suite silently pools old- and new-version trials into one `pass_rate` — the exact scenario `results.py:30-31`'s `schema_version` comment anticipates ("lets runs.jsonl mix shapes across time"). Re-running the same (task, trial) number compounds: the journal treats reruns as extra trials, not corrections.
- **Fix:** add `harness_version` to `GROUP_KEYS`; group score.py's buckets by (harness, harness_version, model, tool_access, task_id) or dedupe by `trial_number` (keep last) before aggregating.

---

## Minor

### F-08 — Tempdir leaks on setup failure and in `verify`
`create()` `mkdtemp`s at `sandbox.py:51`; a raising seed write (`:52-53`) or setup failure (`:57-59`) leaks the dir — `run_one`'s `finally` (`cli.py:74-75`) can't fire because `sb` was never assigned, and `cmd_selfsolve`'s loop keeps going, one leaked `/tmp/llm-bench-*` per failed task. `cmd_verify` (`cli.py:155`) creates a sandbox and never cleans up at all (called once per harness by `run_suite_parallel.sh:25`). Fix: `tmp` → `try/except: rmtree; raise` in `create`; `finally: cleanup(sb)` in `cmd_verify`.

### F-09 — markdown parser CRLF behavior: silent seed loss, hard setup failure
`_FENCE_RE` (`markdown.py:11`) requires `\n` immediately after the info string, so with CRLF input the captured language is `bash\r` and the match fails. Consequences differ by call site and one is silent: CRLF `## Environment/setup` → `extract_section` succeeds, `extract_seed_files` returns `[]`, and the guard at `task.py:43-44` doesn't fire (its `env_section` condition is `not env_section` — a non-empty body disables the check) → **task runs with zero seeded files, no error**. CRLF `## Setup` → loud `ValueError` at `task.py:42-43`. Also `first_bash_block` accepts `lang == ""` (`markdown.py:70`), so any *unlabeled* prose fence in `## Setup`/`## Check` is executed as bash ahead of the real one; and a 4-backtick outer fence truncates at the first inner ``` (probe: body became `` '```bash\nnot-a-script' ``). No repo file currently uses CRLF or 4-tick fences — latent. Fix: normalize `text.replace("\r\n","\n")` at parse entry points; anchor `_FENCE_RE` with `^`/`re.escape`-safe fence-length handling (CommonMark: closing fence length ≥ opening).

### F-10 — `parse_task` accepts empty required fields
`task.py:30-32` defaults `dimensions`/`difficulty`/`instruction` to `""` with no validation. A task missing its `## Instruction` heading runs the full harness pipeline with a blank prompt and records a real `"fail"` — data-integrity hole the Setup/Env guards (`task.py:42-44`) were written to prevent for other sections. Fix: raise when `instruction` is empty.

### F-11 — One torn line bricks `report` and `score`
`results.py:44-46` and `score.py:45-49` `json.loads` every line with no error tolerance. The append itself is safe as used (`results.py:34-37`, single <8 KB write, `O_APPEND`), but a kill/disk-full mid-append leaves a partial line that makes `engine report` and `engine score` crash entirely — inconsistent with the batch-survives-errors philosophy of `cmd_run`. Fix: skip-and-warn on `JSONDecodeError` in the loaders.

### F-12 — Seed filenames must end in a dotted extension
`_SEED_FILE_FIRSTLINE_RE` (`markdown.py:12`) requires `\.\w+`, so valid seeds like `# LICENSE`, `# Makefile`, `# Dockerfile` are **silently dropped** (no guard catches it). Authoring trap; fix by making the extension optional and anchoring the whole line: `^#\s*(\S+)$` subject to the F-01 sanitizer.

### F-13 — `verify` prints raw harness failure output
`cli.py:163` embeds `res.response_text` in the error; for a failing logged-in CLI this can surface token fragments in logs. Cosmetic relative to F-02.

---

## Invariant verdicts (this scope)

- **Invariant 2 (judges decommissioned): BREACHED (latent)** — full dispatch chain live; see F-03 for the exact lines. Not firing on the current 20 expected specs (verified all "grading method" lines).
- **Invariant 3 (model+harness+harness_version+tool_access+trial_number on every RunRecord; pass_rate from N≥3): write-side holds** (dataclass-enforced in `cli.run_one`; N=3 default via `run_suite_parallel.sh`), **read-side weak**: `harness_version` excluded from `report.py` grouping and both it and `tool_access` from `score.py` — F-07.
- Sandbox-isolation invariant: **breached** via F-01/F-02 (host-write primitive + credential-mount escape surface).

## Verification log (offline, no docker, no LLM)

1. `python3` probe importing `engine.markdown`/`engine.sandbox`: `write_file_to(mktemp_base, "../escaped.txt")` and two absolute/deep-traversal variants extracted through the *real* seed regex → all resolved outside the base, all performed the write (files created; cleaned up after). Proves F-01.
2. CRLF + nested-fence probe on `extract_section`/`first_bash_block`/`extract_fenced_blocks` → F-09 behaviors reproduced exactly as described.
3. Read-only survey: all 20 `expected/**` method strings → none classify to judge-ensemble today (F-03 exposure stated correctly).
4. Caller grep: no call site ever passes `env=` to `sandbox.create` (F-02 env-vector stated as inert mechanism, not live leak); `raw_api._resolve_in_sandbox` confirmed as the repo's existing containment idiom (grounding F-01 "unintentional" verdict).
5. `git status`: dirty files are all `checkers/` + `docs/data/` — zero overlap with this scope; audited on-disk state.

## P1 backlog (fix next cycle, ordered)

1. F-01 — apply `_resolve_in_sandbox` guard + `O_NOFOLLOW` in `sandbox.write_file_to` (both seed paths and grading-seed writes).
2. F-02 — remove `.gemini` from `RW_MOUNTS`; add `--network none` to setup/check phases.
3. F-03 — cut the judge dispatch path (invariant 2 closure).
4. F-04 — docker-kill on client timeout.
5. F-05 — distinguish infra exit codes from grading failures before writing a RunRecord.

## P2 backlog

6. F-06 — nonzero exit + error records for `engine run`; F-07 — `harness_version` in aggregation keys.
7. F-08 tempdir-leak `finally`s; F-09 CRLF normalization + unlabeled-fence strictness; F-10 instruction validation; F-11 malformed-line tolerance; F-12 seed-name regex relaxation with sanitizer.

## Summary

The engine's orchestration skeleton is careful — per-command timeouts everywhere, `finally`-cleanup in the hot path, a selfcheck suite that deliberately tests path containment *in raw_api*, and honest `ponytail:` annotations. But the containment discipline stops at the module boundary: `sandbox.write_file_to` — the one function that writes model/task-controlled paths on the host — lacks the guard its sibling already implements, which the probe shows is an arbitrary-file-write primitive, and the docker wrapper's credential-mount policy makes that write land next to every provider login on the box. Close F-01 and F-02 before treating any agent-generated task content as safe, and retire the still-wired judge path (F-03) to match stated policy.
