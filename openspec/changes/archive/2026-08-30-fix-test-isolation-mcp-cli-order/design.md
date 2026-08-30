## Context

pytest's capture machinery replaces and closes `sys.stderr` around each test
phase. Any `logging.StreamHandler` constructed against the pre-replacement
stream object raises during `emit` once that stream is gone; Python's logging
then prints a `--- Logging error ---` banner with an internal traceback to
the current stderr. `tests/test_mcp_tools.py` exercises `main()` and serve
paths that call real `logging.basicConfig` (only one test stubs it, at line
1110), so a root handler bound to a doomed stream survives the file. Typer's
`CliRunner` merges stderr into `result.output`, and alphabetical collection
(`test_cli.py` before `test_mcp_tools.py`) hides the pair from the default
suite order.

## Goals / Non-Goals

**Goals:**

- Make the explicit order pair
  `pytest tests/test_mcp_tools.py tests/test_cli.py::TestIngestCLI::test_ingest_json_output`
  pass on a clean tree.
- Remove the leaked handler at its source through restore, not suppression.
- Leave a regression guard that fails if the leak returns.
- Record the root cause in `docs/tdr/`.

**Non-Goals:**

- Redesigning production logging configuration.
- Auditing every test module for other order dependencies; only the
  demonstrated pair is in scope.
- Silencing the banner via output filtering in the CLI test.

## Decisions

- **Diagnose by handler-diff bisection.** Snapshot `logging.root.handlers`
  and level before and after candidate tests in `tests/test_mcp_tools.py`
  until the surviving handler appears. This pins the leak to one
  installation point without guessing.
- **Fix by restore, not suppression.** An autouse fixture in the leaking
  module snapshots root handlers and level at setup and restores them at
  teardown. Filtering the banner out of `result.output` in the CLI test
  would hide the leak class rather than remove it.
- **Regression guard at the leak, not the symptom.** Prefer a guard that
  detects a handler bound to a closed or replaced stream after the module
  runs. If that proves impractical, fall back to a documented order-pair
  command plus a pair-level test; record the chosen mechanism in the TDR.

## Risks / Trade-offs

- An autouse restore fixture adds per-test overhead to one module; the pair
  runs in about 9 seconds today, so the cost is negligible.
- Restoring handlers could mask a genuine production double-configuration if
  diagnosis is shallow; task 1.3 exists to close that gap before the fix
  lands.
- A new test file would shift the clean-base tripwire counts; task 4.2
  covers the manifest update contract.
