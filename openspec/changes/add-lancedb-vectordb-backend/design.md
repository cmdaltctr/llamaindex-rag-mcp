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
gap this design avoids by using the expression builder), and LlamaIndex's
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

### DD1: Collection metadata via table `update_config`

**Decision.** Store the embedding-identity triple (`provider`, `model`,
`index_identity`) and profile tags in the LanceDB table's durable
key-value config via `update_config` / `delete_config_keys`, read back
through the table's config. Apply the read-merge-write pattern already used
by `stamp_collection_identity` in `identity.py`.

**Evidence.** LanceDB exposes two durable, mutable, post-creation
key-value stores on a table: `replace_schema_metadata` (Arrow schema
metadata) and `update_config` (table config). Both persist to the dataset.
The `Tags` system is git-style version references, not an application
key-value bag, so it is rejected for this use.

**Why `update_config` over schema metadata.** Schema metadata is coupled to
the Arrow schema and rides along with schema evolution; `update_config` is a
purpose-built config bag decoupled from schema changes. Either is durable
and correct. The build session may substitute `replace_schema_metadata`
(LlamaIndex's own embedding registry uses it) with no contract change; this
is a soft preference, not a fork.

**Consequence.** `IdentityGuardMixin` is written against a small
store-supplied accessor pair (read config, merge-write config) rather than
against a ChromaDB collection handle. The mismatch-rejection and
legacy-stamping logic port unchanged. LanceDB fixes the vector column
dimension when the table schema is created on first write, so dimension
locking comes from the schema; embedding-identity enforcement comes from
this config metadata.

**Build-session outcome (verified against lancedb 0.37.1).** Neither
`update_config` nor a Table-level `replace_schema_metadata` exists in
the Python SDK — schema metadata is creation-time only through the
public API. The durable post-creation bag is pylance's
`LanceDataset.update_schema_metadata(values, replace=False)` (merge
semantics, survives close/reopen and adapter writes), reached via
`table.to_lance()` behind the `lance_meta.py` seam. This is the DD1
fallback branch in effect; the spec text was corrected to match.

### DD2: Filter translation via the `lancedb.expr` builder

**Decision.** `lance_filter.py` translates the ChromaDB `where` dict into a
`lancedb.expr` expression tree, not a SQL string:

- `{"field": value}` and `{"field": {"$eq": value}}` → `col("field") == lit(value)`
- `$ne $gt $gte $lt $lte` → the matching comparison
- `$in` / `$nin` → set membership / its negation
- `$and` / `$or` → compose subexpressions with `&` / `|`
- an unknown operator raises a clear `ValueError` naming the operator

The expression builder handles value quoting and typing, so string values
carry no injection risk and no manual escaping is written.

**Evidence.** LanceDB's `where` runs on DataFusion SQL and supports
`=, !=, >, >=, <, <=, IN, AND, OR, NOT, LIKE, IS NULL`, so every ChromaDB
operator maps one-to-one. LanceDB has no parameterised `where` string
(open issue #2652), and `metadata_filter` arrives from MCP clients, so a
hand-built SQL string would be an injection surface. LlamaIndex's own
`_to_lance_filter` demonstrates the trap: it escapes list values but
interpolates scalar strings raw. The `lancedb.expr` builder (`col`, `lit`,
`func`) is the vendor-recommended alternative to raw SQL and removes the
surface by construction.

**Scope note (remote).** The expression builder is documented as a
local/embedded feature; remote LanceDB Cloud tables restrict it. v1 is
embedded only. A future remote path adds an escaped-SQL-string fallback at
this same seam, selected by connection type. Recorded, not built.

**Pipeline reality.** The pipeline's own `where` clauses are simple
equality (`{"file_path": ...}`), so the common path is trivial; the full
operator set exists to honour the MCP tool's advertised contract.

**Build-session outcome (verified against lancedb 0.37.1).**
`lancedb.expr` (`col`, `lit`) exists but has no struct field access, and
`count_rows(filter=)` accepts SQL strings only. The translator therefore
serialises every VALUE through `lit(value).to_sql()` (the engine's own
unparser — verified to escape single quotes), validates field names
against a conservative identifier grammar, and composes with a fixed
operator vocabulary. Behaviourally identical to the expression-tree
construction for every scenario (the injection decoy test proves it);
recorded in ADR-046.

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
  module with its own test file mapping each ChromaDB operator to an
  expression-builder assertion, plus a rejection test for unknown
  operators. Equality-only pipeline usage keeps the hot path small.
- [LanceDB lazy table creation differs subtly from ChromaDB] → Contract
  tests assert create-then-write, write-without-explicit-create, and
  dimension-lock-on-first-write parity against the ABC, run for both
  backends.
- [`update_config` durability or API shape differs from expectation] →
  A focused integration test writes identity + profile config, reopens the
  connection, and asserts the values survive. If `update_config` proves
  unsuitable, `replace_schema_metadata` is the drop-in alternative (DD1).
- [New dependency pulls PyTorch onto the base path] → Verified at
  proposal time: `lancedb==0.37.x` resolves to `lancedb` + `pyarrow` only.
  A dependency-floor / import test asserts no `torch` import on the base
  retrieval path, consistent with the existing ONNX-only boundary.
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

None blocking. DD1 (`update_config` vs schema metadata) and the eventual
value of native hybrid (DD5 / Deferred 1) are the only soft points, both
recorded above with a default and a fallback.
