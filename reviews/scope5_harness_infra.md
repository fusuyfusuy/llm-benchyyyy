# Scope 5 — Harness Adapters & Infra Audit

- **Auditor:** Scope5HarnessInfra
- **Date:** 2026-08-30
- **Files audited:** `engine/harness/configs.py`, `engine/harness/cli_adapter.py`, `engine/harness/raw_api.py`, `engine/pricing.py`, `docker/harness-base.Dockerfile`, `run_benchmarks.sh`, `run_suite_parallel.sh`, `pyproject.toml`, `.gitignore`, `engine/__main__.py` (consumption traced into `engine/cli.py`, `engine/sandbox.py`, `engine/results.py`, `engine/report.py` — verdicts on those internals belong to Scope 4 / Seam auditor; only adapter-facing consequences are scored here).
- **Method:** full read of all in-scope files + on-disk state; offline read-only probes (pasted in §6); no edits made; docker not required — argv/mount construction analyzed statically, unexecutable claims labeled `[INFERENCE]`.
- **Note:** `local://audit-context.md` and `local://boundary-review-plan.md` were not present at read time; format follows the fallback instructions in the assignment brief (rubric bands Critical <7 / Moderate 7.0–8.4 / Minor 8.5–9.4 / Exemplary 9.5–10; health score + severity counts + top findings + P1 backlog).

## Verdict

**Health score: 5.5 / 10 (Critical band)** — the adapter layer is architecturally sound (generic field-map design, shlex-quoting, fail-loud on *response* parse) and invariant 5 (non-root uid-1000 container) and invariant 6 (results/keys never committed) both verify clean. But one **confirmed Critical data-integrity defect is active in the live dataset right now** (null cost coerced to $0.00 on every antigravity group — 21 of 21 aggregated groups report `total_cost_usd=0`, proven against `results/runs.jsonl` in §6.3), and three systemic loudness gaps (exit-0-on-all-error, `wait` masking, host-side version capture) mean the *first live codex-cli run* — the project's own top open epic — will fail in a way no automation can detect.

**Severity counts: Critical 1 · Moderate 7 · Minor 4**

---

## Findings

### CRIT-1 — Null usage/cost is silently coerced to $0 in the report; adapter only fails loud on the *response* path, never on configured metric paths — **Critical, P1**

**Chain (file:line):**
1. `engine/harness/cli_adapter.py:158-161` (single-json) and the `_find_last` results at `:189-192` (jsonl non-sum): a *configured* `input_tokens_path`/`output_tokens_path`/`cost_path` that misses the actual JSON yields `None` with zero diagnostics — contrast `:152-155`/`:172-175`, where a missing *response* path raises `RuntimeError`. The asymmetry is the bug: the field-map's most drift-prone keys (usage/cost; `codex-cli`'s entire map is docs-derived and unverified live per `.mimori/memory.md:5-8`) fail silently, while the least drift-prone fails loud.
2. `engine/cli.py:66-68`: `cost = hr.cost_usd`; the pricing fallback fires only `if model in pricing.PRICING_PER_MTOK` — never for Gemini/OpenAI models, so antigravity/codex runs keep `cost_usd=None`.
3. `engine/report.py:37`: `total_cost = sum(r.get("cost_usd") or 0 for r in rs)` — `None` becomes 0, and the report cannot distinguish "free run" from "unpriced run".

**Failure mechanism & impact (observed, not hypothetical):** every antigravity row in the live dataset has `cost_usd=null` (`configs.py:70` sets `cost_path=None`); §6.3 paste shows all 21 antigravity aggregated groups with `total_cost_usd=0` and passing groups with `cost_per_success_usd=0.0`. The benchmark's dimension-4 headline ("$ per successful task", `scope.md:15-17`, and cost-per-success comparability) is reporting genuine spend as **$0.00** for the harnesses with the most real passes. Same corruption shape will hit claude-code/pi-agent the first time a CLI renames a usage key: run scores normally, tokens/cost null.

