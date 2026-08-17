# Spec: lancedb-vector-store

## ADDED Requirements

### Requirement: LanceDB SHALL implement the VectorStore contract

The system SHALL provide `core/vectordb/lancedb.py` implementing the
`VectorStore` ABC (`core/vectordb/base.py`). A single `lancedb.connect(uri)`
connection SHALL back the store, and each RAG collection SHALL map to one
LanceDB table. The implementation SHALL be split across `lancedb.py`,
`lance_paged.py`, and `lance_filter.py` so no file exceeds 500 lines
(architecture invariant #11). No module outside `core/vectordb/` SHALL
import `lancedb`.

#### Scenario: Collection maps to a table

- **WHEN** a collection named `X` is created, listed, or deleted
- **THEN** the store MUST create, enumerate, or drop the LanceDB table `X`
  through the shared connection

#### Scenario: Single lancedb import site

- **WHEN** `src/rag_mcp/` is searched for `import lancedb`
- **THEN** the only matches MUST be within `core/vectordb/`

#### Scenario: Contract parity with the ABC

- **WHEN** the shared `VectorStore` contract tests run against the LanceDB
  store
- **THEN** every abstract method MUST pass the same assertions the ChromaDB
  store passes, except where a scenario in this spec states an explicit
  difference

### Requirement: LanceDB SHALL lock the vector space on first write

The store SHALL fix a collection's vector dimension when the table schema is
created on first write, matching the ChromaDB dimension-lock behaviour.
`create_collection` SHALL record intent without forcing a schema before the
first write.

#### Scenario: Dimension fixed on first write

- **WHEN** the first documents are written to a new collection
- **THEN** the table schema MUST fix the vector column dimension
- **AND** a later write with a different embedding dimension MUST raise a
  clear error

#### Scenario: Create then write

- **WHEN** `create_collection(name)` is called before any write
- **THEN** the collection MUST be reported as existing
- **AND** the first write MUST succeed and fix the dimension

### Requirement: LanceDB SHALL enforce embedding identity through table config

The store SHALL persist the embedding-identity triple (`provider`, `model`,
`index_identity`) and profile tags in the table's durable Arrow schema
metadata, written read-merge-write through pylance's
`update_schema_metadata` seam (`core/vectordb/lance_meta.py`). (The
originally named mechanisms — table `update_config` and a table-level
`replace_schema_metadata` — do not exist in the lancedb Python SDK as of
0.37.1; schema metadata is the verified durable key-value bag, recorded in
ADR-046.) The store SHALL apply the same legacy-stamp-then-reject rule as
`identity.py`: a collection with no stored identity is stamped on first
write, and a stored identity that does not match the active configuration
is rejected before any write or query. When no embedding identity is
attached (the pre-cloud direct-call path), the store SHALL neither stamp
nor check.

#### Scenario: Legacy collection stamped on first write

- **WHEN** a collection has no stored embedding identity and an identity is
  attached
- **THEN** the first write MUST stamp the active identity into the table
  config
- **AND** existing config keys such as profile tags MUST be preserved
  (read-merge-write)

#### Scenario: Mismatched identity rejected

- **WHEN** a collection's stored identity does not match the active
  configuration
- **THEN** a write or query MUST raise a clear error
- **AND** matching vector dimensions MUST NOT be treated as proof of
  compatibility

#### Scenario: Identity metadata survives reconnection

- **WHEN** identity and profile config are written, the connection is
  closed, and the table is reopened
- **THEN** the stored values MUST be readable unchanged

### Requirement: LanceDB SHALL translate ChromaDB where clauses safely

The store SHALL translate the ChromaDB-style `where` dict into LanceDB
filters in `core/vectordb/lance_filter.py`, with every VALUE serialised
through the `lancedb.expr` type-safe literal builder (whose unparser
performs the engine's own quoting), every field name validated against a
conservative identifier grammar, and the operator vocabulary a fixed
internal set. It SHALL NOT interpolate client-supplied values into SQL
strings. (A full per-leaf expression tree is not possible: `lancedb.expr`
(0.37.1) has no struct field access, and user metadata lives inside an
Arrow `metadata` struct, so filters must reference `metadata.<field>`
paths; recorded in ADR-046.) The ChromaDB operators `$eq`, `$ne`, `$gt`,
`$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$and`, and `$or` SHALL be
supported. An unsupported operator SHALL raise a clear error naming it.

#### Scenario: Equality filter

- **WHEN** a `where` of `{"file_path": "a/b.py"}` is supplied
- **THEN** the store MUST return only rows whose `file_path` equals
  `a/b.py`

#### Scenario: Boolean composition and set membership

- **WHEN** a `where` combines `$and`, `$or`, or `$in` operators
- **THEN** the store MUST return rows matching the composed condition

#### Scenario: String values carry no injection risk

- **WHEN** a filter value contains SQL metacharacters such as a single
  quote
- **THEN** the value MUST be treated as a literal through the expression
  builder
- **AND** it MUST NOT alter the filter structure

#### Scenario: Unknown operator rejected

- **WHEN** a `where` uses an operator outside the supported set
- **THEN** the translator MUST raise a clear error naming the operator

### Requirement: LanceDB reads SHALL use bounded scanner pages

The store SHALL implement `iter_metadatas`, `iter_documents`, and
`fetch_all` over LanceDB's scanner in `core/vectordb/lance_paged.py`, using
bounded pages for the iterators. The BM25 sparse retriever SHALL read
through `iter_documents` unchanged, and the process-local generation counter
SHALL advance on every write and delete so the retriever rebuilds its index.

#### Scenario: Paged iteration over a large collection

- **WHEN** `iter_documents` or `iter_metadatas` scans a collection larger
  than one page
- **THEN** it MUST yield every row using bounded pages
- **AND** it MUST NOT load the whole collection at once

#### Scenario: Hybrid retrieval through the existing BM25 path

- **WHEN** hybrid retrieval runs against a LanceDB-backed collection
- **THEN** the in-memory BM25 retriever MUST build its index from
  `iter_documents`
- **AND** a write or delete MUST advance the generation counter so the
  index is rebuilt

### Requirement: LanceDB SHALL stay local-first with no PyTorch on the base path

The LanceDB dependency SHALL be added through
`llama-index-vector-stores-lancedb` and SHALL NOT introduce PyTorch onto the
base install or the default retrieval path (ONNX-only hard boundary). v1
SHALL target the embedded, local LanceDB connection only.

#### Scenario: No PyTorch on the base path

- **WHEN** the base install is resolved and the default retrieval path runs
- **THEN** `torch` MUST NOT be imported

#### Scenario: Embedded connection by default

- **WHEN** `VECTOR_STORE=lancedb` is selected without remote credentials
- **THEN** the store MUST connect to the local `LANCEDB_URI` directory
