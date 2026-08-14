## 1. Baseline and Capability Contract

- [ ] 1.1 Add regression tests proving the current native placeholder delegates to BM25.
- [ ] 1.2 Define the vector-store native sparse query capability and unsupported response.
- [ ] 1.3 Pin current BM25, RRF, mixed-coverage warning, and public result shapes.

## 2. Native Sparse Implementation

- [ ] 2.1 Implement native sparse writes and queries in the ChromaDB adapter.
- [ ] 2.2 Preserve existing collections without sparse vectors and mixed-coverage diagnostics.
- [ ] 2.3 Add native sparse result normalisation to the shared query contract.

## 3. Registry and Resolution

- [ ] 3.1 Add a lazy registry for concrete `bm25` and `native` sparse backends.
- [ ] 3.2 Keep `auto` in the composition root and resolve it to a registered concrete name.
- [ ] 3.3 Route the hybrid pipeline through the registry without inline backend branching.
- [ ] 3.4 Preserve explicit warning-to-BM25 fallback and report the backend that ran.
- [ ] 3.5 Validate the configured backend name against the registered set before any capability probing, replacing `resolve_sparse_backend`'s current behaviour where every non-`bm25`/`auto` value is silently treated as `native` (a typo such as `sparse` must fail startup listing the registered names).

## 4. Calibration and Compatibility

- [ ] 4.1 Compare BM25 and native quality, latency, determinism, and memory on representative corpora.
- [ ] 4.2 Test existing, fully covered, and mixed-coverage collections.
- [ ] 4.3 Confirm base and lowest-direct installations need no new dependency.

## 5. Validation and Documentation

- [ ] 5.1 Document registered sparse backends, `auto` policy, fallback, and migration advice.
- [ ] 5.2 Run strict OpenSpec validation, targeted retrieval/store tests, Ruff, Pyright, and import-linter.
- [ ] 5.3 Ask for approval, then run the full fast suite with branch coverage.
