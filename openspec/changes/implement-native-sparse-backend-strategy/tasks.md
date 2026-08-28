## 0. Locked-version FTS contract and feasibility (pre-implementation)

> Must complete before any production code changes. `compose.py` (497),
> `lancedb.py` (497), and `chroma.py` (499) are at the 500-line ceiling;
> tasks adding adapter code land it in focused seam modules (following
> `lance_rows.py`), not inline growth. Sequence this change after
> `validate-embedding-write-contract` and not concurrently with
> `register-document-backend-strategies` or
> `add-per-collection-persist-dirs` (shared `compose.py` / adapter
> files).

- [ ] 0.1 Write a pre-implementation contract/feasibility test against the locked `lancedb` 0.37.1 / `pylance` 10.0.0 covering: native FTS on the `text` column (index configuration and `"fts"` search), metadata filtering combined with FTS, returned row/result shape, score semantics, refresh/freshness behaviour after writes, partial index coverage (indexed vs unindexed rows), and fallback signalling to BM25. This test pins the API surface so a dependency bump that changes it fails loudly.

## 1. Baseline and Capability Contract

- [x] 1.1 Add regression tests proving the current native placeholder delegates to BM25.
  > Already satisfied at v3: `test_native_sparse_placeholder_falls_back_to_bm25_not_dense_only` (tests/test_hybrid_retrieval.py:988) pins the placeholder warning-and-delegate behaviour against `_native_sparse_query` in `core/retrieval/pipeline.py`.
- [ ] 1.2 Define the vector-store native sparse query capability and unsupported response.
- [x] 1.3 Pin current BM25, RRF, mixed-coverage warning, and public result shapes.
  > Already satisfied at v3 by tests/test_hybrid_retrieval.py: BM25 ranking/caching/filtering (tests at lines 229–453), RRF worked examples (178–213), mixed-coverage one-shot warning and paged metadata scan (882, 939, 1054), public shape stripping and experiment diagnostics (779, 833). Extend only where the corrected delta adds new behaviour.

## 2. Native Sparse Implementation (LanceDB native FTS)

- [ ] 2.1 Implement native sparse writes/queries in the LanceDB adapter over a native FTS index on the `text` column (not `documents`; the schema in `core/vectordb/lance_rows.py` stores text as `text`), with additive, explicitly triggered index creation. Land adapter code in a focused seam module.
- [ ] 2.2 Preserve existing collections without FTS indexes and mixed-coverage diagnostics restated for indexed vs unindexed rows.
- [ ] 2.3 Add native sparse result normalisation to the shared query contract.
- [ ] 2.4 Implement the FTS lifecycle as its own behaviour per design decision 4: initial creation; stale marking and refresh after writes, replacements, and deletions; freshness diagnostics distinct from indexed-versus-unindexed coverage; rejection of stale native results; failure and fallback diagnostics. Do NOT use the process-local store generation counter as durable FTS-index maintenance — it remains a BM25 cache-invalidation mechanism only (PR #63 semantics unchanged).

## 3. Registry and Resolution

- [ ] 3.1 Add a lazy registry for concrete `bm25` and `native` sparse backends.
- [ ] 3.2 Keep `auto` in the composition root and resolve it to a registered concrete name through the selected store's registry metadata plus a real native-FTS probe, replacing the Chroma-specific `detect_native_sparse_capability` route.
- [ ] 3.3 Route the hybrid pipeline through the registry without inline backend branching.
- [ ] 3.4 Preserve explicit warning-to-BM25 fallback and report the backend that ran through the existing effective-backend diagnostic surface (do not duplicate PR #63's diagnostics requirement).
- [ ] 3.5 Move accepted sparse-backend name validation from the hard-coded settings tuple (`config/__init__.py` already rejects unknown `RETRIEVAL__HYBRID_SPARSE_BACKEND` values against `("auto", "native", "bm25")`) to composition-boundary validation backed by the concrete registry. Keep `auto` as a separately accepted policy name and list it with the registered concrete names on failure. `config/` must not import the runtime registry (leaf invariant; `community_algorithm` precedent).

## 4. Calibration and Compatibility

- [ ] 4.1 Compare BM25 and native quality, latency, determinism, and memory on representative corpora. D17 (archived Stage 6, complete) shows hybrid beats dense with reranking disabled; it does not prove native FTS beats BM25 — this experiment is the evidence for that question.
- [ ] 4.2 Test existing (no FTS index), fully covered, and mixed-coverage collections.
- [ ] 4.3 Confirm base and lowest-direct installations need no new dependency.

## 5. Validation and Documentation

- [ ] 5.1 Document registered sparse backends, `auto` policy, fallback, the FTS lifecycle contract, and migration advice.
- [ ] 5.2 Run strict OpenSpec validation, targeted retrieval/store tests, Ruff, Pyright, and import-linter.
- [ ] 5.3 Ask for approval, then run the full fast suite with branch coverage.
