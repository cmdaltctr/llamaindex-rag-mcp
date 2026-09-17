# Proposal: Pin Magika and correct content-detection parsing

## Why

The installed official package is `magika==1.0.3`; `google-magika` does not
exist on PyPI. The prior `0.6.3` and installed `1.0.3` CLI output use nested
JSONL fields. The current parser
reads `obj.output`, fabricates `unknown/unknown` with `is_text=true`, and
therefore does not use the detected result. The current uncommitted state is
`magika>=1.0.3` in `pyproject.toml`, a 1.0.3 lock entry, and three red tests.
This planning session leaves those files untouched.

Detection controls early binary skipping, code routing, and part of index
identity. It must parse a successful result safely before the dependency
becomes mandatory. This change does not ingest data or modify a store.

## What Changes

- Pin the official base dependency as `magika==1.0.3` in a later authorised
  implementation session. Preserve the existing `MAGIKA_BINARY` subprocess
  transport, settings injection, timeout, and suffix fallback contract.
- Parse only `status == "ok"` records at `result.value.output`. Validate
  non-empty string `group` and `label` fields plus boolean `is_text`. Ignore
  blank JSONL lines. A failed status, non-JSON row, malformed successful
  record, or invalid required field fails the whole scan and uses the existing
  suffix fallback with a warning.
- Normalise only safe boundary differences: non-document, non-code, and
  non-text `is_text=false` groups become `binary`; `text/markdown` becomes
  `document/markdown`; `text/txt` becomes `document/text`.
- Add regressions and a detection-only smoke script. It compares path sets
  from existing suffix and direct Magika scanners. It must fail on residual
  label mismatch, missing, extra, or duplicate paths, empty input, or detector
  failure. It must not copy the suffix table or add a directory walker.
- Record implementation evidence after a passing real-corpus gate. TDR-025
  remains authoritative for settings and identity. Its `google-magika` and
  unverified-taxonomy wording is historical and superseded by this evidence
  until a later TDR update.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `type-aware-ingestion`: requires a pinned Magika detector, validated JSONL
  parsing, narrow label normalisation, and a fail-closed comparison gate.

## Impact

- Later implementation changes: `pyproject.toml`, `uv.lock`,
  `integrations/magika.py`, the existing detector fallback catch in
  `core/codebase/codebase_map.py`, focused regressions, one smoke script, and
  decision records. No pipeline, extension-admission, graph, cache, or
  store design changes are planned.
- Index identity stays stable only where the previous explicit label and all
  other identity inputs match the normalised label. `None` and `unknown`
  labels can rebuild on a later explicit ingest. No backfill occurs.
- The detector remains optional at runtime. Missing binary, non-zero exit,
  timeout, and parser failure use the existing warned suffix fallback.
- The planned smoke gate must pass before any acceptance or merge. It does
  not authorise re-ingestion.
