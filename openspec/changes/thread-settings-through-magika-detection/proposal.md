# Proposal: Thread settings through Magika content-type detection

## Why

The ingestion pipeline calls `detect_file_types(path)` without the
`EffectiveSettings` it already holds, and the detector resolves the
process-global default instead (`core/codebase/codebase_map.py:332`). Any
process that constructs an `Engine` directly — the public library API,
tests, experiment harnesses — installs no global, so the lookup raises and
every file silently degrades to extension-based routing
(`core/ingestion/pipeline.py:195-202`). Experiment 31 logged this warning
57 times; its cells were valid only because the fallback was identical
across cells. This is a live violation of the
`settings-dependency-injection` requirement that `ingest_path_async()`
pass its settings down to every module it calls.

## What Changes

- `detect_file_types()` accepts the caller's `EffectiveSettings` and uses
  it for the Magika binary resolution instead of reading the process
  global.
- The ingestion pipeline passes its already-resolved `resolved_settings`
  into `detect_file_types()`.
- Callers that legitimately resolve at their own entry boundary (the
  codebase-map transport path) keep working unchanged.
- No routing behaviour changes: the extension-based fallback remains the
  documented degradation when the Magika binary is genuinely unavailable.
- Regression test: ingesting through a directly-constructed `Engine`
  (no process global installed) produces a populated `content_type` and
  no "Magika detection failed" warning.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `settings-dependency-injection`: adds an enforcement scenario to the
  existing "Core operations receive settings as a parameter" requirement —
  content-type detection during ingestion SHALL receive the injected
  settings and SHALL NOT require a process-global default.

## Impact

- Code: `src/omrg/core/ingestion/pipeline.py` (one call site),
  `src/omrg/core/codebase/codebase_map.py` (signature + resolution),
  `tests/` (regression test).
- Index identity: `content_type` feeds `build_index_identity`, so rows
  previously written by direct-Engine processes (identity built with
  `content_type=None`) go stale and rebuild on their next re-ingest.
  Server-written collections already carry the label and are unaffected.
- No public API break: the new parameter is optional; existing callers
  compile and behave identically.
- Experiment 31's artefacts already document the observed failure
  (`experiments/31-reader-rescue-retrieval-impact-2026-09-15/report.md`,
  Limitations) and need no revision.
