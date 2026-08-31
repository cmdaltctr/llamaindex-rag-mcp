# TDR-017: Restore root logging state after MCP entry-point tests

**Date:** 2026-08-30
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** pytest | logging | test-isolation | regression-guard

## Context

`tests/test_cli.py::TestIngestCLI::test_ingest_json_output` failed with
`JSONDecodeError` whenever `tests/test_mcp_tools.py` ran immediately before
it under explicit file arguments. The full suite stayed green because pytest
collects files alphabetically: `test_cli.py` always ran first. CI therefore
never saw the failure, and the leak survived PR #73 and PR #74.

The string handed to `json.loads(result.output)` began with
`--- Logging error ---` plus a logging-internal traceback, then valid ingest
JSON. Typer's `CliRunner` merges stderr into `result.output`, so the banner
landed ahead of the JSON and parsing failed at char 0.

### Root Cause Analysis

Diagnosis used a handler-snapshot pytest plugin (scratch files under `/tmp`
only), solo runs, and ordered pairs. Full evidence lives in
`openspec/changes/fix-test-isolation-mcp-cli-order/notes.md`.

The causal chain:

1. `tests/test_mcp_tools.py::test_main_reports_runtime_setup_error` calls
   the production `main()`.
2. `main()` runs `logging.basicConfig(..., stream=sys.stderr, force=True)`
   (`src/rag_mcp/transports/mcp/__init__.py:125-131`; was `transports/mcp.py:469-474` at diagnosis time). At that moment `sys.stderr`
   is the `capsys` replacement stream. `force=True` also removes pytest's
   two root handlers.
3. `capsys` teardown closes the replacement stream. The
   `logging.StreamHandler` installed on `logging.root` now holds a closed
   stream. Nothing removes it: pytest's logging plugin removes only its own
   per-test handlers, and the test's `patch` contexts restore only what
   they patched.
4. The later CLI test ingests a file. `detect_file_types`
   (`core/codebase/codebase_map.py:218`) emits `logger.warning("Magika CLI
   not installed; using suffix-based detection")`.