**Fix (discrete):**
- In `_extract_fields`, for each of `input_tokens_path`/`output_tokens_path`/`cost_path` that is non-`None` in the config, raise (or emit a one-time loud warning + `bench:` stderr line) when extraction returns `None` on an otherwise-successful parse — mirror the response-path rule.
- `configs.py:58,70`: give codex/antigravity a `cost_path` derived from their real JSON (they are live-verified per `configs.py:7-9` except codex), or document the harness as *unpriceable* and have `report.aggregate` count null-cost rows per group and render `"- (N unpriced)"` instead of `$0`.

### MOD-1 — `engine run` exits 0 when *every* trial errors; errored trials produce no record and no error count — **Moderate, P1**

`engine/cli.py:126-135`: each future's exception is printed and `continue`d; `main()` (`cli.py:213-219`) always returns 0. Nothing in the pipeline distinguishes "3/3 trials graded" from "0/3 trials ran, all errored" — `results/runs.jsonl` simply has fewer rows. **Live proof** (§6.2): `python3 -m engine run --task … --harness raw-api --trials 1` → `ERROR: ModuleNotFoundError: No module named 'anthropic'` printed, **EXIT_CODE=0**, zero rows appended. This is the exact future shape of the codex-cli first-run (docs-derived map raises `RuntimeError` on every trial, `cli_adapter.py:164-170`) and also silently swallowed the partial antigravity data (§6.3 shows `trials=2` and `trials=1` groups — dropped errored trials are invisible and violate the N≥3 invariant, `scope.md:110`).
**Fix:** count errors in `cmd_run`; write an `result="error"` RunRecord (or a sidecar `errors.jsonl`); exit non-zero when `errors > 0` (or `> X%`); report.aggregate should flag groups with `trials < 3`.

### MOD-2 — `run_suite_parallel.sh` masks all parallel-run failures via bare `wait`; no `set -u`/`pipefail` — **Moderate, P1**

