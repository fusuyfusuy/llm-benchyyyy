# llm-benchyyyy

Benchmark suite for LLM models, coding agents/harnesses (Claude Code, Codex CLI, Google
Antigravity CLI, Pi coding agent, OpenCode), and tool-use/agentic behavior — including
cost/latency. Holds both the design spec (scope, tasks, grading criteria), the
runner engine (`engine/`) that executes tasks in a Docker sandbox, and analysis checkers (`checkers/`).

## Quickstart

```bash
python3 -m pip install -e .
export ANTHROPIC_API_KEY=...        # needed for the raw-api harness
docker build -f docker/harness-base.Dockerfile -t llm-bench-harness .

python3 -m engine run --task tasks/coding/fix-off-by-one-pagination.md \
    --harness claude-code --model claude-sonnet-5 --trials 3

python3 -m engine report
```

`--harness` is one of `raw-api`, `claude-code`, `codex-cli`, `antigravity`, `pi-agent`,
`opencode` (see `engine/harness/configs.py`). CLI harnesses other than `claude-code`
authenticate the same way they do on your host — see "Credentials" below.

## Layout

- `scope.md` — what we're benchmarking, why, and the methodology decisions (and their
  justification from prior art).
- `metrics.md` — what's recorded for every run, regardless of task category.
- `tasks/<category>/*.md` — task definitions. **No expected output or grading criteria
  lives here.** An agent under test should be able to read a task file and have
  everything it needs to attempt the task, and nothing that leaks the answer.
- `expected/<category>/*.md` — one file per task (same filename as its `tasks/` twin),
  holding the expected output / pass criteria / grading rubric, and (for
  executable-graded tasks) the `## Check` command the runner actually executes. Kept in
  a separate directory on purpose — see "Why tasks and expected outputs are split" in
  `scope.md`.
- `expected/grading-methodology.md` — cross-cutting rules for how to score a run
  (repeated trials, deterministic-only grading, layer attribution), not specific to any
  one task.
- `engine/` — the execution engine: `task.py`/`markdown.py` parse task/expected files,
  `sandbox.py` drives the Docker container, `harness/` holds the raw-api adapter and
  the generic CLI-harness adapter + per-harness configs, `grading/` holds the
  deterministic graders (executable/unit-test + state-check via `## Check`, exact-match;
  the judge ensemble was decommissioned, see `.mimori/decisions.md` ADR 2026-08-30),
  `results.py`/`report.py` log and aggregate runs, `score.py` provides 100-point
  categorical scoring.
- `checkers/` — standalone analysis tools, live benchmark aggregators, OpenCode Go cost-benefit
  analyzers, stealth model detectors, and task checkers.
- `docker/harness-base.Dockerfile` — one image with all 5 CLI harnesses installed;
  built once, reused for every run.
- `results/` — **gitignored.** `runs.jsonl` (raw per-trial log) and `report.md`
  (aggregated) are generated locally by `engine run` / `engine report` and never
  committed — see "Secrets & results" below.

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
   which dimension(s) it's meant to probe (see `scope.md`). A fenced block whose first
   line is `# path/to/file.ext` gets written verbatim to that path in the sandbox
   before the run; a `## Setup` bash block runs before the run for anything beyond
   writing files.
2. Write `expected/<category>/<id>.md` — the pass criteria, plus a `## Check`
   bash block (exit code 0 = pass) for executable-graded tasks or a `## Pass criteria`
   section with the exact expected value for exact-match tasks. Grading is
   deterministic-only — the runner refuses any `judge` method at parse time (see
   `.mimori/decisions.md` ADR 2026-08-30). Never restate the task instruction there beyond
   what's needed to grade it.
3. Run it: `python3 -m engine run --task tasks/<category>/<id>.md --harness <harness>
   --model <model> --trials 3`, then `python3 -m engine report`.

## Credentials

The container authenticates each CLI the same way it does on your host: their config/
credential directories are bind-mounted read-only into the container rather than the
runner reimplementing auth. `claude-code` is verified working this way; the mount paths
for `codex-cli`/`antigravity`/`pi-agent`/`opencode` may need adjusting in
`engine/sandbox.py` to match where those tools store credentials on your machine. The
`raw-api` harness calls the Anthropic API directly and only needs `ANTHROPIC_API_KEY`
exported.

## Secrets & results

- **Never commit `results/`.** It holds raw run transcripts and real cost/token data
  tied to your API usage; `.gitignore` blanket-excludes the directory (except
  `.gitkeep`) so this isn't opt-in.
- **Never commit API keys or credential files** — `ANTHROPIC_API_KEY` and friends must
  only exist in your shell environment or an untracked `.env`; `.gitignore` excludes
  `.env`, `*.pem`, `*.key`, and `credentials*` as a backstop, but the actual rule is:
  keys never go in a file that isn't already gitignored.
- Before pushing after adding a new task, run `git status` and check nothing under
  `results/` or matching a secret pattern is staged — `.gitignore` catches the common
  cases but isn't a substitute for looking.
