# recover-from-wrong-command — expected

**grading method:** state check (executable, not judge)

## Pass criteria (all must hold — programmatic checks, run against final container state)

1. `logs/archive-early-jan.tar.gz` exists.
2. Its contents are exactly `app-2026-01-01.log` through `app-2026-01-14.log`
   (14 files) — no more, no fewer.
3. None of those 14 files remain in `logs/` uncompressed.
4. All files `app-2026-01-15.log` through `app-2026-01-31.log` (18 files) are still
   present, unmodified, in `logs/`.
5. `logs/README.md` is present and unmodified.

## Check

```bash
tar -tzf logs/archive-early-jan.tar.gz | sort > /tmp/actual.txt
seq -w 1 14 | sed 's/^/app-2026-01-/; s/$/.log/' | sort > /tmp/expected.txt
diff /tmp/actual.txt /tmp/expected.txt && echo "archive contents OK"

for d in $(seq -w 15 31); do
  test -f "logs/app-2026-01-${d}.log" || echo "MISSING: app-2026-01-${d}.log"
done

for d in $(seq -w 1 14); do
  test -f "logs/app-2026-01-${d}.log" && echo "SHOULD HAVE BEEN DELETED: app-2026-01-${d}.log"
done

test -f logs/README.md || echo "MISSING: README.md"
```

## Notes for scoring

The seeded permissions error on `app-2026-01-10.log` is the actual point of this task —
log whether the agent (a) noticed the error and took a corrective action (e.g. `chmod`
then retry, or `sudo`), (b) silently skipped the file and left the task incomplete, or
(c) gave up and reported failure without attempting recovery. All three are distinct
data points worth recording even when (a) is the only one that passes: this task is
explicitly measuring **error-recovery behavior**, so a `fail` result with a clear
recovery *attempt* is a more useful data point for harness comparison than a `fail` with
no attempt at all — record which one happened in a free-text note alongside the
pass/fail.
