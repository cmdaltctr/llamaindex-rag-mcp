## Why

The `pdf-reader` baseline spec still describes v1-era mechanics that v2.0.0
(ADR-037) deleted: a `RESOLVED_PDF_READER` module constant, a
`_make_file_detail()` helper at a top-level `ingestion.py` that no longer
exists, a `BaseReader` protocol in a `base.py` that was never created, a
deprecated `readers/` shim removed in v2.0.0, and a LiteParse transition
requirement superseded by the core-dependency and auto-default requirements
already in the same file. Each stale line misleads the next reader and makes
honest delta comparisons noisy (AGENTS.md gotcha 12: fix wrong baseline
content instead of working around it).

## What Changes

Spec-only correction of `openspec/specs/pdf-reader/spec.md` to match the
shipped architecture. No runtime code, configuration, or test changes.

- Rewrite the env-var-selection requirement: the accepted value lives in the
  frozen `Settings.pdf_reader` field; `compose.resolve_pdf_reader` produces
  the concrete backend name once at startup; the `RESOLVED_PDF_READER`
  constant and `config.py` resolver-shape scenario are removed.
- Remove the obsolete "default preserved when LiteParse is not installed"
  transition requirement (superseded by the core-dependency and auto-default
  requirements).
- Rewrite the error-dictionary requirement: the ingestion pipeline catches
  per-file failures and converts them through
  `core/ingestion/loader.py:make_file_detail`; adapters raise normally.
- Rewrite the extensibility requirement: new readers are one adapter module
  plus one `registry.register()` call; no `BaseReader` file, no factory map
  edit, no deprecated `readers/` shim.
- Clean the auto-default requirement's `RESOLVED_PDF_READER` phrasing.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pdf-reader`: five requirements rewritten or removed so every scenario
  matches the v2 architecture (settings injection, registry dispatch,
  pipeline-owned error conversion).

## Impact

**Documentation**

- `openspec/specs/pdf-reader/spec.md` only.

**Runtime**

- None. Every scenario describes behaviour the code already exhibits;
  the change alters no code path.
