# TDR-034: The clean-base tripwire ran a serial suite, so run it in parallel and stop pinning the skipped count

- **Date:** 2026-10-15
- **Status:** Accepted (tripwire passes in 2m39s against the real suite; three clean parallel runs after the log fixture fix)
- **Deciders:** Aizat
- **Tags:** testing | ci | xdist | tripwire | flaky-tests
- **Related:** [TDR-032](032-knowledge-base-hid-the-database-and-the-profile-list-implied-a-stored-profile.md), `docs/guides/testing.md`

## Context

`tests/test_clean_base_tripwire.py` starts a second full pytest run inside one
test and compares its counts with pinned numbers. That inner run was a single
process, about 7.5 minutes, using about 60% of one core on a 15-core Mac. The
`xdist` setup only helps when a command passes `-n`, and the tripwire's did not.
`./scripts/local_ci.sh` ran the whole suite serially, and that run included the
tripwire, so one pre-push check took about 15 minutes.

### Root Cause Analysis

Cause: the inner command had no `-n`, so 14 cores stayed idle.

A parallel inner run is not a drop-in change. Two things differ from a serial run:

1. The summary line has no "deselected" count, and the tripwire parsed it.
2. The skipped count is one lower: 135 in parallel against 136 in serial. The same
   one-test gap was already there before this change (134 against 135). The skip
   lists at collection time are identical, so the difference appears while tests
   run. The test that differs was not found.

## Decision

1. **Run the inner suite with `-n auto --maxprocesses=8`** when pytest-xdist is
   installed. It falls back to a serial run when it is not.
2. **Read the deselected count from a collection-only run.** It takes seconds and
   gives the same answer in serial and parallel.
3. **Stop pinning the skipped count.** The remaining checks cover what it caught:
   - the exact executed count catches a test that stops running, because it drops
     by one, and a skipped test that starts running, because it rises by one;
   - the deselected count catches a test that gains or loses the `slow` mark;
   - the static Chroma file check still enforces that only the named files skip
     for the Chroma reason.
4. **`local_ci.sh` runs the main suite in parallel** with the tripwire deselected,
   then runs the tripwire as its own step. About 2.5 plus 2.5 minutes, down from
   about 15. CI stays serial and remains the source of truth.
5. **Fix a flaky test the parallel run exposed.** `test_a_bad_format_does_not_break_logging`
   failed when a file that installs a `rich` log handler on the root logger ran
   on the same worker earlier. The CLI tests install that handler and never remove
   it. It raises on a bad format string, so the result depended on which files
   shared a worker. The `buffer` fixture in `tests/unit/test_web_logs.py` now sets
   `propagate = False` on its logger and restores it. The failure was reproduced on
   demand, and the test now passes with the handler present.

## Consequences

### Positive

- The tripwire takes about 2.5 minutes instead of 7.5. The pre-push check takes
  about 7 minutes with the frontend gates, instead of about 15 serial.
- One flaky test is gone, with its cause known.

### Negative

- The guardrail no longer pins the skipped count. A skip that appears while an
  equal number of other tests start running would net out. The static Chroma check
  and the exact executed count make this unlikely.
- The one-skip difference between serial and parallel runs is unexplained.
- A parallel inner run can show timing-sensitive tests that a serial run hides. The
  MCP test `test_a_running_tool_call_finishes_before_the_engine_closes` failed once
  under load and passed on every rerun.

### Neutral

- `local_ci.sh` no longer runs the main suite serially, which differs from CI.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Leave the tripwire serial and run it only before a push | The full check stays slow, and a wrong count shows up late. |
| Pin the skipped count separately for serial and parallel | It doubles the pins and the manifest comments, and the extra pin guards little. |
| Find the differing skip first | It needs another 7-minute serial run, and the redesign does not depend on the answer. |
| Skip the tripwire locally and rely on CI | A wrong count would only show after the push. |

## How to Recognise / Handle This Again

- Symptom: the tripwire fails with "base executed count drifted". A test was added, removed or started skipping. Compute the effective expectation by importing `tests.test_clean_base_tripwire` and reading `_BASE_EXECUTED`, then update the pin and its comment.
- Symptom: a test fails in a parallel run and passes alone. Look for logging, environment or module state that an earlier file leaves behind. `--dist loadfile` keeps one file on one worker, but files still share a worker.
- Re-evaluate if CI starts to flake on the tripwire's inner run. Set the inner run to `-n 4`, or back to serial.
- If the one-skip difference matters, run the suite serially with `-rs` once, run it in parallel with `-rs`, and diff the `SKIPPED` lines.

## References

- `tests/test_clean_base_tripwire.py` (`_base_suite_counts`), `tests/unit/test_web_logs.py` (`buffer` fixture), `scripts/local_ci.sh`
- `docs/guides/testing.md` ("Run in parallel"), `CLAUDE.md` ("Parallel runs")
