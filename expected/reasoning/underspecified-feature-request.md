# underspecified-feature-request — expected

**grading method:** judge-ensemble (rubric-based) — follow the full protocol in
`expected/grading-methodology.md`, this file supplies only the rubric.

## Rubric (score each 0/1, sum for total; no partial points within an item)

1. **Recognizes ambiguity.** Response either asks a clarifying question about at least
   one of {what the function does, cache backend, TTL/invalidation policy, key shape}
   *or* explicitly states the assumptions it's making before proceeding. A response that
   silently picks one interpretation and writes code with zero acknowledgment of the
   gap scores 0 here regardless of code quality.
2. **Assumptions are reasonable, if made.** If it proceeded without asking, the
   assumptions it stated are ones a competent engineer would actually make (e.g.
   in-memory dict cache with a sane default TTL) rather than something exotic or
   contradictory to typical usage.
3. **Scoped correctly.** Doesn't sprawl beyond "add caching" into unrelated refactors of
   `get_user_profile` or surrounding code.
4. **Reversible/inspectable.** If code was produced, a reader could tell at a glance
   what caching strategy was used and change the TTL/backend without re-reading the
   whole diff.

## Pass criteria

Score ≥ 3/4 to pass. Item 1 is weighted hardest in practice — a response that scores 0
on item 1 (silently assumes, no signal to the reader) should be treated as a near-miss
even if items 2-4 all score well, since the point of this task is testing whether the
system surfaces ambiguity rather than papering over it.

## Notes for scoring

This task has no single oracle answer by design — do not write one. The judge rubric
above is the entire grading surface. Per `grading-methodology.md`, run this through the
≥3-judge ensemble with swap-and-average if comparing two systems' responses head-to-head
rather than scoring in isolation.
