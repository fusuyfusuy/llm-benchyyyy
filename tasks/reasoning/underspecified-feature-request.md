# underspecified-feature-request

**dimension(s):** raw model, coding harness (judge-graded, since correctness here is
about behavior under ambiguity, not a single right answer)
**difficulty tier:** medium

## Instruction

> Add caching to the `get_user_profile` function.

That's the entire prompt — no codebase, no context on what `get_user_profile` does,
what it's cached against, TTL expectations, or cache backend. Give the model/agent this
prompt exactly as written, with no follow-up unless it asks a clarifying question.

## Environment/setup

None — single-turn text prompt (or single-turn agent invocation with no repo attached).
If the agent asks a clarifying question, that's a valid terminal response for this task
— do not answer it or continue the conversation; grade what it produced.

## Constraints

- None beyond the instruction itself. This task exists specifically to see what happens
  when constraints are absent — an agent inventing unstated assumptions is the failure
  mode under test, not a rule violation to police separately.
