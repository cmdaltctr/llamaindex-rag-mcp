# ADR-046: LanceDB as the Second Vector-Store Backend

**Date:** 2026-08-17
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The `VectorStore` ABC (`core/vectordb/base.py`, ADR-034) was written so a
second store could sit behind the same interface. Its docstring names
LanceDB, Qdrant, and pgvector as intended future implementations, yet only
ChromaDB existed when this change began.

`compose.py` selected the store with `if settings.vector_store == "chroma"`.
That is a branch over a strategy name, which architecture invariant #10
forbids ("Registries are the dispatch mechanism ... MUST NOT branch if/elif
over strategy names"). The registry pattern already existed in
`core/retrieval/registry.py`, so extending it was the house convention
rather than a new invention.

The multi-agent stdio workload wants per-collection on-disk isolation.
ChromaDB keeps every collection in one shared SQLite file per persist
directory, so parallel writers contend on the write lock. LanceDB gives
each collection its own table and files with optimistic concurrency.

LlamaIndex ships a maintained `llama-index-vector-stores-lancedb`
integration, so the embedding and write path reuses the LlamaIndex
machinery the ChromaDB store already uses.

## Decision

1. **Adopt LanceDB (embedded, local-first) as the second backend** through
   `llama-index-vector-stores-lancedb`. One `lancedb.connect(uri)`
   connection backs the store; each RAG collection maps to one LanceDB
   table, mirroring how `ChromaVectorStore` holds one client and drives
   many collections (DD4).

2. **Create tables lazily.** LanceDB cannot create a table without data or
   a schema, so the vector dimension is fixed on first write — the same
   create-on-first-write and dimension-lock behaviour as ChromaDB
   (ADR-003). `create_collection` records intent in a process-local set
   until the first write materialises the table.

3. **Select the store through a registry.** `core/vectordb/registry.py`
   registers `chroma` and `lancedb` lazily under their configured names
   (`"module:attr"` import strings). `compose.build_vector_store` resolves
   the configured name through the registry; an unregistered name raises
   a `ValueError` listing the registered names at startup. This replaces
   the branch and satisfies invariant #10 (DD3).

4. **Translate filters through a type-safe seam.** `lance_filter.py`
   translates the ChromaDB-style `where` dict (the shape the MCP
   `search_documents` tool advertises) into a LanceDB filter string.
   Values never travel as interpolated client input (DD2; see the
   verified facts below).

5. **Read collections in pages over the LanceDB scanner.**
   `lance_paged.py` provides `iter_metadatas`, `iter_documents`, and
   `fetch_all` over `table.search().select().limit().offset()`,
   `to_arrow()`, and `count_rows()`, and strips the adapter's internal
   metadata keys from rows (DD4).

6. **Keep collection metadata in durable table metadata.** Profile tags
   and the embedding-identity triple live in the table's Arrow schema
   metadata, written read-merge-write behind `core/vectordb/lance_meta.py`
   (DD1; see the verified facts below).

7. **Keep hybrid retrieval on the existing BM25 path.** The in-memory
   sparse retriever reads rows through `iter_documents` and invalidates
   off the generation counter, so it works over LanceDB unchanged. No
   native LanceDB full-text index is built in v1 (DD5).

### Verified build-session facts

The proposal and `design.md` recorded soft guesses for two decisions. The
build session verified them against lancedb 0.37.1, pylance 10.0.0, and
`llama-index-vector-stores-lancedb` 0.5.0. These findings override the
earlier guesses:

- **The Python SDK has no table `update_config` and no Table-level
  `replace_schema_metadata`.** Schema metadata is creation-time only
  through the public API. The durable post-creation key-value bag is
  pylance's `LanceDataset.update_schema_metadata(values, replace=False)`
  — merge semantics, survives close/reopen and adapter writes — reached
  via `table.to_lance()` behind `core/vectordb/lance_meta.py`. This is
  the DD1 fallback branch in effect.
- **`lancedb.expr` (`col`, `lit`) exists but has no struct field access,
  and `count_rows(filter=)` accepts SQL strings only.** The translator
  serialises every value through `lit(value).to_sql()` — the engine's own
  unparser, verified to escape single quotes — validates field names
  against `^[A-Za-z_][A-Za-z0-9_-]*$`, backtick-quotes every emitted
  identifier (unquoted, a hyphen-bearing name parses as subtraction),
  and composes with a fixed operator vocabulary. Injection-safe by
  construction; a decoy test proves it.
- **SQL NULL semantics diverge from ChromaDB missing-key semantics, and
  the planner rejects schema-absent struct fields.** ChromaDB treats a
  key a row lacks as "not equal"; SQL comparisons against NULL are
  unknown and silently drop such rows, and DataFusion raises
  "Field ... not found in struct" for a field the schema lacks. The
  translator is therefore null-aware — `$ne`/`$nin` emit an explicit
  `OR ... IS NULL` — and the store passes the table's metadata field
  names so schema-absent fields fold to the ChromaDB constants
  (`false` for equality/membership/comparisons, `true` for
  `$ne`/`$nin`) instead of reaching the planner. A cross-backend
  contract test pins the parity.
- **LanceDB fixes the Arrow `metadata` struct on the first write, and
  pylance 10 has no nested `add_columns`** (dotted paths are rejected
  by lance-core: "Top level field ... cannot contain `.`"). A later
  write introducing new metadata keys therefore cannot grow the struct
  in place: without help, a node write fails ("field does not exist in
  table schema") and a precomputed upsert silently drops the key.
  `lance_meta.evolve_metadata_fields` rebuilds the table — read every
  row, cast to the expanded schema (old rows gain nulls), overwrite in
  place — carrying the schema metadata bag across the rewrite. The
  adapter's internal struct keys are added alongside user keys so
  adapter writes into upsert-created tables succeed. Cost: one full
  table rewrite per key-set expansion, and the table's Lance version
  history restarts at the rewrite; both accepted for correctness over
  incremental ingestion (found in review; fixed on this branch).
- **The LlamaIndex adapter's `mode` defaults to `"overwrite"`.** The store
  passes `mode="create"` and redirects stdout during writes because the
  adapter prints a notice when it lazily creates a table — stdout is the
  MCP protocol channel and must stay clean.
- **The adapter writes user metadata inside an Arrow struct.** Internal
  keys (`_node_content`, `_node_type`, `document_id`, `doc_id`,
  `ref_doc_id`) share the struct with the user's keys; reads strip them
  through `lance_paged.strip_internal_metadata`.
- **The dependency tree adds `lancedb`, `pylance`, `pyarrow`, `tantivy`,
  and `lance-namespace` only.** No PyTorch reaches the base install; the
  ONNX-only boundary holds. `lancedb>=0.37` is pinned because it
  guarantees `lancedb.expr` (the adapter's own floor `>=0.21.1` does
  not). `pyarrow>=25` and `pylance>=10` are declared directly — the
  store builds upsert rows with pyarrow and calls pylance's
  `update_schema_metadata`, but the adapter pulls pylance with no
  version constraint — and both are floored at the locked major: their
  frequent major bumps carry no semantic signal, so floor equals lock.

### Deferred work (recorded, not built)

From `design.md`. Recorded here so a future change knows these were
considered and parked:

1. **`lancedb-native-fts-hybrid`** — LanceDB's native BM25 full-text index
   and hybrid search (`query_type="hybrid"`, default RRF reranker). Needs
   an FTS-index lifecycle (build, rebuild on write) and a calibration
   experiment comparing RRF against this repo's cross-encoder reranker
   (ADR-031). Own change, own experiment.
2. **LanceDB Cloud / remote tables** — a connection-type-selected
   escaped-SQL-string filter fallback at the `lance_filter.py` seam plus
   remote-safe read paths. The embedded contract stays the default.
3. **Shared generation-counter helper** — hoist the process-local
   generation dict out of the two stores when a third backend lands
   (Rule of Three).

## Consequences

### Positive
- A second real backend behind the unchanged ABC; no pipeline consumer
  changed. The contract suite runs identical assertions against both
  stores (`tests/test_vectordb_contract.py`).
- Per-collection on-disk isolation: each LanceDB table owns its files with
  optimistic concurrency, removing the shared-SQLite write-lock contention
  for multi-agent stdio workloads.
- The invariant #10 branch in `compose.py` is gone; selection follows the
  house registry pattern.
- Hybrid retrieval keeps identical ranking behaviour across backends; this
  change carries no sparse-retrieval risk.
- The filter surface is injection-safe by construction for
  MCP-client-sourced `metadata_filter` values.
- The identity guard ports unchanged in logic: `lance_meta.py` reuses
  `identity.py`'s pure helpers, so the legacy-stamp-then-reject rule stays
  identical across backends.

### Negative
- `VECTOR_STORE=lancedb` is opt-in; ChromaDB stays the default.
- Switching backends re-ingests into a fresh store; no cross-backend
  migration is provided.
- The generation counter is process-local per store instance, so the
  one-writer-per-collection boundary from ADR-045 still applies.
- Known limitation: tables created by `upsert_precomputed` fix the
  metadata struct at first write. Mixing writer kinds on one collection
  with different metadata keys may raise; re-ingest instead.

### Neutral
- Paged scans reuse the shared `CHROMA_SCAN_PAGE_SIZE` setting — the
  LanceDB store reads it through `_default_page_size`.
- ChromaDB local/cloud behaviour, defaults, and existing collections are
  unchanged.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Qdrant or pgvector** | Heavier operations (a server, or a database to run) for a local-first MCP server. LanceDB is embedded with no new infrastructure. |
| **Native LanceDB FTS / hybrid search in v1** | Production-ready, but needs an FTS-index lifecycle and a reranker that competes with this repo's calibrated cross-encoder (ADR-031). Deferred to its own change and experiment (`lancedb-native-fts-hybrid`). |
| **LanceDB Cloud (remote tables) in v1** | The expression builder and the pandas/arrow read paths are documented as local/embedded features with remote restrictions. A remote path would add an escaped-SQL-string fallback at the `lance_filter.py` seam. Deferred; embedded only. |
| **Hand-built SQL filters (LlamaIndex `_to_lance_filter` style)** | It escapes list values but interpolates scalar strings raw — an injection surface for MCP-client-sourced values. The expression-builder seam removes it by construction (DD2). |
| **Do nothing — keep ChromaDB only** | Leaves the invariant #10 branch in `compose.py` and the shared-SQLite write-lock contention unresolved, and the ABC's second-implementation promise unfulfilled. |

## References

- OpenSpec change: `openspec/changes/add-lancedb-vectordb-backend/`
  (proposal, design, delta specs)
- Implementation: `src/rag_mcp/core/vectordb/lancedb.py`,
  `src/rag_mcp/core/vectordb/lance_filter.py`,
  `src/rag_mcp/core/vectordb/lance_meta.py`,
  `src/rag_mcp/core/vectordb/lance_paged.py`,
  `src/rag_mcp/core/vectordb/registry.py`, `src/rag_mcp/compose.py`,
  `src/rag_mcp/config/__init__.py`, `src/rag_mcp/core/settings.py`
- Tests: `tests/test_lancedb_store.py`, `tests/test_lance_filter.py`,
  `tests/test_lancedb_import_site.py`, `tests/test_vectordb_contract.py`,
  `tests/test_vectordb_registry.py`, `tests/test_no_torch_at_runtime.py`
- Guides: `docs/guides/architecture.md`, `docs/guides/configuration.md`
- Related: ADR-003 (dimension locking), ADR-031 (reranker), ADR-034
  (vector-store ABC), ADR-037 (architecture v2), ADR-042 (dependency
  floors), ADR-045 (hosted Chroma cloud backend)
