## 1. Preparation

- [ ] 1.1 Create branch `git switch -c feat/phase-3-refactor-vectordb-abstraction` (requires Phase 2 merged)
- [ ] 1.2 Baseline: `uv run pytest -m "not slow" --cov=rag_mcp` — record pass/coverage as the phase gate
- [ ] 1.3 Enumerate every ChromaDB call site across `core/ingestion/`, `core/retrieval/`, and `chroma_utils.py`; freeze the operation list (create, write/upsert, query, delete, metadata read/write, generation bump) in this file

## 2. VectorStore ABC

- [ ] 2.1 Create `core/vectordb/base.py` with the `VectorStore` ABC covering the frozen operation list from 1.3, including collection metadata read/update (Phase 4 profile tags depend on this)
- [ ] 2.2 Document dimension locking, metadata filter translation, and generation bumping as contract behaviour in the ABC docstrings
- [ ] 2.3 Write an integration test (`tests/test_vectordb_contract.py`) exercising every ABC method against an implementation — fails until `chroma.py` exists

## 3. ChromaDB implementation

- [ ] 3.1 Create `core/vectordb/chroma.py` implementing the ABC
- [ ] 3.2 Absorb all `chroma_utils.py` logic into `chroma.py`
- [ ] 3.3 Move collection management and `_bump_collection_generation()` from the ingestion writer into `chroma.py`, preserving exact upsert semantics
- [ ] 3.4 Move dimension-lock handling (fixed dims at creation, clear error on mismatch) into `chroma.py`
- [ ] 3.5 Move metadata filter (`where` clause) translation into `chroma.py`
- [ ] 3.6 Make the contract integration test pass
- [ ] 3.7 Delete `chroma_utils.py` and update its callers in the same commit (internal helper — no compat shim)

## 4. Wiring and selection

- [ ] 4.1 Add `VECTOR_STORE` setting to `config.py` (default `chroma`) with a clear startup error for unknown values listing available implementations
- [ ] 4.2 Construct the store in `compose.py` from the setting and inject it into the ingestion writer and retrieval pipeline
- [ ] 4.3 Remove all direct ChromaDB client usage from `core/ingestion/` and `core/retrieval/` (grep gate: zero direct usage outside `core/vectordb/`)
- [ ] 4.4 Verify existing `output/chroma_*` collections open, read, and query with no data migration

## 5. Acceptance and wrap-up

- [ ] 5.1 Run `uv run pytest -m "not slow" --cov=rag_mcp` — all pre-existing tests green with no assertion changes; coverage thresholds hold
- [ ] 5.2 Write ADR 029 (Vector Store Abstraction Interface) recording the contract, the encoded ChromaDB behaviours, and the rejected minimal-interface alternative
- [ ] 5.3 Update `docs/guides/architecture.md` with the vectordb layer
- [ ] 5.4 Run `openspec validate phase-3-refactor-vectordb-abstraction --strict`
- [ ] 5.5 Run `graphify update .`
- [ ] 5.6 Commit (`refactor:`) and open PR with `gh pr create --base main`
