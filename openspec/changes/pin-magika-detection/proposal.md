# Proposal: Pin google-magika as the base content-type detector

## Why

The architecture treats Magika as an optional external executable, so it
was never pinned and — verified 2026-09-15 — has never been installed on
any machine this project ran on. Every ingestion ever executed used the
suffix fallback. Detection drives chunking dispatch (mislabelled code
files lose AST splitting) and the early binary skip (junk files reach the
reader as errors), so the optional-binary design silently disabled both
powers that justified the integration (TDR-025 amendment). Pinning the
official `google-magika` package makes the base install detect by
content, not by filename.

## What Changes

- Add `google-magika` as a base dependency (`uv add google-magika`),
  version-pinned in `pyproject.toml` and `uv.lock`.
- No integration code change: the existing subprocess call resolves
  `MAGIKA_BINARY=magika` to the venv's console script under
  `uv run`; the suffix fallback remains for bare-environment runs.
- Add a detection-only label-equivalence smoke tool that compares
  suffix-map labels against Magika labels over operator-supplied paths.
  It MUST NOT ingest, embed, or touch any collection — no
  `ingest_path_async`, no store access. Label-string stability matters
  because the unchanged-skip keys on the content-type label
  (TDR-025 amendment): matching labels mean existing rows skip on next
  re-ingest at zero cost; differing labels rebuild only the affected
  files.
- Record the dependency decision as an ADR (new base dependency;
  onnxruntime-based, consistent with the no-torch rule) and update the
  dependency-floors test if the new package requires a floor entry.
- **No re-ingest is performed by this change.** Identity shifts affect
  only future ingests, file by file, and only where the label differs.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `type-aware-ingestion`: adds a requirement that the base install
  performs content-based detection through the pinned Magika package,
  with the label-equivalence smoke as the deployment guard.

## Impact

- Code: `pyproject.toml`, `uv.lock`, new smoke script, floors test,
  ADR. `integrations/magika.py` unchanged.
- Dependencies: `google-magika` (pulls `onnxruntime`; no torch).
  Startup cost: one subprocess per ingest operation, model load
  roughly 1-2 s.
- Index identity: files whose Magika label differs from their suffix
  label rebuild on their NEXT re-ingest (correct staleness); identical
  labels skip. Nothing re-ingests automatically.
- CI: the base-suite tripwire executed/skipped counts shift with new
  tests; magika-dependent tests that currently assert the fallback path
  must be reviewed for environment assumptions.
