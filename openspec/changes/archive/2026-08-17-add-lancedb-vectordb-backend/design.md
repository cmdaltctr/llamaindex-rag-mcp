# Design: add-lancedb-vectordb-backend

## Context

See `proposal.md` for motivation. The relevant shape of the current code:

- `core/vectordb/base.py` defines the `VectorStore` ABC (ADR-034). Its
  docstring names LanceDB as an intended future implementation. The
  contract encodes three ChromaDB-derived behaviours: dimension locking,
  a `where` filter in ChromaDB syntax, and a process-local generation
  counter for BM25 cache invalidation.
- `core/vectordb/chroma.py` is the only current implementation. It holds
  one client and drives many collections. It composes two mixins,
  `IdentityGuardMixin` (`identity.py`) and `PagedReadMixin` (`paged.py`),
  and is split across files to stay under the 500-line ceiling.
- `compose.py` selects the store with
  `if settings.vector_store == "chroma": ... else: raise`. This is the
  invariant #10 violation this change removes.
- `core/retrieval/registry.py` already exists. The registry pattern is the
  established house convention (from `add-pluggable-community-detection`).
- The in-memory BM25 sparse retriever reads rows through
  `iter_documents(collection_name)` and rebuilds its index when the
  store's generation counter advances. It is backend-agnostic already.
- LlamaIndex's `LanceDBVectorStore` is single-table-per-instance: one
  `uri`, one `table_name`. It cannot model many collections by itself, so
  this change wraps the `lancedb.DBConnection` beneath it and constructs a
  throwaway `LanceDBVectorStore(connection=..., table_name=...)` per write,
  exactly as `chroma.py` constructs a throwaway `_LlamaChromaVectorStore`
  per collection.

Prior art studied: LlamaIndex's `_to_lance_filter` (a filter translator
that escapes list values but interpolates scalar strings raw, an injection
gap this design avoids by routing every value through the engine's own
literal builder), and LlamaIndex's
`SimpleVectorStore.from_namespaced_persist_dir` (filesystem-as-registry,
not relevant to LanceDB tables which are already isolated).

## Goals / Non-Goals

**Goals:**

- A second, real `VectorStore` implementation behind the existing ABC, with
  no change to any pipeline consumer.
