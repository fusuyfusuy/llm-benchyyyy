# <task-id>

**dimension(s):** <which of: raw model / coding harness / tool-use-agentic / cost-latency>
**difficulty tier:** <easy | medium | hard>
**sourced from:** <where this came from — a real incident, a real PR, a recurring ask;
team-workflow tasks are only valuable if they're actually representative, so note the
provenance>

## Instruction

<the exact prompt/task as the agent under test would see it>

## Environment/setup

<what repo state, files, sandbox, or tools must exist before the run. Prefer something
reproducible — a pinned commit, a container, a fixture — over "whatever's on disk right
now.">

## Constraints

<anything the agent must NOT do — needed for policy-adherence scoring, not just
task-completion>

---

**When adding a task from this template:**

1. Save as `tasks/team-workflows/<id>.md` (delete this instructions block).
2. Write the matching `expected/team-workflows/<id>.md` with pass criteria or a rubric —
   see `expected/grading-methodology.md` for the grading protocol, and the `coding/` and
   `reasoning/` examples for the expected-file shape.
3. If this task is based on a real production incident or real user data, scrub any
   secrets/PII before committing — team-workflow tasks are the least likely to leak into
   a public benchmark, but that's not a reason to be careless with real data.
4. Prefer 50 well-reviewed team-workflow tasks over 500 unreviewed ones — see scope.md's
   decontamination/rot section. An unreviewed task that nobody checks the pass criteria
   on is worse than not having it.
