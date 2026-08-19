# llm-benchyyyy

Design spec for benchmarking LLM models, coding agents/harnesses, and tool-use/agentic
behavior — including cost/latency. This repo holds the **scope, task definitions, and
grading criteria only**. There is no runner here; tasks are run by hand or by whatever
harness/script you point at a given task+harness+model combination.

## Layout

- `scope.md` — what we're benchmarking, why, and the methodology decisions (and their
  justification from prior art).
- `metrics.md` — what to record for every run, regardless of task category.
- `tasks/<category>/*.md` — task definitions. **No expected output or grading criteria
  lives here.** An agent under test should be able to read a task file and have
  everything it needs to attempt the task, and nothing that leaks the answer.
- `expected/<category>/*.md` — one file per task (same filename as its `tasks/` twin),
  holding the expected output / pass criteria / grading rubric. Kept in a separate
  directory on purpose — see "Why tasks and expected outputs are split" in `scope.md`.
- `expected/grading-methodology.md` — cross-cutting rules for how to score a run
  (repeated trials, judge protocol, layer attribution), not specific to any one task.

## Categories

- `coding/` — real repo/coding tasks (SWE-bench / terminal-bench style: instruction +
  environment + verifiable success condition).
- `reasoning/` — general reasoning/QA prompts with a known-good answer or rubric.
- `agentic/` — multi-turn, tool-using scenarios (terminal, multi-step planning, recovery
  from a wrong turn).
- `team-workflows/` — tasks sourced from things this team actually asks these tools to
  do. Start from `tasks/team-workflows/TEMPLATE.md`.

## Adding a task

1. Write `tasks/<category>/<id>.md` — instruction, environment/setup, constraints, and
   which dimension(s) it's meant to probe (see `scope.md`).
2. Write `expected/<category>/<id>.md` — the pass criteria or rubric. Never restate the
   task instruction there beyond what's needed to grade it.
3. Record results per `metrics.md`'s schema — model, harness, tool-access config, trial
   number, pass/fail, cost, wall-clock.