`run_suite_parallel.sh:31-36` backgrounds each `python3 -m engine run` (so `set -e` at `:2` can never see it fail — `set -e` doesn't apply to async jobs), and `:40` `wait` with no operands returns **0** unconditionally; the script then prints "📊 All runs finished" and generates the report (`:42-43`) even if every harness process died. Combined with MOD-1's exit-0, a fully-failed multi-harness suite is a green, complete-looking run. Also: `:2` lacks `set -u -o pipefail` (harmless today — no pipes, all `$#`/`$?` guarded — but the unquoted-`for arg in "$@"`/`"$harness"`/`"$model"` expansion discipline at `:19-35` is otherwise correct); `:20` `IFS=':' read -r harness model` silently accepts `a:b:c` (model keeps `b:c` — arguably desirable for provider-scoped ids; note only). The `verify` gate at `:23-26` is the one loud spot (correctly `exit 1` — `cmd_verify` does `sys.exit(1)` at `cli.py:167`).
**Fix:** collect PIDs (`pids+=($!)`), then `rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; exit $rc` before the report step.

### MOD-3 — `harness_version` is captured on the **host**, while harnesses execute inside the container; fallback to bare harness name is silent — **Moderate, P1**

`cli_adapter.py:22-38` runs `config.version_argv` via plain `subprocess.run` (host `PATH`), but `run()` (`:200-206`) executes the CLI via `sandbox_mod.run` → `docker run … BASE_IMAGE` (`sandbox.py:74-95`). Invariant 3 / `metrics.md:12-13` demand the version of *what actually ran*; today the record attributes the container run to the host binary. Two concrete consequences:
- `codex` is **not installed on this host** (§6.1 probe: `codex: MISSING`) while it *is* installed in the image (`Dockerfile:31`), so every codex run's `OSError` is swallowed at `cli_adapter.py:34-35` and `harness_version` records the bare string `"codex-cli"` — an "unpinned version", which `metrics.md:13` declares invalidating, silently.
- The image installs CLIs at *latest* (MOD-5), so host↔container versions drift in exactly the direction the drift-detection was supposed to catch. Today's data (§6.3) shows real versions (`0.84.2`, `1.1.19`, `2.1.241 (Claude Code)`) only because the host happens to carry matching CLIs — luck, not design.
**Fix:** capture version inside the sandbox once per run (`sandbox_mod.exec_in(sb, shlex.join(version_argv))` in `run()`, still cached per image), and raise/warn when falling back to the bare name.

### MOD-4 — Adapter ignores `proc.returncode`: timed-out (124) or crashed harnesses still produce scored records with truncated JSONL and incomplete per-turn sums — **Moderate, P2**

`sandbox.py:98-115` deliberately converts `subprocess.TimeoutExpired` into a `CompletedProcess(returncode=124)` carrying *partial* stdout; `_parse_jsonl` (`cli_adapter.py:72-84`) silently drops the truncated final line (`:79-80`); `_extract_fields` only inspects `returncode` to decorate error messages when *no* events parsed (`:164-168`). So a pi/opencode run that times out or crashes after emitting ≥1 event: `response_text` = last complete event (may be an intermediate turn), `_sum_metrics` (`:121-138`) sums only the turns that completed → **undercounted tokens/cost on a record indistinguishable from a clean run** (grading likely fails it, but the trial's cost/time feed `cost_per_trial_usd` and `total_cost_usd` at `report.py:38,50-54`). `HarnessRunResult.raw_exit_code` (`cli_adapter.py:49,217`) is captured then **discarded** — `RunRecord` has no exit-code field (`results.py:11-31`), so the 124 convention dies at the adapter boundary.
**Fix:** in `cli_adapter.run` (`:205-207`), raise when `proc.returncode != 0` *before* extracting (or record `exit_code` in `RunRecord` and let the grader/report decide); at minimum treat 124 as a hard error for metrics purposes.

### MOD-5 — Dockerfile installs all 5 CLI harnesses unpinned at build-time-latest, contradicting its own "image must match host" comment — **Moderate, P2**

`docker/harness-base.Dockerfile:30,31,35` (`npm install -g @anthropic-ai/claude-code` / `@openai/codex` / `@earendil-works/pi-coding-agent`) and `:50-51` (unpinned `curl … | bash` installers). `.mimori/memory.md:42-43`: pi is `@earendil-works` fork, "host runs 0.84.x … image must match host" — but nothing enforces that; the next `docker build` after an upstream release silently benchmarks a different pi/opencode/claude than every historical run, and combined with MOD-3 (host-side version capture) the recorded version may even *disagree* with what ran. Correctness-of-attribution issue, not availability.
**Fix:** pin exact versions (`@earendil-works/pi-coding-agent@0.84.2` etc.) or fail the build on mismatch with `ARG PI_VERSION` inputs; the `verify` command then becomes meaningful per rebuild.

### MOD-6 — Read-write bind-mounts of host credential dirs contradict the "mounted read-only" ADR and create a model→host code-exec vector via pi's auto-installed extension packages — **Moderate (security), P1/P2**

Exact container-intrusion surface (all model-controlled commands run in this container with network egress unrestricted and, for claude-code/antigravity, `--dangerously-skip-permissions` per `configs.py:39,65`):
- `sandbox.py:27-34` `CREDENTIAL_MOUNTS` = `~/.claude`, `~/.claude.json`, `~/.gemini`, `~/.config/opencode`, `~/.codex`, `~/.pi/agent`; mounted at `:81-84` — **`RW_MOUNTS = {".pi/agent", ".gemini"}` (`:37`) are writable *on the host***.
- Env-var surface: **none today** — `create()` is called without `env` at `cli.py:47` and `selfsolve.py:34`, `extra_env` is never passed by any caller (grep in §6.4), so the `-e` loop at `sandbox.py:85-88` carries zero secrets; `ANTHROPIC_API_KEY` is consumed only host-side by the SDK (`raw_api.py:93`) and never crosses. Note for the future: `-e f"{k}={v}"` puts values in the host-visible `docker` argv (`/proc/*/cmdline`) if anyone ever uses it.
- The secrets that *do* cross are the OAuth/token files in the six mounted paths — a model can `cat /home/ubuntu/.claude/.credentials.json` and exfiltrate over the (necessarily open) network. That half is the documented ADR tradeoff ("bind-mounting host's own CLI config dirs read-only, not reimplementing auth", `.mimori/memory.md:31-32`, ADR 2026-08-19).
- The **undeclared** half: `.pi/agent` is rw and `.mimori/memory.md:47-49` documents that pi's `settings.json` `packages` list "makes pi auto-install extensions at startup" and the container reuses host `~/.pi/agent/npm/node_modules`. So a model-controlled `bash` tool call can rewrite host `~/.pi/agent/settings.json` → arbitrary code executed **on the host** at the next host pi launch. `.gemini` rw has no justification comment at all (the rw rationale written at `sandbox.py:20-26` covers pi only; even pi needs rw only for `settings.json.lock`/cache).
**Fix:** keep `.pi/agent` rw only via a throwaway overlay (copy auth/models-store into a fresh temp dir seeded per run, discard after); drop `.gemini` from `RW_MOUNTS` unless proven necessary; the ADR text and the mount table must agree.

### MOD-7 — `raw_api.run`: no timeout/retry/exception path on the Anthropic SDK, unbounded loop wall-clock, all mid-run spend lost on API error — **Moderate, P2**

`raw_api.py:102-106`: `client.messages.create(...)` — no `timeout=`, no `max_retries=`, no `try/except`. `[INFERENCE]` the SDK's defaults (600 s read timeout, 2 retries for 429/5xx) apply — the installed `anthropic` package could not be inspected to confirm because it is **absent from the interpreter** (§6.2), which is itself the MOD-1 trigger. Consequences from the code that *is* provable: (a) worst case 20 turns × 3 attempts × 600 s ≈ unbounded relative to the 600 s `timeout_seconds` every CLI harness gets (`configs.py:28`) — `run_one` applies no wall-clock cap on the raw-api branch (`cli.py:49-57`); (b) any `APIStatusError` (overloaded, auth expiry mid-suite) propagates → the whole trial's accumulated tokens/$ (potentially 19 billed turns) produce **no record** (MOD-1 drops it silently); (c) no `stop_reason == "max_tokens"` handling — a tool_use truncated at the token cap yields a partial `input` dict, so `tool_input["command"]` / `["path"]` at `raw_api.py:71,74-75` can `KeyError` and kill the run mid-billed `[INFERENCE — SDK partial-block semantics not live-verifiable here]`; (d) the read/write tools (`raw_api.py:74-86`) execute on the **host** fs via `sb.workdir` (not `exec_in`): confined by the `_resolve_in_sandbox` guard (`:62-66`, correctly defeats `..`, absolute-path rebinding, and symlink-escape via `resolve()`+`is_relative_to` — verified by reasoning, `PermissionError ⊂ OSError` is caught at `:76,81`), so the *isolation* answer for the brief is: **bash = container (`:71` via `exec_in`), read/write = host-side writes into the bind-mounted workdir, escape-blocked** — equivalent for data but a different failure domain (host uid-1000 writes, `mkdir -p` outside the container lifecycle; uid matches at 1000, §6.1, so no permission skew).
**Fix:** pass explicit `timeout=`/`max_retries=`, wrap the create() call to return a partial `RawApiResult` (tokens billed so far, `result="error"`) instead of raising; check `resp.stop_reason` and a truncated `tool_use` before indexing `tu.input`; route read/write through `exec_in` for domain-consistency or keep the guard and say so in the docstring.

### MIN-1 — `cached_tokens` is permanently `None` in every record; `tool_call_count` is a `num_turns` proxy for two harnesses — **Minor, P2**

`cli.py:91` hardcodes `cached_tokens=None`; `report` shows zero non-null rows (§6.3). `metrics.md:34-35` explicitly says cached-token counts "should not be hidden" because prompt caching materially changes $/task — claude-code's own JSON `usage` block reports them and pi/opencode equivalents exist, but no `HarnessConfig` field can express them (schema gap in `configs.py:17-34`). Separately `configs.py:46,71` set `tool_call_count_path=["num_turns"]` for claude-code/antigravity — `metrics.md:38-39` defines tool_call_count as tool *invocations* (thrash detector); turns ≠ calls, so a 1-turn-10-tool-call run scores as 1.
**Fix:** add `cached_input_tokens_path`/`cache_creation_tokens_path` to `HarnessConfig`, plumb through `run()` into the record; rename or dual-report the proxy (`turn_count`) instead of silently overloading `tool_call_count`.

### MIN-2 — `bench` legacy script alias; `anthropic>=0.40` unpinned and not installed in the runtime interpreter — **Minor, P2**

`pyproject.toml:11` keeps `bench = "engine.cli:main"` as a pure legacy alias — violates the project's no-back-compat rule (one canonical entry point at `:10`); several repo docs (`judge.py:4` "no API key needed", ADR wording) also still reference `bench …` invocations, which is why the alias lingered — deleting the alias requires those string updates. `:6` `anthropic>=0.40` has no ceiling and the module is absent from `python3` 3.14.4 (§6.2), i.e. the declared dependency has never actually resolved in the interpreter that `run_benchmarks.sh`/`run_suite_parallel.sh` invoke — raw-api is 100% broken today, loudly per-trial (stderr), silently in exit code (MOD-1).

### MIN-3 — Decommissioned judge-ensemble subsystem still dispatchable; `run_host_text` docstring anchors to it — **Minor, P2**

Invariant: "NO LLM JUDGES ALLOWED … decommissioned" (`.mimori/memory.md:24-26`). Yet `cli.py:32` still routes `"judge-ensemble"` to `grading/judge.py`, `spec.py:36-37` auto-maps *any* method string containing "judge" to it, and `cli.py:181-192` exposes `--judge-harness`/`--judge-model`. `run_host_text` (`cli_adapter.py:221-235`, my file) exists for that path and would execute the harness CLI's full argv — including `claude --dangerously-skip-permissions` (`configs.py:39`) — **unsandboxed on the host**, on a prompt embedding the system-under-test's response text (a prompt-injection-to-host-shell channel if ever re-enabled). Probed: **no `expected/` task uses judge grading** (§6.5 — every method line says unit test/state check/exact match, several literally "(executable, not judge)"). Dead but one-flag-and-one-task-file away from live.
**Fix (clean cutover per project rules):** delete `run_host_text`, the `judge-ensemble` GRADERS entry, the CLI flags, and `grading/judge.py`; make `spec.py` raise on "judge".

### MIN-4 — `pricing._DEFAULT_RATES` silently misprices any unknown model id; batch tier never represented — **Minor, P3**

`pricing.py:15,21`: an unrecognized id (typo'd `claude-opus-5-20260115` — the exact class of error `.mimori/memory.md:37-39` says was caught live once) silently prices an opus run at Sonnet rates ($3/$15 vs $15/$75 — 5× underreport). Units themselves verify correct: table is $/MTok, divisor is `1_000_000` (`:21-22`), no /1k mixup; haiku's dated id is its real slug, not the banned-date-suffix case. `metrics.md:36-37` also wants the pricing tier (batch vs realtime) noted per record — no such field exists anywhere.
**Fix:** `cost_usd` should return `None` (or raise) for unknown models rather than defaulting, letting the null path (see CRIT-1 fix) surface it; add `pricing_tier` to `RunRecord` if batch is ever used.

---

## Checks that PASSED (no finding)

- **argv quoting / injection:** `configs.py` templates are `list[str]`, `{prompt}` substituted as a whole token and every arg `shlex.quote`d into the `bash -lc` string (`cli_adapter.py:97-101,202-203,226`); model substitution equally quoted. No word-splitting or injection path from prompt/model text. Unresolved-placeholder check: every config with a `model_flag` uses `{model}` and every `command` uses `{prompt}` exactly once (`configs.py:37-109`) — consistent.
- **pi multi-turn SUM invariant:** `PI_AGENT.sum_usage_event_types=("message_end",)` (`configs.py:89`) correctly wires `_sum_metrics`, bool-guarded, zero-contribution from usage-less user/toolResult events — matches the live-verified memory gotcha (`memory.md:50-52`). Non-summed `last-wins` for codex/others is the documented convention.
- **Invariant 5:** `Dockerfile:43-44` `USER ubuntu` before any `--dangerously-skip-permissions`-requiring run; host uid=1000 matches (§6.1). No root+skip-permissions combo exists. No `COPY`/`ARG` of secrets in the image.
- **Invariant 6 / `.gitignore`:** probe-verified (§6.6): `results/` blanket + `!results/.gitkeep`, `.env`, `.env.*`, `*.pem`, `*.key`, `credentials*` all match; `git ls-files results/` → only `.gitkeep`; `git log --diff-filter=A -- results/*` → nothing besides `.gitkeep` ever committed. Repo is public; history is clean.
- **Concurrent appends:** `results.py:34-37` opens append-mode and issues one small buffered write per record; same-process threads (`--jobs`) are GIL-serialized, and multi-process `run_suite_parallel.sh` appends to one `runs.jsonl` rely on O_APPEND single-`write()` atomicity — holds on local fs for sub-8 KiB lines (records are ~300 B), with no flock. `load_all` (`results.py:40-44`) has no malformed-line tolerance, so a torn line on NFS/oversized-record would hard-crash `report`/`score`. Watch-list item, not scored (no reproducible corruption on this fs).
- **`run_benchmarks.sh`:** sequential under `set -e` — python failures do abort the chain (unlike the parallel script); no unquoted expansions; missing `set -u/pipefail` is inert with zero variables/pipes. Neither script preflights docker/network; MOD-1/MOD-2 already own the failure-masking consequence, and per-`docker run` absence produces loud per-trial errors + exit 0 — folded into MOD-1.
- **`pricing.py` units:** $/MTok consistently, math verified (§MIN-4).

## Invariant breaches summary

| Invariant | Status |
|---|---|
| 3 — every run tagged harness_version, pinned versions valid | **Breached in mechanism** (MOD-3: host capture; codex → bare name silently) |
| 5 — non-root uid-1000 container, no skip-permissions+root | Honored (Dockerfile:43, probe §6.1) |
| 6 — results/ + keys never committed | Honored (probe §6.6) |
| NO LLM JUDGES | **Breached in surface** (MIN-3: dispatchable, flags live; no task uses it) |
| Cost/metrics completeness (metrics.md) | **Breached in effect** (CRIT-1 $0 coercion; MIN-1 cached_tokens always null; MOD-1 trial drops) |
| N ≥ 3 trials | Enforced nowhere; live data already contains trials=1/2 groups (MOD-1 side effect) |

## Top 5 (by risk × confidence)

1. **CRIT-1** — null→$0 cost coercion is corrupting the live cost leaderboard today (`cli_adapter.py:158-161`, `cli.py:66-68`, `report.py:37`; §6.3 proof).
2. **MOD-1** — `engine run` exits 0 with 100 % errored trials; no error record, no count (live proof §6.2).
3. **MOD-6** — model-writable host `~/.pi/agent/settings.json` → documented packages auto-install → host code-exec; `.gemini` rw unjustified (`sandbox.py:37`).
4. **MOD-3 + MOD-5** — harness_version captured from the wrong filesystem (host vs image) *and* the image is unpinned: attribution drift in both directions, codex permanently name-only (`cli_adapter.py:22-38`, `Dockerfile:30-35`).
5. **MOD-2** — `run_suite_parallel.sh` bare `wait` green-lights total suite failure (`:36-40`).

## P1 backlog (fix before next suite run)

- [ ] P1: fail loud on configured-but-missing usage/cost/tool paths in `_extract_fields`; stop coercing null cost to $0 in `report.aggregate`; mark unpriced groups explicitly (CRIT-1).
- [ ] P1: error accounting + non-zero exit in `cmd_run`; `result="error"` records for dropped trials (MOD-1).
- [ ] P1: PID-collect + per-job `wait` exit aggregation in `run_suite_parallel.sh` (MOD-2).
- [ ] P1: capture harness_version inside the sandbox; make name-fallback loud (MOD-3).
- [ ] P1: drop `.gemini` from `RW_MOUNTS`; overlay-seed `.pi/agent` instead of rw-mounting host dir (MOD-6).
- [ ] P1: pin the `anthropic` dependency and install into the runtime interpreter (or document venv) — raw-api is fully broken today (MIN-2 × MOD-1).

## P2 backlog

- [ ] P2: raise/skip on nonzero `proc.returncode` before metric extraction; persist `exit_code` in `RunRecord` (MOD-4).
- [ ] P2: pin the 5 CLI installs in `harness-base.Dockerfile` (or ARG-version them) (MOD-5).
- [ ] P2: explicit timeout/retry/`stop_reason` handling + partial-result return in `raw_api.run` (MOD-7).
- [ ] P2: cached-token paths through config→adapter→record (MIN-1); remove `bench` alias + judge-ensemble dead wiring (MIN-2/3); strict pricing for unknown models (MIN-4).

---

## 6. Probe appendix (paste-verified, read-only)

### 6.1 Host CLIs + uid (`harness_version` host-capture feasibility)
```
claude: /home/devhax/.local/bin/claude
codex: MISSING
agy: /home/devhax/.local/bin/agy
pi: /home/devhax/.local/bin/pi
opencode: /home/devhax/.opencode/bin/opencode
uid=1000
```

### 6.2 Full-error batch exits 0 with zero records (`anthropic` SDK absent)
```
$ python3 --version
Python 3.14.4
$ python3 -c 'import anthropic'
ModuleNotFoundError: No module named 'anthropic'
$ python3 -m engine run --task tasks/reasoning/multi-step-inventory-word-problem.md --harness raw-api --trials 1
tasks/reasoning/multi-step-inventory-word-problem.md trial=1 harness=raw-api model=claude-sonnet-5 -> ERROR: ModuleNotFoundError: No module named 'anthropic'
EXIT_CODE=0
$ wc -l results/runs.jsonl   # before and after: identical (no record written)
179 results/runs.jsonl
```

### 6.3 Live-data corruption proof (costs null → $0 groups; trials<3 residue)
```
harness=antigravity  rows= 59 cost_null=True  version_is_bare_name=False
harness=claude-code  rows= 60 cost_null=False version_is_bare_name=False
harness=pi-agent     rows= 60 cost_null=False version_is_bare_name=False
distinct harness_version values: ['0.84.2', '1.1.19', '2.1.241 (Claude Code)']
cached_tokens non-null rows: 0

$ python3 -c 'report.aggregate(results.load_all())' (abridged)
ci-pipeline-recovery trials= 2 pass_rate= 0.0 total_cost_usd= 0
ci-pipeline-recovery trials= 3 pass_rate= 0.67 total_cost_usd= 0 cost_per_success= 0.0
cross-file-interaction-bug trials= 1 pass_rate= 0.0 total_cost_usd= 0
needle-in-file-haystack trials= 3 pass_rate= 1.0 total_cost_usd= 0 cost_per_success= 0.0
policy-adherence-pressure trials= 2 pass_rate= 0.5 total_cost_usd= 0 cost_per_success= 0.0
```

### 6.4 Env pass-through: no caller ever populates `container_env`/`extra_env`
```
cli.py:47:        sb = sandbox_mod.create(t.seed_files, t.setup_script)     # env= absent
cli.py:155:       sb = create([], None)                                     # cmd_verify
selfsolve.py:34:  sb = sandbox_mod.create(t.seed_files, t.setup_script)
sandbox.py:91:    merged_env = {**sb.container_env, **(extra_env or {})}    # always {} on bench paths
```

### 6.5 Grading methods in use — zero judge tasks
```
every expected/**/*.md "**grading method:**" line = executable state check / unit test / exact match
(19 files; several annotate "(executable, not judge)")
```

### 6.6 gitignore / results history (invariant 6 clean)
```
$ git check-ignore -v results/runs.jsonl results/report.md .env .env.prod secret.pem tls.key credentials.json mycredentials.yaml .pi/x
.gitignore:4:results/        results/runs.jsonl
.gitignore:4:results/        results/report.md
.gitignore:8:.env            .env
.gitignore:9:.env.*          .env.prod
.gitignore:10:*.pem          secret.pem
.gitignore:11:*.key          tls.key
.gitignore:12:credentials*   credentials.json
.gitignore:22:.pi/           .pi/x
(mycredentials.yaml: NOT matched — `credentials*` is prefix-only; matches the documented backstop scope in memory.md:17-19)
$ git ls-files results/
results/.gitkeep
$ git show --name-only 4d13963 -- results/
results/.gitkeep
```
