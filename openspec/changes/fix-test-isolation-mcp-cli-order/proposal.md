## Why

`TestIngestCLI::test_ingest_json_output` fails with a `JSONDecodeError`
whenever `tests/test_mcp_tools.py` runs immediately before it, and passes in
isolation. Reproduced on base `dd64bf3` before PR #73 and again on `d6fd49c`
after PR #74, so both merged changes are unaffected carriers of a
pre-existing leak.

The failure mechanism is observed directly. The string handed to
`json.loads(result.output)` begins with `--- Logging error ---` followed by a
logging-internal traceback, then valid ingest JSON. `tests/test_mcp_tools.py`
leaves a logging handler installed on a stream that pytest has since replaced
or closed; when the CLI test's ingest emits a log record, the handler fails
during emit and Python's logging machinery prints the error banner into the
captured output. Typer's `CliRunner` merges stderr into `result.output`
(`tests/test_cli.py:166-205`), so the banner lands ahead of the JSON.

The full suite never fails because pytest collects files alphabetically:
`test_cli.py` always runs before `test_mcp_tools.py`. The failing order only
occurs under explicit file arguments, so CI stays green while the leak
persists undetected.

## What Changes

- Identify the exact test or import path in `tests/test_mcp_tools.py` that
  installs the surviving handler. `logging.basicConfig` is stubbed in only
  one test (`tests/test_mcp_tools.py:1110`); other runtime paths call the
  real configuration.
- Restore logging configuration around that module's tests so no handler
  outlives the file: snapshot and restore root handlers and level through an
  autouse fixture, mirroring the existing `monkeypatch` discipline.
- Add regression coverage for the demonstrated order pair and document the
  pair command in `tests/TEST_README.md`.
- Record the root cause in a TDR under `docs/tdr/`.

Production logging behaviour stays out of scope unless diagnosis implicates
it. Restore, not suppression, is the fix shape.

## Capabilities

### Modified Capabilities

- `internal-maintainability`: adds a requirement that test modules restore
  logging state they install, with the MCP-then-CLI order pair as the
  observable scenario.
