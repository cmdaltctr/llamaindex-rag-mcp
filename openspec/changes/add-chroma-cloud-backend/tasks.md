## 1. Configuration contract (test first)

- [ ] 1.1 Write failing tests for `CHROMA_MODE` default `local`, explicit `cloud`, and rejection of unknown values
- [ ] 1.2 Write failing tests: cloud mode requires `CHROMA_CLOUD_API_KEY`; tenant/database are supplied together or both omitted
- [ ] 1.3 Write failing tests that cloud credentials never appear in settings/runtime summaries or validation messages
- [ ] 1.4 Add the four Chroma settings to the typed config model; keep YAML defaults secret-free
- [ ] 1.5 Add `.env.example` entries with local-default and cloud setup guidance (no real credentials)
- [ ] 1.6 Extend config source/coverage and no-secret contract tests for the new variables

## 2. Chroma client injection and composition

- [ ] 2.1 Write failing tests: `ChromaVectorStore` accepts an injected `ClientAPI` and uses it for every collection operation
- [ ] 2.2 Write failing tests: local mode constructs `PersistentClient(path=...)`; cloud mode constructs `CloudClient` with exact key/tenant/database arguments
- [ ] 2.3 Write failing tests: cloud connection validation occurs before default-store registration; authentication/network errors propagate without local fallback
- [ ] 2.4 Add optional client injection to `ChromaVectorStore`; preserve direct-call local lazy fallback for tests/library callers
- [ ] 2.5 Extend `build_chroma_vector_store` to construct and validate local/cloud clients inside `core/vectordb/chroma.py`
- [ ] 2.6 Update `compose.build_vector_store(settings)` to pass resolved storage values instead of discarding settings
- [ ] 2.7 Assert `core/vectordb/chroma.py` remains the only production `chromadb` import/construction site

## 3. Cloud behaviour and security

- [ ] 3.1 Test parity for collection lifecycle, dense query result shape, metadata filters, deletes, and dimension mismatch using fake local/cloud clients
- [ ] 3.2 Test runtime summary exposes mode and optional identifiers but never API-key content or prefix
- [ ] 3.3 Test explicit cloud failure leaves the process default vector store unset
- [ ] 3.4 Test all four compute/storage combinations resolve independently; no `hybrid` selector is introduced
- [ ] 3.5 Add collection identity metadata (provider, model, immutable index hash) with read-merge-write preservation of existing profile metadata
- [ ] 3.6 Test identity mismatch rejection for same-dimension models and compatible collection reuse
- [ ] 3.7 Document one-writer-per-collection BM25 boundary; test immutable-index collection naming helper
- [ ] 3.8 Add an opt-in Chroma Cloud smoke script (disposable collection; ingest, query, delete; checkpoint/log redaction)

## 4. Calibration harness migration

- [ ] 4.1 Inventory raw Chroma/config access in experiments 10b, 10.1, 12, 9a-rerun, 13, and 14; map each operation to the `VectorStore` ABC
- [ ] 4.2 Write focused tests for a shared experiment storage configuration helper (mode, collection ID, resume metadata, secret exclusion)
- [ ] 4.3 Migrate experiments 10b, 12, and 9a-rerun from env/module-constant patches to the production store construction path
- [ ] 4.4 Migrate experiments 10.1, 13, and 14 away from direct `PersistentClient`; use ABC reads/writes or add one verified minimal contract method
- [ ] 4.5 Generate deterministic collection names from experiment ID, corpus/config identity, provider/model, parser, and chunking config; obey Chroma naming rules
- [ ] 4.6 Build each immutable index once; retrieval-only cells/repetitions reuse it read-only, with run IDs kept in checkpoint/result metadata
- [ ] 4.7 Preserve local output directories and `--resume`; cloud checkpoints store identifiers/provider/model but no key
- [ ] 4.8 Mutation-check one runner: broken mode selection, identity guard, or index-reuse mapping makes the focused test fail

## 5. Documentation and decision record

- [ ] 5.1 Load `s-adr`; create the next ADR for hosted Chroma experiment storage, strict explicit selection, and the sparse-cache boundary
- [ ] 5.2 Update configuration, architecture, testing, and experiment guides; reuse upstream LlamaIndex client-injection pattern references
- [ ] 5.3 Add the agreed four-mode deployment matrix and independent selector examples to the configuration/experiment guide
- [ ] 5.4 Update `experiments/EXP_README.md` with cloud execution prerequisites, immutable-index reuse, and cost/reproducibility notes
- [ ] 5.5 Record that OpenRouter supplies embeddings while Chroma Cloud stores vectors; Fireworks needs a future provider adapter and is not a vector store
- [ ] 5.6 Record re-ingestion requirement when changing embedding provider/model, corpus/parser/chunking identity, or dimension

## 6. Verification

- [ ] 6.1 Run focused config, composition, vector-store, redaction, and migrated experiment tests
- [ ] 6.2 Run `uv run lint-imports`; all import-linter contracts must remain kept with no stale ignore entries
- [ ] 6.3 Run `uv run ruff check` and `ruff format --check`
- [ ] 6.4 Run `openspec validate add-chroma-cloud-backend --strict`
- [ ] 6.5 Run `graphify update .`
- [ ] 6.6 Obtain approval, then run `uv run pytest -m "not slow" --cov=rag_mcp --cov-branch`
- [ ] 6.7 With user-provided credentials, run the opt-in disposable cloud smoke (never in CI); delete its collection after verification
