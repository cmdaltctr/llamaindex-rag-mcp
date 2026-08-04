# ADR-034: Phase 3 Refactor — Vector Store Abstraction Interface

**Date:** 2026-08-04
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `phase-3-refactor-vectordb-abstraction`
**Amends:** ADR-003 (ChromaDB stays the default implementation; the ABC sits in front of it)
**Phase:** 3 of 5 (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §5.2, §8)

> **Numbering note.** The proposal called this "ADR 029" based on the
> pre-refactor numbering. ADRs 029–033 landed before Phase 3, so the next
> available number is 034.

## Context

Before this change, ChromaDB was called directly throughout the pipeline.
Collection creation, document writes, queries, dimension locking,
generation bumping, and paged metadata scans were scattered across
`core/ingestion/` (writer, loader), `core/retrieval/` (pipeline, dense,
sparse), and `core/metadata/` (taxonomy), with a shared helper
(`chroma_utils.py`) that 49 lines of paging logic. Every future vector
store (LanceDB, Qdrant, pgvector) would require surgery in the pipeline
code itself.

Phase 3 is the only phase of the five-phase refactor that introduces a
genuinely new abstraction. The design risk is honest scope: capture
what ChromaDB actually does for the pipeline without inventing a fantasy
of store-portability that has not been earned by a second implementation.

## Decision

Introduce a `VectorStore` ABC (`core/vectordb/base.py`) that covers every
vector-store operation the pipeline uses, and make ChromaDB the first
implementation (`core/vectordb/chroma.py`). All pipeline code accesses
the store through the interface — never through ChromaDB APIs directly.

### D1: Encode ChromaDB behaviours, don't hide them

The ABC documents three ChromaDB-specific behaviours the pipeline
depends on as contract-level surface, not hidden implementation detail:

* **Dimension locking** — the vector dimension is fixed when the first
  document is written to a collection. Subsequent writes with a
  different dimension raise a clear error (ChromaDB dim-lock, ADR-003).
  The ABC does not take a dimension parameter at creation time because
  ChromaDB infers it from the first write.
* **Metadata filter syntax** — the `where` parameter on query/delete
  follows the ChromaDB filter shape (`{"category": "AI"}`,
  `{"$and": [...]}`). The ABC passes it through; a future store
  implementation translates it to its native filter representation.
* **Generation bumping** — every write or delete advances a
  process-local generation counter so the BM25 sparse retriever knows
  when to rebuild its in-memory index. The counter moved from
  `core/ingestion/_state.py` into the store instance so the store owns
  the write→invalidate contract end-to-end.

**Rejected alternative:** a minimal "ideal" interface (put/get/delete)
that treats these as ChromaDB quirks. The pipeline depends on all three;
pretending otherwise produces an interface that leaks on first
alternative implementation.

### D2: Collection metadata is part of the contract

The ABC includes `get_collection_metadata` and
`update_collection_metadata`. This is load-bearing for Phase 4: profile
tags live in collection metadata (`metadata={"profile": "codebase"}`)
and `ProfileResolver` reads them through the store. Designing the ABC
without it would force a Phase 4 interface revision.

ChromaDB's `collection.modify(metadata=...)` replaces the entire dict
rather than merging, so the implementation does a read-merge-write to
preserve keys not present in the update.

### D3: `chroma_utils.py` is absorbed, not shimmed

The 49-line `chroma_utils.py` (paged metadata scans) merged into
`chroma.py`'s `iter_metadatas` and `iter_documents` methods. No compat
shim is kept because it was an internal helper, not a public import
surface (unlike the Phase 1 modules). Its callers (loader, pipeline,
taxonomy, sparse) moved to the store interface in the same change.

### D4: Construction in compose, selection in config

`VECTOR_STORE` (default `chroma`) resolves in `config.py`; the Settings
validator rejects unknown values with a clear error listing available
implementations. `compose.py` constructs the implementation via
`build_vector_store` and registers it as the process-wide default store
in `ensure_runtime_setup`. Pipeline functions accept an optional
`store: VectorStore | None = None` parameter that falls back to the
default — this follows the Phase 2 DI discipline (the pipeline never
constructs or imports ChromaDB) while keeping `server.py` and `cli.py`
call sites unchanged.

### D5: The write path goes through LlamaIndex