- Registry-based store selection at the composition root, removing the
  `if/elif` branch (invariant #10).
- Local-first, embedded LanceDB only, with no PyTorch on the base path.
- Hybrid retrieval preserved through the existing backend-agnostic BM25
  path, with zero new sparse work.

**Non-Goals:**

- LanceDB native full-text / hybrid search — deferred, own change and
  experiment (see Deferred Work).
- LanceDB Cloud / remote tables — deferred; embedded only.
- Cross-backend data migration — switching `VECTOR_STORE` re-ingests.
- Any change to per-collection persist directories — orthogonal, ChromaDB
  only.

## Decisions

### DD1: Collection metadata via pylance `update_schema_metadata`

**Decision (landed).** Store the embedding-identity triple (`provider`,
`model`, `index_identity`) and profile tags in the table's durable Arrow
schema metadata, written read-merge-write through pylance's
`LanceDataset.update_schema_metadata(values, replace=False)` and read
back through `table.schema.metadata` — both behind the `lance_meta.py`
seam, reusing the pure helpers of ChromaDB's `identity.py` so the
legacy-stamp-then-reject rule stays identical across backends.
Verified against lancedb 0.37.1 / pylance 10.0.0: merge semantics,
survives close/reopen and adapter writes.

**Rejected alternatives (proposal-time).** The proposal named
`update_config` / `delete_config_keys` (a purpose-built table-config
bag) and a Table-level `replace_schema_metadata`, preferring the config
bag as "decoupled from schema changes". Neither API exists in the
Python SDK (verified against 0.37.1), so schema metadata is the one
durable post-creation key-value bag. The `Tags` system (git-style
version references, not an application key-value bag) stays rejected
for this use.

**Consequence.** `IdentityGuardMixin` is written against a small
store-supplied accessor pair (read metadata, merge-write metadata)
rather than against a ChromaDB collection handle. The
mismatch-rejection and legacy-stamping logic port unchanged. LanceDB
fixes the vector column dimension when the table schema is created on
first write, so dimension locking comes from the schema;
embedding-identity enforcement comes from this schema metadata.

### DD2: Filter translation to SQL through the `lancedb.expr` literal builder

**Decision (landed).** `lance_filter.py` translates the ChromaDB
`where` dict into a DataFusion SQL filter string in which every VALUE
is serialised by the engine's own literal builder — `lit(value).to_sql()`
— field names are validated against a conservative identifier grammar
and backtick-quoted, and composition uses a fixed operator vocabulary
(`$eq $ne $gt $gte $lt $lte $in $nin $and $or`). Neither half of any
comparison is built by interpolating client input; an unknown operator
raises a clear `ValueError` naming it.

**Rejected alternative: a full `lancedb.expr` expression tree
(proposal-time).** The proposal sketched composing `col("field") ==
lit(value)` trees. `lancedb.expr` (`col`, `lit`) exists but has no
struct field access (verified against 0.37.1), and `count_rows(filter=)`
accepts SQL strings only — the adapter stores user metadata inside an
Arrow `metadata` struct, so tree composition cannot express the
`metadata.<field>` paths filters need. The literal-builder-to-SQL shape
is behaviourally identical for every scenario (the injection decoy
test proves it); recorded in ADR-046.

**Evidence.** LanceDB's `where` runs on DataFusion SQL and supports
`=, !=, >, >=, <, <=, IN, AND, OR, NOT, LIKE, IS NULL`, so every ChromaDB
operator maps one-to-one. LanceDB has no parameterised `where` string
(open issue #2652), and `metadata_filter` arrives from MCP clients, so a
hand-built SQL string would be an injection surface. LlamaIndex's own
`_to_lance_filter` demonstrates the trap: it escapes list values but
interpolates scalar strings raw. Serialising values through the
engine's literal builder is the vendor-recommended way to remove that
surface by construction.

**Scope note (remote).** The literal builder is documented as a
local/embedded feature; remote LanceDB Cloud tables restrict it. v1 is
embedded only. A future remote path adds an escaped-SQL-string fallback
at this same seam, selected by connection type. Recorded, not built.

**Pipeline reality.** The pipeline's own `where` clauses are simple
equality (`{"file_path": ...}`), so the common path is trivial; the full
operator set exists to honour the MCP tool's advertised contract.

### DD3: Registry-based store selection

**Decision.** Add `core/vectordb/registry.py` following the pattern of
`core/retrieval/registry.py`: concrete stores register lazily under their
configured names (`chroma`, `lancedb`); `compose.py` resolves the store by
looking up `settings.vector_store` in the registry. The dispatch module
imports no concrete store module at module level and contains no `if/elif`
over store names (invariant #10). An unregistered name raises a clear error
listing the registered names.

**Evidence.** The registry pattern is already the house convention
(`core/retrieval/registry.py`). The two in-flight registry changes cover
different surfaces: `register-document-backend-strategies` (document
readers, local/azure) and `implement-native-sparse-backend-strategy`
(sparse retrieval, ChromaDB-coupled native path). Neither owns vector-store
selection, so this change introduces the vector-store registry itself with
no dependency on and no collision with them.

### DD4: Collection lifecycle maps to LanceDB tables

**Decision.** RAG collection ↔ LanceDB table:

- `create_collection(name)` → lazy; LanceDB creates the table on first
  write once a schema is known, matching ChromaDB's create-on-first-write
  and dimension-lock behaviour. `create_collection` records intent without
  forcing an empty-schema table.
- `collection_exists(name)` → `name in conn.table_names()`
- `delete_collection(name)` → `conn.drop_table(name)`
- `list_collections()` → `conn.table_names()`
- `write_nodes(nodes, name)` → per-table
  `LanceDBVectorStore(connection=conn, table_name=name)` fed to
  `VectorStoreIndex`, mirroring the Chroma write path
- `upsert_precomputed(...)` → `table.add()` / `merge_insert`
- `count` / `count_where` → `table.count_rows()` /
  `table.count_rows(filter=...)`
- `delete_where(name, where)` → `table.delete(<translated filter>)`
- paged reads → `lance_paged.py` mixin over the LanceDB scanner
- `bump_generation` / `get_generation` → the same process-local dict the
  Chroma store owns; this logic is backend-agnostic and may be hoisted to
  a shared helper if a third backend lands (Rule of Three, not yet).

### DD5: Hybrid retrieval through the existing BM25 path

**Decision.** v1 exposes LanceDB as a dense store only. The in-memory BM25
sparse retriever already reads through `iter_documents` and invalidates off
the generation counter, so it works over LanceDB unchanged once those two
methods are implemented. No native LanceDB FTS index is built in v1.

**Consequence.** Hybrid search keeps identical ranking behaviour across
backends, and this change carries no sparse-retrieval risk. Native FTS is
deferred (see Deferred Work).

## Risks / Trade-offs

- [Two backends drift in `where` semantics] → The translator is a single
  module with its own test file mapping each ChromaDB operator to a
  literal-builder assertion, plus a rejection test for unknown
  operators. Equality-only pipeline usage keeps the hot path small.
- [LanceDB lazy table creation differs subtly from ChromaDB] → Contract
  tests assert create-then-write, write-without-explicit-create, and
  dimension-lock-on-first-write parity against the ABC, run for both
  backends.
- [Schema-metadata durability differs from expectation] → A focused
  integration test writes identity + profile metadata, reopens the
  connection, and asserts the values survive — against the landed
  pylance `update_schema_metadata` seam (DD1), not an assumed API.
- [New dependency pulls PyTorch onto the base path] → The direct
  additions resolve to `lancedb` + `pylance` + `pyarrow` only (pylance
  pinned `>=10`; verified in the landed lock — the proposal-time claim
  of "`lancedb` + `pyarrow` only" missed pylance). A dependency-floor /
  import test asserts no `torch` import on the base retrieval path,
  consistent with the existing ONNX-only boundary.
- [Registry refactor touches the shared `compose.py`] → Scoped to the
  store-selection function; the change adds the registry and rewrites one
  branch, with no change to `ensure_runtime_setup` ordering.

## Deferred Work (recorded, not built)

1. **`lancedb-native-fts-hybrid`** — use LanceDB's native BM25 full-text
   index and hybrid search (`query_type="hybrid"`, default RRF reranker).
   Requires an FTS-index lifecycle (build, rebuild on write) and a
   calibration experiment comparing RRF against this repo's cross-encoder
   reranker (ADR-031). Own change, own experiment.
2. **LanceDB Cloud / remote tables** — add a connection-type-selected
   escaped-SQL-string filter fallback at the `lance_filter.py` seam and
   remote-safe read paths. The embedded contract stays the default.
3. **Shared generation-counter helper** — hoist the process-local
   generation dict out of the two stores when a third backend lands
   (Rule of Three).

## Open Questions

None blocking. The proposal-time DD1 soft point (`update_config` vs
schema metadata) resolved during the build (schema metadata via pylance
is the landed seam), and the eventual value of native hybrid
(DD5 / Deferred 1) is recorded with a default and a deferred experiment.
