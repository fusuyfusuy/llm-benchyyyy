# recover-from-wrong-command

**dimension(s):** tool-use/agentic behavior, coding harness
**difficulty tier:** medium

## Instruction

You're given a directory `logs/` containing files `app-2026-01-01.log` through
`app-2026-01-31.log` (31 files) plus one unrelated file `README.md`. Compress every
`.log` file older than 2026-01-15 into a single archive `logs/archive-early-jan.tar.gz`,
then delete the original `.log` files that were archived (but not the ones from
2026-01-15 onward, and not `README.md`).

The environment is seeded so that the first `rm` or `tar` command the agent runs against
a glob like `*.log` will hit a permissions error on exactly one file
(`app-2026-01-10.log`, chmod'd read-only) — this is intentional, to observe recovery
behavior, not a broken environment.

## Environment/setup

Container with `logs/` populated as described; `app-2026-01-10.log` set to mode `0444`
before the run starts. Agent has shell access (this task requires it — it's specifically
testing tool-use, not code-writing).

## Constraints

- Must not delete or modify `README.md`.
- Must not delete any `.log` file dated 2026-01-15 or later.
- Must end in a state where the archive exists, contains exactly the pre-01-15 logs,
  and those logs (including the one that hit the permissions error) are gone from
  `logs/` — recovering from the permissions error is part of completing the task, not
  optional.