5. The dead handler's `emit` raises `ValueError: I/O operation on closed
   file`. `logging.handleError` prints the `--- Logging error ---` report
   to the current `sys.stderr`, which inside `runner.invoke` is CliRunner's
   merged capture.
6. `result.output` starts with the banner. `json.loads` fails at char 0.

Bisection found a co-leaker. `test_main_calls_mcp_run` also called real
`basicConfig`; its handler bound pytest's fd-capture temp file, which stays
open, so its ordered pair passed. Only the handler-snapshot diff exposed it.
CPython `id()` reuse made the full-file snapshot look like one handler
"flipping" closed; the stream repr change proved that a second `force=True`
call installed a second handler.

Post-implementation review exposed a second side effect of the same call:
`force=True` *closes* every handler attached to the root logger, it does not
merely remove them. The first version of the restore fixture reattached the
original handler objects after each test, but by then they were closed —
pytest's own root `_FileHandler` (mode `w`) stayed attached with
`stream=None` and silently dropped every later file-log record for the rest
of the session. Restoration must therefore prevent the close, not just undo
the removal.

Production logging is not implicated. Both configuration sites are
deliberate once-per-process entry-point behaviour:

- `transports/mcp/__init__.py` `main()` forces root logging to `sys.stderr` so the
  stdio protocol channel (stdout) stays clean.
- `transports/cli/__init__.py` `_setup_logging()` installs the RichHandler
  with `force=True`; `run_cli()` is its only caller, the console-script
  entry point. CLI tests bypass it via `runner.invoke`.

## Decision

Two autouse fixtures in `tests/test_mcp_tools.py`. No production change.

1. **`_restore_root_logging`** (function-scoped, autouse). Snapshots
   `logging.root.handlers` and level at setup. During the test a
   monkeypatched `logging.basicConfig` wrapper detaches the current root
   handlers before delegating whenever `force=True` is requested, so the
   originals are never closed. Teardown closes only handlers the test
   added, then reattaches the original handlers and level. The fixture
   restores state; it never filters output.
2. **`_root_logging_leak_guard`** (module-scoped, autouse). At module setup
   it takes strong references to the root handlers and records the level.
   At module teardown, after all function-scoped teardowns have restored
   state, it fails if the handler list is not the same objects in the same
   order, if any handler that was alive at module setup is closed or holds
   a closed stream at teardown, or if the root level drifted. The dead
   handler check (`_holds_dead_stream`) tests both the `_closed` flag —
   `FileHandler.close()` nulls the stream, so the flag is the only
   evidence — and the stream's own closed flag, which is the capsys leak
   shape. Handlers already dead at module start are exempt: pytest itself
   can leave closed `LogCaptureHandler` objects on root between modules,
   and that pre-existing contamination is outside this guard's scope. The
   guard also fires if the restore fixture is removed or bypassed, for
   example by import-time logging configuration.

Two design choices avoid false positives under pytest capture:

- Closed-flag check instead of `sys.stderr` identity. Pytest global capture
  also swaps `sys.stderr`, so identity comparison false-positives. pytest's
  own handlers hold `stream=None` once `force=True` has closed them, so the
  closed flag stays silent for them.
- Object identity with held references. The guard keeps strong references
  to the baseline handlers, so CPython cannot reuse their ids and the
  comparison is exact — it catches a same-class, same-level replacement,
  which class-name matching missed. Diagnosis-time id instability came from
  comparing ids of unreferenced handlers across snapshots, not from
  identity itself. A probe confirmed this pytest version keeps its
  logging-plugin handler objects stable across a whole module run, so
  plugin churn cannot false-positive the check.

Two counted regression tests pin the behaviour:
`test_force_basic_config_shelters_existing_root_handlers` attaches a
mode-`w` `FileHandler` to the root logger, calls `basicConfig(force=True)`,
and asserts the handler survived unclosed;
`test_leak_guard_detects_closed_handlers` asserts the dead-handler
predicate catches a closed `FileHandler` (stream nulled) and a handler
holding a closed stream, while passing a live handler. The clean-base
tripwire moves to `_BASE_EXECUTED=1952`.

Mutation verification: disabling `_restore_root_logging` made the guard
fail with `StreamHandler holds closed stream` plus handler-set drift.
Neutralising the sheltering detach made the sheltering regression fail
with `force=True closed a pre-existing root handler`. Neutralising the
`_closed` flag check made the detection regression fail. Re-enabled, the
module is green under default capture, `-s`, and `--log-file`, and the
full suite is green after `tests/test_cli.py`.

### Why no production change

Both `basicConfig(force=True)` sites are deliberate entry-point
configuration, each run once per process. Invoking these entry points
in-process while a test harness owns the streams is a test isolation
problem. Embedding `main()` or `run_cli()` inside another host process
would reconfigure that host's logging; that is accepted entry-point
semantics.

## Consequences

### Positive

- The canonical order pair passes. The leak is removed at its source.
- The guard fails loudly if the leak returns, including via import-time
  configuration or a removed restore fixture.
- File logging survives the module: under `--log-file`, records written
  after `tests/test_mcp_tools.py` still reach the log file.
- Two counted regression tests added; the tripwire manifest is bumped to
  match (`_BASE_EXECUTED=1952`).

### Negative

- Two autouse fixtures add per-test overhead to one module. The pair runs
  in about 9 seconds today, so the cost is negligible.
- The guard checks only the root logger. Handler leaks on named loggers
  stay undetected.

### Neutral

- Verification results: module alone 44 passed, 5 skipped; ordered pair
  45 passed, 5 skipped; ordered pair under `-s` and under `--log-file`
  both 45 passed, 5 skipped; module after `tests/test_cli.py` 168 passed;
  full fast suite 1957 passed, 100 skipped, 18 deselected; minimal pair
  passes; CLI test alone passes.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Change the production `basicConfig` calls | Both sites are deliberate once-per-process entry-point configuration; changing them alters production behaviour to suit tests. |
| Filter `--- Logging error ---` from `result.output` in the CLI test | Hides the leak class instead of removing it. The guard would never fire. |
| Stub `logging.basicConfig` in all `main()` tests | Hides real entry-point behaviour the tests exist to exercise. The fd-capture co-leaker would survive. |
| Guard by `sys.stderr` stream identity | Pytest global capture also swaps `sys.stderr`, so stream identity false-positives. Handler identity with held references is used instead. |
| Add a pair-level test in a new file | Adds a counted test and shifts the clean-base tripwire manifest (`_BASE_EXECUTED`). |

## How to Recognise / Handle This Again

1. **Symptom.** A test that parses `result.output` fails with
   `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`, only when
   another test file ran first under explicit file arguments. The captured
   output starts with `--- Logging error ---`.
2. **Diagnose.** Run the canonical order pair below. If it fails, snapshot
   `logging.root.handlers` after each test teardown with a small plugin and
   diff between tests. Look for a handler whose `stream.closed` is `True`,
   and for handler-count changes after tests that call entry points.
3. **Recover.** Keep both fixtures in `tests/test_mcp_tools.py`. A new test
   in that module that calls `main()` needs no extra work; the restore
   fixture already covers it.

Verification commands:

```bash
# Minimal pair (smallest failing combination before the fix)
LOCAL_BACKEND=ollama uv run pytest \
  "tests/test_mcp_tools.py::test_main_reports_runtime_setup_error" \
  "tests/test_cli.py::TestIngestCLI::test_ingest_json_output"

# Canonical order pair
LOCAL_BACKEND=ollama uv run pytest tests/test_mcp_tools.py \
  "tests/test_cli.py::TestIngestCLI::test_ingest_json_output"
```

## Revisit Triggers

- pytest changes its capture or logging plugin behaviour: handler
  lifetimes, what teardown closes.
- A new test module invokes `main()`, `run_cli()`, or another `force=True`
  entry point. The restore fixture lives in `tests/test_mcp_tools.py`
  only.
- Guard noise appears under another capture mode (`-s`, `--capture=sys`)
  or a logging-configuring plugin.

## References

- `openspec/changes/fix-test-isolation-mcp-cli-order/` — proposal, design,
  and the full diagnosis in `notes.md`.
- `tests/test_mcp_tools.py` — "Logging isolation" fixtures:
  `_restore_root_logging`, `_root_logging_leak_guard`.
- `src/rag_mcp/transports/mcp/__init__.py:125-131` — the installing `basicConfig`
  call in `main()`.
- `src/rag_mcp/transports/cli/__init__.py` — `_setup_logging()`, the
  second `force=True` site.
- `tests/TEST_README.md` — documented order-pair command.
