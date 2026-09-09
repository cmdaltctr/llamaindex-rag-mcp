## Why

The fast suite (`uv run pytest -m "not slow"`) currently fails with 13
pre-existing failures on `feat/improve-rag-input-quality-5`, proven
independent of the ADR-063 promotion by a stash-and-rerun on 2026-09-09
(13 of 14 failures reproduced with the promotion changes reverted). The
failures have three unrelated causes, so none of them can be fixed as a
side effect of the chunking work, and every one of them erodes trust in
the pre-commit gate the repository's own conventions require.

## What Changes

- **Cause 1 — `query_instruction` signature drift (5 failures).** The
  query-embedding-preparation work added a `query_instruction=`
  keyword to the dense query path
  (`src/omrg/core/retrieval/pipeline.py:313`), but the reranker test
  fakes in `tests/test_retrieval.py`
  (`TestRerankReasonDiagnostics`, `TestThresholdFollowsRerankOutcome`)
  still define `_fake()` without that parameter, so every affected test
  dies on `TypeError` before asserting anything. Fix: teach the fakes
  the new kwarg (or accept-and-ignore it, matching whatever the
  production call site passes).
- **Cause 2 — operator `.env` leaking into "fresh" Settings resolution
  (4 failures).** `test_vector_store_defaults` and the Chroma
  fail-closed tests build a fresh `Settings` expecting packaged
  defaults, but the developer's real `.env` (13 `VECTOR_STORE`/`CHROMA`
  lines in this checkout) is picked up, so `vector_store_provenance`
  resolves to `explicit` instead of `default`. Fix: those tests must
  resolve with `_env_file=None` (the pattern
  `test_embedding_tokenizer_settings.py` already uses) or otherwise
  exclude the ambient dotenv file, so suite results stop depending on
  the machine's local configuration.
- **Cause 3 — integration inventory marker drift (2 failures).**
  `tests/test_strategy_registration_inventory.py` pins an integration
  inventory marker declaring 11 `omrg.integrations` modules, but the
  package now contains 18 (the OCR worker and its submodules landed
  after the marker was written). Fix: recount and update the marker and
  its documented module table to match the current disk layout.
- **Cascade — `test_clean_base_tripwire` (1 failure).** This test
  re-runs the base suite as a subprocess and fails while any of the
  above fail. No separate fix; it turns green when causes 1–3 are
  repaired.

No production code changes are expected. If any fix turns out to
require touching production behaviour, that is scope creep and must be
surfaced, not absorbed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change repairs test-suite conformance with already-specified
behaviour; it introduces no requirement changes, so
`.openspec.yaml` sets `skip_specs: true`.

## Impact

- `tests/test_retrieval.py` (5 tests, reranker fake signatures)
- `tests/test_vector_store_defaults.py`, `tests/test_engine.py`,
  `tests/test_legacy_chroma_fail_closed.py` (4 tests, dotenv isolation)
- `tests/test_strategy_registration_inventory.py` (2 tests, marker/table
  recount)
- `tests/test_clean_base_tripwire.py` (cascade, no direct edit expected)
- No runtime code, no dependencies, no configuration semantics change.
