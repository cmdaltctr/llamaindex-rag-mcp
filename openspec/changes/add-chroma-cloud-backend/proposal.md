## Why

Long-running retrieval calibration repeatedly embeds and writes the same
corpora into local ChromaDB indexes. The embedded `PersistentClient` also
uses one SQLite file per persist directory, so parallel writers contend and
indexes cannot be shared across machines. Chroma Cloud removes the local
write bottleneck while preserving the existing Chroma collection API and
`VectorStore` implementation.

LlamaIndex upstream already establishes the safe pattern: client construction
is separate from `ChromaVectorStore`, and the store accepts an injected
collection. The project can follow that pattern with `chromadb.CloudClient`
without a new dependency or a second vector-store adapter.

## What Changes

- Add an explicit `CHROMA_MODE=local|cloud` setting; default remains `local`.
- Keep embedding and storage as independent axes: existing
  `EMBED_PROVIDER=local|cloud` selects compute, while `CHROMA_MODE` selects
  storage. No third setting named `hybrid` is introduced.
- Persist embedding provider/model and immutable index identity in collection
  metadata; reject incompatible reuse even when vector dimensions match.
- Add `CHROMA_CLOUD_API_KEY` plus optional tenant and database settings.
- Construct `chromadb.CloudClient` in the Chroma construction path when cloud
  mode is selected; local mode keeps `PersistentClient` unchanged.
- Pass resolved storage settings from `compose.build_vector_store(settings)`
  instead of discarding the supplied settings and reading a process default.
- Fail startup when cloud mode lacks credentials or the cloud client cannot
  authenticate. Never silently switch to an empty local index.
- Keep collection operations, dimension locking, metadata filters,
  generation counters, ingestion, and retrieval behind the existing
  `VectorStore` contract.
- Migrate the active `calibrate-rag-retrieval-defaults` runners away from
  direct `PersistentClient` construction and removed module-level config
  constants so they use the same cloud-aware store composition path.
- Allocate a unique cloud collection per experiment cell/repetition and keep
  checkpoint/resume free of credentials.
- Document Chroma Cloud setup for experiment runs and record that changing
  embedding model or store requires re-ingestion.
- Add the four-mode deployment matrix to the configuration/experiment guide;
  identify Fireworks as a future cloud-compute adapter, not a vector store.

Out of scope: changing the default embedding provider, adding Qdrant, native
sparse retrieval, migrating existing local indexes automatically, and
changing production defaults. Those remain separate reviewed changes.

## Capabilities

### New Capabilities

- `chroma-cloud-backend`: Explicit hosted Chroma connection, credential
  validation, local/cloud selection, and failure behaviour.

### Modified Capabilities

- `vectordb-abstraction`: The Chroma implementation accepts either an injected
  local or cloud client while preserving the existing `VectorStore` contract.
- `config-composition-root`: `compose.py` selects the resolved storage mode
  and passes construction-time values to the Chroma integration; settings
  parsing remains construction-free.

## Impact

**Code:** `config/__init__.py`, `core/vectordb/chroma.py`, `compose.py`,
focused composition/vector-store tests, and the six active calibration
experiment harnesses (10b, 10.1, 12, 9a-rerun, 13, 14).

**Configuration:** new `CHROMA_MODE`, `CHROMA_CLOUD_API_KEY`,
`CHROMA_CLOUD_TENANT`, and `CHROMA_CLOUD_DATABASE` variables. Credentials stay
in environment variables and are never written to YAML, logs, or result files.

**Dependencies:** none. `chromadb.CloudClient` ships in the existing ChromaDB
dependency.

**Experiments:** `calibrate-rag-retrieval-defaults` may choose either axis
independently. Each immutable index records corpus/config identity, provider,
model, and tenant/database identifiers (never keys). Retrieval-only cells and
repetitions reuse that index read-only. A fresh collection is required when
the embedding model, corpus, parser, or chunking configuration changes.

**Concurrency boundary:** ChromaDB handles remote concurrent access, but the
project's BM25 invalidation counter is process-local. A coordinator builds
each immutable index once; evaluation workers query it read-only. Cross-process
mutation of the same collection remains out of scope.

**Compatibility:** local mode is unchanged. Existing local collections remain
usable. Cloud mode starts with an independent remote database and requires
explicit ingestion.
