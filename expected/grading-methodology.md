# Grading methodology

Cross-cutting rules for scoring a run. Task-specific pass criteria live in each task's
`expected/<category>/<id>.md` file; this file is the protocol those criteria are graded
under.

## Deterministic grading only

Every automatic grade must be reproducible without an LLM: a unit test, an exact match,
or a programmatic state check (file exists, exit code 0, output matches a pattern). The
grading-method vocabulary is `exact-match | unit-test | state-check | human`; `human`
grading has no automatic grader — the runner refuses it at dispatch, so genuinely
open-ended judgment calls ("is this explanation clear") are recorded off-ledger, never
scored into `runs.jsonl`.

The LLM judge ensemble this file once specified as a protocol was **decommissioned** —
see `.mimori/decisions.md` ADR 2026-08-30. The measured biases that justified removal
are structural, not prompt-fixable: position bias worth 10-15 points of win-rate swing,
verbosity bias worth 15-30 points, and self-preference bias worth 10-25% when a model
judges its own family's output. The engine enforces the rule at parse time
(`engine/grading/spec.py` raises on any `judge` method), so re-enabling it requires a
code revert plus a superseding ADR.

**Anti-Cheat Rule:** To prevent an agent from achieving a false positive `exit 0` by simply deleting test assertions, all executable coding tasks MUST either:
1. Provide the test assertions in a held-out file that the agent never sees or edits.
2. If the agent must edit the same file that contains the tests, use a cryptographic hash (e.g., `sha256sum`) in the `## Check` block to verify the test suite itself was not tampered with.

## Scoring open-ended quality without a judge

Where correctness is genuinely open-ended, split what is checkable from what is not:

1. **Automate the floor.** Any aspect with a deterministic proxy (tests pass, file
   exists, output pattern, diff-size budget) goes in the `## Check` block and gates the
   result automatically.
2. **Human-review the rest, out of band.** Record the task as `human` in
   `**grading method:**` only when it is deliberately excluded from automatic
   dispatch; the review outcome then goes into analysis notes, not into the automatic
   pass-rate pipeline.
3. **Never substitute an LLM.** If a rubric reads as prose judgment ("idiomatic,"
   "clear"), rewrite it into executable checks where possible or classify the task
   `human`; a decommissioned judge re-enabled "just for this one task" is the exact
   drift the parse-time refusal exists to stop.

## Repeated trials

Every (task, model, harness, tool_access) combination runs **N ≥ 3 trials**. Report
pass-rate and variance, never a single boolean — a model can solve a task once and fail
it repeatedly at only slightly different sampling. For tasks used to make a real
go/no-go decision (e.g. picking a harness for the team), raise N until the model-to-model
delta you care about is larger than the trial-to-trial variance; small deltas need more
trials to detect reliably, not fewer.

## Layer attribution

Every graded result carries the `model` / `harness` / `harness_version` / `tool_access`
/ `scaffold_notes` fields from `metrics.md`. Never report or compare a score without
these — the same model can score 30+ points apart depending on harness/tool-access
alone, so an untagged number cannot be attributed to "the model" or "the harness" and is
not usable for a decision.

## Cost/latency comparability

Only compare `cost_per_success_usd` / `time_per_success_seconds` (from `metrics.md`)
across systems, never raw per-attempt cost or latency — a cheap-but-flaky system and an
expensive-but-reliable one are incomparable on a per-attempt basis. When comparing
latency specifically, hold prompt length roughly constant across the systems being
compared; longer prompts inflate both time-to-first-token and degrade output
tokens/sec independent of the model's actual speed.
