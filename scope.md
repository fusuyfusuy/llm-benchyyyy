# Scope

## What we're benchmarking

Four things, on purpose kept distinct because they answer different questions:

1. **Raw models** — same harness/tool access held fixed, swap the model. Answers "is
   model A smarter than model B."
2. **Coding agents/harnesses** — same model held fixed (where possible), swap the
   harness (Claude Code, Cursor, Aider, Codex CLI, OpenHands, ...). Answers "does this
   harness's scaffolding/tool design get more out of the same model."
3. **Tool-use / agentic behavior** — planning, multi-step tool calls, error recovery,
   policy adherence (does it stay within the rules while completing the task, not just
   whether it completes it).
4. **Cost / latency / ops** — $/successful task, wall-clock/successful task, token
   efficiency. Orthogonal to correctness; a system can be cheap-and-flaky or
   expensive-and-reliable, and only cost-per-success makes those comparable.

**Every result must be tagged with which layer it's attributed to**: model, harness,
tool-access config, and scaffold/system prompt. This isn't optional bookkeeping — GAIA's
published leaderboards show the *same underlying model* scoring 30-50 points apart
depending on whether it's run bare, with a vendor scaffold, or inside a full agent
system. An untagged number is not a valid data point in this benchmark.

## Task domains

Crossed against the four dimensions above:

- **Real repo/coding tasks** (`tasks/coding/`) — fix a bug, implement a feature, pass a
  held-out test suite in an actual codebase. Modeled on the terminal-bench task schema:
  instruction + sandboxed environment + executable verifier + (in `expected/`) an oracle
  reference solution.
- **General reasoning/QA** (`tasks/reasoning/`) — prompts with a known-good answer or
  rubric, graded automatically where possible (exact match / unit test) and by
  judge-ensemble where not.
- **Team workflows** (`tasks/team-workflows/`) — tasks pulled from what this team
  actually asks these tools to do. Highest relevance, most maintenance burden; start
  from the template and add real examples as they come up.
- **Multi-turn agentic scenarios** (`tasks/agentic/`) — long-horizon tasks needing
  planning, tool calls, and recovery from a mistake mid-task (terminal use, multi-step
  execution). Track a **success-vs-difficulty curve**, not a single scalar, per METR's
  time-horizon framing: report the task length/complexity at which success rate crosses
  50%, not just pass/fail on a fixed-length task.

## Task schema (applies to every task file in `tasks/`)

Every task file should contain, in this order:

- **id** — stable slug, referenced by the matching `expected/` file.
- **dimension(s)** — which of the four things above this task is meant to probe.
- **difficulty tier** — rough tier (easy/medium/hard), so results can be sliced by
  difficulty rather than averaged into one meaningless number.
- **instruction** — the natural-language prompt/task as the agent under test would see
  it.
- **environment/setup** — what sandbox, repo state, files, or tools must exist before
  the task starts. Prefer a disposable, reproducible setup (container, fresh checkout)
  over "run this against whatever's currently on disk."
- **constraints** — anything the agent must NOT do (e.g., must not modify test files,
  must stay within N tool calls) — needed for policy-adherence scoring, not just
  task-completion.

Nothing about expected output or how it's graded belongs in this file.

## Why tasks and expected outputs are split into separate directories

Three independent reasons, all confirmed by how existing eval frameworks are built:

1. **Contamination control.** If an agent under test reads a task's containing
   directory (or the repo is dropped into an agent's context wholesale), the expected
   answer must not be reachable from there. This matters more as we re-run the same
   tasks against newer models over time — an answer sitting next to the prompt is a
   standing leak, not just a one-time risk.
2. **The Dataset → Solver → Scorer separation** that frameworks like Inspect AI use
   (and which promptfoo/OpenAI Evals mirror less formally): the task+environment
   (Dataset) is independent from the agent/model/harness being evaluated (Solver), which
   is independent from how a run is graded (Scorer). Keeping tasks/ and expected/ as
   separate trees is that same separation expressed as a filesystem layout, so a task
   can be run through any Solver without adaptation and graded consistently.
3. **Grading changes more often than tasks do.** Rubrics get refined, judges get
   swapped, exact-match graders get replaced by unit tests. Keeping grading criteria in
   its own tree means that churn never touches the task prompts, which is what would
   actually invalidate historical comparisons.

## Freshness, decontamination, and benchmark rot

Public coding benchmarks decay: OpenAI stopped reporting SWE-bench Verified after
finding a large fraction of an audited subset unsolvable-as-written, and independent
audits found roughly a third of "passing" patches showed evidence of solution leakage
(models reciting memorized fixes rather than solving the issue). Apply the same
skepticism here:

- Prefer **team-workflow tasks and freshly-written coding/reasoning tasks** over
  anything copied from a public dataset — public tasks may already be in a model's
  training data.
- **Version every task.** When a task's instruction or environment changes, bump its id
  (`fix-flaky-retry-v2`) rather than editing in place, so historical scores stay
  attributable to what was actually run.
- **Retire saturated tasks** — if every model/harness combination passes a task for two
  consecutive rounds, it's no longer discriminating; replace it rather than let it
  inflate aggregate pass rates.
- **Periodically test for verbatim recall** on any task written more than ~a year ago:
  ask a model to recite the task's expected output without being shown it. A hit means
  the task has leaked (into training data or a shared transcript) and should be retired
  or rewritten.
- Tasks in `team-workflows/` are the least likely to leak since they're internal by
  construction — weight them accordingly when a score needs to be trusted.

## Non-determinism

A single run's pass/fail is not a result. Every task should be run **N ≥ 3 trials**
per (model, harness, tool-access) combination, and results reported as pass-rate +
variance, not a single boolean. See `expected/grading-methodology.md` for the full
protocol, including judge-ensemble rules for anything graded by an LLM rather than an
executable check.
