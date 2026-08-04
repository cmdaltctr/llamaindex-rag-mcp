## Why

ChromaDB is called directly throughout the codebase — collection creation, document writes, queries, dimension locking, and generation bumping are scattered across `core/ingestion/` and `core/retrieval/` with no abstraction. Every future vector store (LanceDB, Qdrant, pgvector) would require surgery in the pipeline code. This is Phase 3 of the five-phase refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §8): design a `VectorStore` abstract interface that honestly captures the ChromaDB behaviours actually in use, make ChromaDB the first implementation, and route all store access through the interface. This is real design work, not folder shuffling — it earns its own ADR (029).

## What Changes

- Create `core/vectordb/base.py` defining the `VectorStore` ABC: collection creation, document write (upsert semantics), query (dense + metadata filter), delete, collection metadata read/write (needed by Phase 4 profile tags), generation bumping.
- Create `core/vectordb/chroma.py` implementing the ABC, absorbing `chroma_utils.py` (49 lines) and the ChromaDB-specific logic currently in the ingestion writer (collection management, `_bump_collection_generation()`, dimension handling).
- The interface explicitly encodes the ChromaDB-specific behaviours in use rather than pretending they don't exist: **dimension locking** at collection creation, **metadata filter syntax** (`where` clause), and **generation bumping** for upsert semantics.
- `config.py` gains `VECTOR_STORE=chroma` (default) as the store selector; `compose.py` constructs the store via the setting.
- `chroma_utils.py` is absorbed into `chroma.py` and removed as a top-level module (it is a migration source, not a target-state file).
- New ADR 029: Vector Store Abstraction Interface — documents the interface design and which ChromaDB behaviours are encoded and why.
- No new vector store implementations in this phase. LanceDB/Qdrant/pgvector are future work that the ABC enables.

## Capabilities

### New Capabilities

- `vectordb-abstraction`: The `VectorStore` abstract contract — the operations every store implementation must provide, the ChromaDB-specific behaviours encoded in the contract (dimension locking, metadata filters, generation bumping), and store selection via configuration.

### Modified Capabilities

None. Store behaviour is unchanged — ChromaDB remains the only implementation and all reads/writes behave identically. Only the call path changes (through the ABC).

## Impact

- **Code**: new `core/vectordb/` (`base.py`, `chroma.py`); `chroma_utils.py` absorbed; ingestion writer and retrieval pipeline call the interface instead of ChromaDB directly; `config.py` gains one setting; `compose.py` wires the store.
- **Tests**: existing tests pass against the ChromaDB implementation; a new integration test verifies the interface contract.
- **Dependencies**: none added or removed.
- **ADRs**: new ADR 029. ADR-003 (ChromaDB) unchanged — ChromaDB stays the default implementation.
- **Downstream**: Phase 4's `ProfileResolver` reads collection metadata through this interface.
- **Risk**: Medium — the interface must capture enough of ChromaDB's behaviour to be useful without leaking ChromaDB assumptions into the ABC.
