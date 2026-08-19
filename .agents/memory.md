# Project Memory

## Active Epics & Tasks
- v1 runner built + pushed to github.com/fusuyfusuy/llm-benchyyyy (public). Open:
  codex-cli/antigravity/pi-agent/opencode JSON field-mapping in
  bench/harness/configs.py unverified live (docs-derived only, codex not
  installed locally). raw-api + judge.py untested live, ANTHROPIC_API_KEY not
  set in this env.

## Core Invariants & Architecture Rules
- tasks/ and expected/ MUST stay separate dirs. Never put pass criteria/rubric
  in tasks/. Reason: contamination control + Dataset/Solver/Scorer split, see
  scope.md.
- Never commit results/. .gitignore blanket-excludes it (except .gitkeep).
  Holds real cost/token data + API-driven run transcripts.
- Never commit API keys/credential files. Keys live in env only. .gitignore
  backstops .env, *.pem, *.key, credentials* but rule is: keys never touch a
  tracked file.
- Task/expected markdown convention bench/markdown.py parses: fenced block
  first line `# path/to/file` = seed file written verbatim (minus that line)
  before run. `## Setup` bash block = setup script, runs before harness.
  `## Check` bash block in expected/ = grader command, exit 0 = pass.
  `## Rubric` numbered list = judge-graded criteria.
- Every run must repeat N>=3 trials, report pass_rate not single pass/fail
  (non-determinism). Every result tagged model+harness+harness_version+
  tool_access (layer attribution) — untagged score is not valid, see
  metrics.md.
- CLI harness containers authenticate by bind-mounting host's own CLI config
  dirs read-only, not reimplementing auth. Container runs as non-root `ubuntu`
  (uid 1000) — Claude Code CLI refuses --dangerously-skip-permissions as root.

## Domain Vocabulary & Gotchas
- Model ID is `claude-sonnet-5`, no date suffix — `claude-sonnet-5-20260115`
  is invalid (caught live during smoke test, was in cli.py/pricing.py/judge.py
  before fix).
- pi-coding-agent needs Node >=20 (image uses 22.x via NodeSource, not Ubuntu
  apt package).
- Antigravity CLI install URL: antigravity.google/cli/install.sh (an earlier
  guessed URL 404'd).
