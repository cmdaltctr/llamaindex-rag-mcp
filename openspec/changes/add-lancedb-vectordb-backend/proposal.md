# Proposal: add-lancedb-vectordb-backend

## Why

The `VectorStore` ABC (`core/vectordb/base.py`, ADR-034) was written so a
second store could sit behind the same interface. Its own docstring names
LanceDB, Qdrant, and pgvector as the intended future implementations, yet
only ChromaDB exists today. LanceDB is the strongest first candidate: the
Lance format gives each collection its own on-disk files with optimistic
concurrency instead of ChromaDB's single shared SQLite write lock, so it
suits the multi-agent, multi-process stdio pattern this server already runs.
LlamaIndex ships a maintained `llama-index-vector-stores-lancedb`
integration, so the embedding and write path reuses the same LlamaIndex
machinery the ChromaDB store already uses.

Adding a second real backend also forces one latent debt to be paid.
`compose.py` selects the store with `if settings.vector_store == "chroma"`,
a branch over a strategy name. Architecture invariant #10 forbids exactly
this ("Registries are the dispatch mechanism ... MUST NOT branch if/elif
over strategy names"). The registry pattern already exists elsewhere in the
codebase (`core/retrieval/registry.py`), so this change extends the house
convention rather than inventing one.

## What Changes

- **New backend**: `core/vectordb/lancedb.py` provides
  `LanceVectorStore(VectorStore)`, implementing every abstract method. One
  `lancedb.connect(uri)` connection backs the store; each RAG "collection"
  maps to one LanceDB table. This mirrors how `ChromaVectorStore` holds one
  client and drives many collections.
- **Filter translation**: `core/vectordb/lance_filter.py` translates the
  ChromaDB-style `where` dict (the shape the MCP `search_documents` tool
  advertises) into LanceDB SQL filters. Every VALUE is serialised through
  the `lancedb.expr` type-safe literal builder (`lit(value).to_sql()`,
  whose unparser performs the engine's own quoting), field names are
  validated against a conservative identifier grammar and backtick-quoted,
  and the operator vocabulary is a fixed internal set — no client input is
  interpolated into SQL (design decision DD2). A full expression tree is
  not possible: `lancedb.expr` (0.37.1) has no struct field access
  (verified in the build session; recorded in ADR-046). Operator
  translation is null-aware so ChromaDB missing-field semantics hold:
  `$ne`/`$nin` match rows lacking the field, other operators do not, and
  a field absent from the schema folds to the same constants instead of
  reaching the planner.
- **Paged reads**: `core/vectordb/lance_paged.py` provides a mixin for
  `iter_metadatas`, `iter_documents`, and `fetch_all` over LanceDB's
  scanner (`table.search().limit().offset()`, `table.to_pandas()`,
  `table.count_rows(filter=...)`). `PagedReadMixin` is ChromaDB-shaped and
  is not reused.
- **Collection metadata**: profile tags and embedding identity are stored
  in the table's durable Arrow schema metadata, written read-merge-write
  through pylance's `update_schema_metadata` via the
  `core/vectordb/lance_meta.py` seam, mirroring the existing
  `identity.py` stamping logic (design decision DD1; the originally named
  `update_config` does not exist in the lancedb Python SDK — verified
  against 0.37.1 and corrected here).
- **Registry dispatch**: `core/vectordb/registry.py` registers `chroma`
  and `lancedb` lazily under their configured names. `compose.py` resolves
  the store through the registry, replacing the `if/elif` branch and
  satisfying invariant #10 (design decision DD3).
- **Configuration**: `config/__init__.py` and `core/settings.py` accept
  `VECTOR_STORE=lancedb` and add `LANCEDB_URI` (parent directory for
  LanceDB tables, default `./lancedb`), documented in `.env.example`.
- **Dependency**: add `llama-index-vector-stores-lancedb` via `uv add`,
  plus `lancedb`, `pylance`, and `pyarrow` as direct dependencies — the
  store calls `lancedb.expr`, pylance's `update_schema_metadata`, and
  builds upsert rows with pyarrow, so each needs a pinned floor rather
  than the adapter's unconstrained transitive ranges. The resolved tree
  adds `lancedb`/`pylance`/`pyarrow`/`tantivy`/`lance-namespace` only; no
  PyTorch reaches the base install, so the ONNX-only hard boundary holds.

Not in scope, recorded as deferred future work:

- **LanceDB native full-text and hybrid search.** LanceDB has a
  production-ready native BM25 full-text index and hybrid (vector + FTS)
  search with a default RRF reranker. v1 does not use it. The existing
  in-memory BM25 sparse path is backend-agnostic (it reads rows through
  `iter_documents` and rebuilds off the generation counter), so LanceDB
  gets hybrid retrieval through the current path with no new work. Native
  FTS adds an index lifecycle to manage and a reranker that competes with
  this repo's calibrated cross-encoder, so it belongs in its own change
  with its own experiment.
- **LanceDB Cloud (remote tables).** The `lancedb.expr` builder and the
  pandas/arrow read paths are documented as local/embedded features with
  remote restrictions. v1 targets the embedded, local-first path only. A
  future remote path would add an escaped-SQL-string filter fallback at the
  `lance_filter.py` seam.
- **Per-collection persist directories.** The `add-per-collection-persist-dirs`
  change fixes ChromaDB's shared-SQLite write-lock contention. LanceDB
  tables are already isolated on disk, so that change neither needs to be
  widened for LanceDB nor blocks this one. The two are orthogonal.

## Capabilities

### New Capabilities

- `lancedb-vector-store`: defines the LanceDB implementation of the
  `VectorStore` contract, the collection-to-table mapping, the filter
  translation rule, the collection-metadata home, and the local-first
  scope.
- `vector-store-registry`: defines registry-based store selection at the
  composition root, replacing the `if/elif` branch over the `VECTOR_STORE`
  name.

### Modified Capabilities

- `vectordb-abstraction`: the "Store selection via configuration"
  requirement gains the constraint that selection happens through a
  registry, and the contract gains a second registered implementation.

## Impact

- **Code**: new `core/vectordb/lancedb.py`, `core/vectordb/lance_filter.py`,
  `core/vectordb/lance_paged.py`, `core/vectordb/registry.py`; edits to
  `compose.py` (registry dispatch), `config/__init__.py` and
  `core/settings.py` (new `LANCEDB_URI`, `VECTOR_STORE=lancedb` accepted),
  `.env.example`.
- **Contracts**: MCP tool surface unchanged. The `metadata_filter`
  parameter keeps its "ChromaDB-compatible where clause" contract; the
  LanceDB backend honours it through translation.
- **Dependencies**: `llama-index-vector-stores-lancedb`, `lancedb`,
  `pylance`, and `pyarrow` as new direct dependencies, no PyTorch on the
  base path.
- **On-disk data**: none for existing ChromaDB users. `VECTOR_STORE`
  stays `chroma` by default; `lancedb` is opt-in. Switching backends
  re-ingests into a fresh LanceDB store; no cross-backend migration is
  provided.
- **File-size ceiling**: the LanceDB store is split across
  `lancedb.py` / `lance_paged.py` / `lance_filter.py` to stay under the
  500-line ceiling (invariant #11), matching the Chroma split.

## Open Questions

None blocking. The two soft choices recorded in `design.md` were settled
by the build session (verified against lancedb 0.37.1): DD1 landed on
its fallback branch — Arrow schema metadata through pylance's
`update_schema_metadata`, because the SDK has no `update_config` — and
DD3 introduced the vector-store registry in this change with no
dependency on the in-flight registry work (the two open registry changes
cover document readers and sparse retrieval, not vector stores).
