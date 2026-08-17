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
  advertises) into LanceDB filters using the `lancedb.expr` type-safe
  expression builder (`col`, `lit`, `&`, `|`), not hand-built SQL strings.
  The builder handles value quoting and typing, closing the SQL-injection
  surface by construction (design decision DD2).
- **Paged reads**: `core/vectordb/lance_paged.py` provides a mixin for
  `iter_metadatas`, `iter_documents`, and `fetch_all` over LanceDB's
  scanner (`table.search().limit().offset()`, `table.to_pandas()`,
  `table.count_rows(filter=...)`). `PagedReadMixin` is ChromaDB-shaped and
  is not reused.
- **Collection metadata**: profile tags and embedding identity are stored
  through LanceDB table `update_config` (durable key-value config on the
  table), read-merge-write, mirroring the existing `identity.py` stamping
  logic (design decision DD1).
- **Registry dispatch**: `core/vectordb/registry.py` registers `chroma`
  and `lancedb` lazily under their configured names. `compose.py` resolves
  the store through the registry, replacing the `if/elif` branch and
  satisfying invariant #10 (design decision DD3).
- **Configuration**: `config/__init__.py` and `core/settings.py` accept
  `VECTOR_STORE=lancedb` and add `LANCEDB_URI` (parent directory for
  LanceDB tables, default `./lancedb`), documented in `.env.example`.
- **Dependency**: add `llama-index-vector-stores-lancedb` via `uv add`.
  Its resolved tree pulls `lancedb` and `pyarrow` only; no PyTorch reaches
  the base install, so the ONNX-only hard boundary holds.

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
- **Dependencies**: one new direct dependency
  (`llama-index-vector-stores-lancedb`), no PyTorch on the base path.
- **On-disk data**: none for existing ChromaDB users. `VECTOR_STORE`
  stays `chroma` by default; `lancedb` is opt-in. Switching backends
  re-ingests into a fresh LanceDB store; no cross-backend migration is
  provided.
- **File-size ceiling**: the LanceDB store is split across
  `lancedb.py` / `lance_paged.py` / `lance_filter.py` to stay under the
  500-line ceiling (invariant #11), matching the Chroma split.

## Open Questions

None blocking. Two soft choices are recorded in `design.md` for the build
session: DD1 may use table schema metadata instead of `update_config`
(both are durable; `update_config` is the recommended default here), and
DD3 introduces the vector-store registry in this change rather than
depending on any in-flight registry work (the two open registry changes
cover document readers and sparse retrieval, not vector stores).
