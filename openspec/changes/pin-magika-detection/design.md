# Design: Pin google-magika as the base content-type detector

## Context

`integrations/magika.py` shells out to a binary named by
`MAGIKA_BINARY` (default `magika`) via `shutil.which` + subprocess. The
architecture deliberately registered no dependency, so the binary was
never present and the suffix fallback was the only path that ever ran
(verified 2026-09-15: not in `pyproject.toml`, `uv.lock`, or `.venv`).
Detection feeds three consumers: the chunking dispatch
(`code/<language>` → AST splitter; `binary/…` → pre-read skip) and the
index identity's `content_type` field, which the unchanged-skip keys on
(`source_state.py:150-153`). TDR-025 (amended) records both facts.

## Goals

- Standard installs classify by content without operator action.
- Existing collections are untouched: no re-ingest, no automatic
  identity churn; affected files rebuild only when next re-ingested AND
  only when their label differs.
- Label-string differences between the Magika taxonomy and the suffix
  map are surfaced before deployment re-ingests, not discovered during
  one.

## Non-Goals

- No change to `integrations/magika.py` (subprocess + `MAGIKA_BINARY`
  override policy stays).
- No batch/server-side detection cache; one subprocess per ingest
  operation remains the cost model.
- No re-labelling of stored rows and no migration.

## Decisions

### D1 — Pip package over system binary

`uv add google-magika` puts a `magika` console script in `.venv/bin`;
`shutil.which("magika")` resolves it under `uv run` with zero
integration-code change. `MAGIKA_BINARY` keeps pointing operators at a
different/external binary when they want one.

### D2 — Detection-only smoke as the deployment guard

`scripts/magika_label_smoke.py` takes paths, runs BOTH the suffix map
and the Magika scan over them (detection only — imports nothing from
the ingestion pipeline beyond `detect_file_types`), and prints a
per-file label comparison plus the would-change count. It refuses to
import `ingest_path_async` (asserted by a test) so the no-re-ingest
constraint is mechanical, not aspirational. Operators run it on a real
corpus before approving any re-ingest window.

### D3 — Version pin and floors

Pin the version in `pyproject.toml`; register a floor in
`tests/test_dependency_floors.py` if the lock gap exceeds the test's
one-minor tolerance (gotcha #13). The Magika label taxonomy is
model-version-dependent — bumping the pin requires re-running the
smoke on a representative corpus (recorded in the ADR's revisit
triggers).

### D4 — Test environment honesty

Existing tests that patch `_is_magika_available` keep working (the
patch target is unchanged). New tests assert the installed-detector
path; they must skip cleanly where the package is absent so the
optional-binary degradation stays testable. The base-suite tripwire
counts re-baseline with the new tests.

## Risks / Trade-offs

- **Taxonomy mismatch → mass rebuild.** If Magika's `group/label`
  strings differ from `_SUFFIX_MAP` for common types, every such file's
  identity changes and the next re-ingest rebuilds it. D2's smoke makes
  this visible before it costs anything; the corpus run in this
  change's verification is the operator's own data.
- **Startup cost.** Model load adds roughly 1-2 s per ingest operation
  (one subprocess). Acceptable against ingestion runs that already
  spend seconds per document; noted in the ADR.
- **onnxruntime weight.** google-magika pulls onnxruntime — already the
  project's sanctioned runtime (no-torch rule) but a real install-size
  increase; the ADR records the trade.
