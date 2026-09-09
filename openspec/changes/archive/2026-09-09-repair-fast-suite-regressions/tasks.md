## 1. Signature drift (cause 1)

- [x] 1.1 Read the production call site (`src/omrg/core/retrieval/pipeline.py`, the `_dense_query_rows` invocation that passes `query_instruction=`) and record the exact keyword set the fakes must accept.
- [x] 1.2 Update the reranker test fakes in `tests/test_retrieval.py` (`TestRerankReasonDiagnostics`, `TestThresholdFollowsRerankOutcome`) to accept the full signature per design D1. Run the five failing tests; confirm they pass on values, not just signatures.
- [x] 1.3 If any of the five fails on values after the signature fix, stop and report: that indicates a production defect in the query-embedding-preparation work, not test drift.

## 2. Dotenv isolation (cause 2)

- [x] 2.1 Add a `_fresh_get_settings`-equivalent that resolves with `_env_file=None` (or pass `_env_file=None` at each construction site) in `tests/test_vector_store_defaults.py`, `tests/test_engine.py`, and `tests/test_legacy_chroma_fail_closed.py`, per design D2. Do not touch tests that intentionally exercise dotenv loading.
- [x] 2.2 Confirm the four previously failing tests pass with the real operator `.env` still present in the checkout (that file is the reproduction case; do not delete it).

## 3. Inventory recount (cause 3)

- [x] 3.1 Run the discovery command `tests/test_strategy_registration_inventory.py` uses; generate the actual 18-module list of `omrg.integrations*`.
- [x] 3.2 Update the marker declaration and the documented module table to the discovered layout per design D3. Confirm both `test_integration_inventory_table_matches_disk` and `test_integration_inventory_marker_count_agrees` pass.

## 3b. Reader-seam drift (the unaccounted 13th failure)

The proposal counted 13 pre-existing failures but enumerated only 12
(5 + 4 + 2 + 1). The remaining one, diagnosed during acceptance, is
`tests/unit/test_ingestion_pdf_extractor.py::TestChunkerThreadsReaderName::
test_chunker_passes_resolved_reader_to_factory`: the ingestion path now
calls `build_pdf_reader(reader, settings, ocr_client=)`
(`core/ingestion/backends/local.py`) while the test still patches the
retired `get_pdf_reader` facade seam, so its stub is never invoked.
Same drift family as cause 1; test-only repair, assertion unchanged.

- [x] 3b.1 Update the test to patch `omrg.integrations.pdf.build_pdf_reader` with the full production signature; confirm it passes on values.

## 3c. Optional-adapter collection stability

CI uses a bare frozen sync. Exp25’s installed-adapter contract needs the
optional OpenAI-like embedding package for two parameter cases. It must
skip those cases when absent, then let the clean-base tripwire pin either
supported dependency set explicitly.

- [x] 3c.1 Make the Exp25 adapter test skip only when its optional package is absent, while retaining its installed-adapter assertions.
- [x] 3c.2 Pin clean-base counts for both bare CI and optional-adapter environments; confirm the tripwire passes in bare CI.

## 4. Acceptance

- [x] 4.1 Run `test_clean_base_tripwire` alone and confirm it passes unchanged (design D4 — no edit expected).
- [x] 4.2 Run the full fast suite `uv run pytest -m "not slow" --cov=omrg --cov-branch` on a machine with the operator `.env` present; zero failures, coverage floors hold.
- [x] 4.3 Sanity-run the same suite with the ambient `.env` temporarily renamed (restored immediately after) to prove CI-equivalence; zero failures.
