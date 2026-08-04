## 1. Preparation

- [x] 1.1 Create branch `git switch -c feat/phase-3-refactor-vectordb-abstraction` (requires Phase 2 merged)
- [x] 1.2 Baseline: `uv run pytest -m "not slow" --cov=rag_mcp` — record pass/coverage as the phase gate
      (828 passed, 87% overall coverage)
- [x] 1.3 Enumerate every ChromaDB call site across `core/ingestion/`, `core/retrieval/`, and `chroma_utils.py`; freeze the operation list (create, write/upsert, query, delete, metadata read/write, generation bump) in this file

Frozen operation list (from call-site enumeration):
1. Collection creation — `db.get_or_create_collection(name)` (loader.py)
2. Collection access — `db.get_collection(name)` (writer, pipeline, loader, sparse)
3. Document write (upsert via LlamaIndex) — `ChromaVectorStore` + `VectorStoreIndex` (writer.py)
4. Dense query — `collection.query(query_embeddings, n_results, where, include)` (dense.py)
5. Paged metadata read — `collection.get(include=["metadatas"], limit, offset)` (chroma_utils, loader, pipeline, taxonomy)
6. Paged document read — `collection.get(include=["documents","metadatas"], limit, offset)` (sparse.py)
7. Count — `collection.count()` (writer, pipeline, loader, sparse)
8. Count-by-filter — `collection.get(where=..., include=[]).ids` (writer._count_chunks)
9. Delete by filter — `collection.delete(where=...)` (writer)
10. Delete collection — `db.delete_collection(name)` (writer)
11. List collections — `db.list_collections()` (pipeline, taxonomy)
12. Generation bump — process-local counter (writer bumps, sparse reads)
13. Collection metadata read/write — NEW (Phase 4 profile tags depend on this)

## 2. VectorStore ABC

- [x] 2.1 Create `core/vectordb/base.py` with the `VectorStore` ABC covering the frozen operation list from 1.3, including collection metadata read/update (Phase 4 profile tags depend on this)
- [x] 2.2 Document dimension locking, metadata filter translation, and generation bumping as contract behaviour in the ABC docstrings
- [x] 2.3 Write an integration test (`tests/test_vectordb_contract.py`) exercising every ABC method against an implementation — fails until `chroma.py` exists

## 3. ChromaDB implementation

- [x] 3.1 Create `core/vectordb/chroma.py` implementing the ABC
- [x] 3.2 Absorb all `chroma_utils.py` logic into `chroma.py`
- [x] 3.3 Move collection management and `_bump_collection_generation()` from the ingestion writer into `chroma.py`, preserving exact upsert semantics
- [x] 3.4 Move dimension-lock handling (fixed dims at creation, clear error on mismatch) into `chroma.py`
- [x] 3.5 Move metadata filter (`where` clause) translation into `chroma.py`
- [x] 3.6 Make the contract integration test pass
- [x] 3.7 Delete `chroma_utils.py` and update its callers in the same commit (internal helper — no compat shim)

## 4. Wiring and selection

- [x] 4.1 Add `VECTOR_STORE` setting to `config.py` (default `chroma`) with a clear startup error for unknown values listing available implementations
- [x] 4.2 Construct the store in `compose.py` from the setting and inject it into the ingestion writer and retrieval pipeline
- [x] 4.3 Remove all direct ChromaDB client usage from `core/ingestion/` and `core/retrieval/` (grep gate: zero direct usage outside `core/vectordb/`)
- [x] 4.4 Verify existing `output/chroma_*` collections open, read, and query with no data migration

## 5. Acceptance and wrap-up

- [x] 5.1 Run `uv run pytest -m "not slow" --cov=rag_mcp` — all pre-existing tests green with no assertion changes; coverage thresholds hold
      (852 passed, 87% overall — no regression from baseline)
- [x] 5.2 Write ADR 029 (Vector Store Abstraction Interface) recording the contract, the encoded ChromaDB behaviours, and the rejected minimal-interface alternative
      (Renumbered to ADR-034 — 029–033 landed before Phase 3)
- [x] 5.3 Update `docs/guides/architecture.md` with the vectordb layer
- [x] 5.4 Run `openspec validate phase-3-refactor-vectordb-abstraction --strict`
- [x] 5.5 Run `graphify update .`
- [ ] 5.6 Commit (`refactor:`) and open PR with `gh pr create --base main`
