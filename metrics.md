# Metrics to record per run

Record these fields for every attempt at every task, regardless of category. "Run" =
one attempt by one (model, harness, tool-access config) combination at one task.

## Identity / attribution (required — see scope.md's layer-attribution rule)

- `task_id` — matches the task's filename in `tasks/`.
- `model` — exact model id/version (e.g. `claude-sonnet-5-20260115`, not just "Sonnet").
- `harness` — the tool/agent under test (e.g. `claude-code`, `cursor`, `aider`, `raw-api`
  for a no-harness baseline).
- `harness_version` — version/commit of the harness, if applicable. Harnesses change
  behavior between releases; an unpinned version invalidates comparison over time.
- `tool_access` — which tools were available (e.g. `read+write+bash`, `read-only`,
  `no-internet`). Two runs of the same model+harness with different tool access are not
  comparable.
- `scaffold_notes` — system prompt / config overrides, if any, that differ from the
  harness's default.
- `trial_number` — which of the N ≥ 3 repeated trials this is.

## Outcome

- `result` — pass / fail / partial (for rubric-graded tasks, partial credit per the
  rubric in `expected/`).
- `grading_method` — exact-match / unit-test / judge-ensemble / human. See
  `expected/grading-methodology.md` for judge protocol.
- `constraint_violations` — did the run break any constraint listed in the task file
  (e.g. modified a file it shouldn't have)? Track separately from task success —
  a run can pass the task and still violate policy.

## Cost / latency (normalize per successful task, not per attempt — see scope.md)

- `wall_clock_seconds` — start to final answer/patch.
- `input_tokens` / `output_tokens` (and cached-token counts if the provider reports
  them — prompt caching materially changes $/task and should not be hidden).
- `cost_usd` — computed from the above at the pricing tier actually used; note the tier
  (batch vs. realtime) since it affects both cost and latency.
- `tool_call_count` — number of tool invocations; a proxy for efficiency and for
  detecting thrashing (many calls, no progress) independent of pass/fail.

## Derived (compute after collecting raw runs, don't hand-enter)

- `pass_rate` — passes / N trials, per (task, model, harness, tool_access).
- `cost_per_success_usd` — total cost across trials / number of passing trials. If zero
  trials pass, report cost-with-no-success separately rather than dividing by zero.
- `time_per_success_seconds` — same idea, wall-clock.
- `success_by_difficulty` — pass rate sliced by the task's difficulty tier, per
  scope.md's task schema.