The `write_nodes` method embeds and writes LlamaIndex `TextNode` objects
via `ChromaVectorStore` + `VectorStoreIndex`, using the LlamaIndex
global `Settings.embed_model` assigned by `compose.ensure_runtime_setup`.
This couples the ChromaDB implementation to LlamaIndex, which is
acceptable because (a) LlamaIndex is already a hard dependency and (b)
the ABC surface stays store-agnostic — a future non-LlamaIndex store
would implement `write_nodes` differently.

## Consequences

### Positive

* All ChromaDB imports are now confined to `core/vectordb/chroma.py`.
  The grep gate (`import chromadb` in `core/ingestion/` or
  `core/retrieval/`) returns zero hits.
* Adding a second store implementation (LanceDB, Qdrant, pgvector)
  costs one new file plus one `build_vector_store` branch — no pipeline
  edits.
* The generation counter is owned by the store instance, so the
  write→invalidate contract is structurally connected rather than
  spread across `_state.py` (writer) and `sparse.py` (reader).
* Collection metadata read/update is available for Phase 4 profile tags
  without an interface change.
* The contract integration test (`tests/test_vectordb_contract.py`)
  exercises every ABC method against the ChromaDB implementation, giving
  a second implementation a ready-made conformance suite.

### Negative

* The ABC leaks ChromaDB assumptions anyway — the `where` clause shape
  and the generation counter are ChromaDB-flavoured. A second
  implementation is the real test and will amend this ADR if the
  assumptions prove wrong.
* The `store=None` default in pipeline functions is a hidden dependency
  on the process-wide singleton. Tests that need a fresh store must call
  `reset_default_store()` (added to `conftest._patch_chromadb`).
* `BM25SparseRetriever`'s constructor changed from `collection=` to
  `store=`, requiring test updates. The assertions themselves are
  unchanged; only the construction and generation-counter access
  patterns moved.

### Neutral

* The `VECTOR_STORE` env var is new but defaults to `chroma`, so
  existing deployments are unaffected.
* `codebase_map.py` still imports `chromadb` directly — it is out of
  scope for this phase (not a pipeline module). A future phase may route
  it through the store.

## Alternatives Considered

| Option | Rejected Because |
| ------ | ---------------- |
| **Minimal put/get/delete interface** | The pipeline depends on dimension locking, metadata filters, and generation bumping. Hiding them produces an interface that leaks on first alternative implementation (D1). |
| **Keep `chroma_utils.py` as a compat shim** | It was an internal helper with no external consumers. Shimming it would leave dead code until v2.0.0 (D3). |
| **Abstract the LlamaIndex write path too** | LlamaIndex is a hard dependency and the `ChromaVectorStore` adapter is the only sane way to embed+write nodes. Pushing LlamaIndex out of the ABC would add complexity with no benefit until a non-LlamaIndex store exists. |
| **No collection metadata in the ABC** | Phase 4's `ProfileResolver` needs it. Adding it later would force an interface revision (D2). |
| **Keep the generation counter in `_state.py`** | The counter is tied to write/upsert semantics, which are the store's responsibility. Keeping it in a separate module splits the write→invalidate contract across two files. |

## References

- Design doc: [`openspec/changes/archive/2026-08-04-phase-3-refactor-vectordb-abstraction/design.md`](../../openspec/changes/archive/2026-08-04-phase-3-refactor-vectordb-abstraction/design.md) (decisions D1–D4)
- Proposal: [`openspec/changes/archive/2026-08-04-phase-3-refactor-vectordb-abstraction/proposal.md`](../../openspec/changes/archive/2026-08-04-phase-3-refactor-vectordb-abstraction/proposal.md)
- Refactor proposal: [`docs/brainstorm/refactor-proposal/PROPOSAL.md`](../brainstorm/refactor-proposal/PROPOSAL.md) (§5.2 vectordb, §8)
- [ADR-003](./003-use-chromadb-as-vector-store.md) — Use ChromaDB as Vector Store (unchanged: ChromaDB stays the default)
- [ADR-031](./031-three-layer-config-compose-di.md) — Three-Layer Architecture (the composition root constructs the store)
- `src/rag_mcp/core/vectordb/base.py` — `VectorStore` ABC
- `src/rag_mcp/core/vectordb/chroma.py` — ChromaDB implementation
- `src/rag_mcp/compose.py` — `build_vector_store` factory
- `tests/test_vectordb_contract.py` — contract integration test
