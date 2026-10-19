## MODIFIED Requirements

### Requirement: LanceDB SHALL implement the VectorStore contract

The system SHALL provide `core/vectordb/lancedb/store.py` implementing the
`VectorStore` ABC (`core/vectordb/base.py`). A single `lancedb.connect(uri)`
connection SHALL back the store, and each RAG collection SHALL map to one
LanceDB table. The implementation SHALL be split across the modules of the
`core/vectordb/lancedb/` folder (`store.py`, `paged.py`, `filter.py` and
their siblings) so no file exceeds 500 lines (architecture invariant #11).
No module outside `core/vectordb/lancedb/` SHALL import `lancedb`.

#### Scenario: Collection maps to a table

- **WHEN** a collection named `X` is created, listed, or deleted
- **THEN** the store MUST create, enumerate, or drop the LanceDB table `X`
  through the shared connection

#### Scenario: Single lancedb import site

- **WHEN** `src/omrg/` is searched for `import lancedb`
- **THEN** the only matches MUST be within `core/vectordb/lancedb/`

#### Scenario: Contract parity with the ABC

- **WHEN** the shared `VectorStore` contract tests run against the LanceDB
  store
- **THEN** every abstract method MUST pass the same assertions the ChromaDB
  store passes, except where a scenario in this spec states an explicit
  difference

### Requirement: LanceDB SHALL enforce embedding identity through table config

The store SHALL persist the embedding-identity triple (`provider`, `model`,
`index_identity`) and profile tags in the table's durable Arrow schema
metadata, written read-merge-write through pylance's
`update_schema_metadata` seam (`core/vectordb/lancedb/meta.py`). (The
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
filters in `core/vectordb/lancedb/filter.py`, with every VALUE serialised
through the `lancedb.expr` type-safe literal builder (whose unparser
performs the engine's own quoting), every field name validated against a
conservative identifier grammar and backtick-quoted in the emitted SQL,
and the operator vocabulary a fixed internal set. It SHALL NOT
interpolate client-supplied values into SQL strings. (A full per-leaf
expression tree is not possible: `lancedb.expr` (0.37.1) has no struct
field access, and user metadata lives inside an Arrow `metadata` struct,
so filters must reference `metadata.<field>` paths; recorded in
ADR-046. The string assembly this design necessarily performs is the
sanctioned exception to parameterised filtering recorded in ADR-058.)
The ChromaDB operators `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`,
`$nin`, `$and`, and `$or` SHALL be supported. An unsupported operator
SHALL raise a clear error naming it. Translation SHALL preserve ChromaDB
missing-field semantics: `$ne` and `$nin` match rows whose field is null
or absent, every other operator does not, and a field absent from the
table's schema SHALL fold to the same constants instead of reaching the
SQL planner. The translator SHALL validate each field name and
membership operand, including the membership-list limit, before it folds
a schema-absent field to a constant.

The translator SHALL treat the engine's unparser as untrusted. Every
serialised literal SHALL match the closed form for its value type and
represent the original value. This applies to bool, int, float, Decimal,
bytes, date, datetime, and string values. The translator SHALL decode or
parse each fragment and compare it with the original value using the
corresponding type's exact or canonical semantics. A fragment that is
not a faithful serialisation of its value SHALL refuse the whole filter
with an actionable error before any SQL reaches the engine. Client
filters are untrusted input, so nesting depth, comparison-clause count,
membership-list length, and serialised length SHALL each be capped with
an error naming the crossed limit.

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

#### Scenario: Missing-field semantics match ChromaDB

- **WHEN** a `where` filters on a metadata field that some rows lack or
  that no row carries (absent from the schema)
- **THEN** `$ne` and `$nin` MUST match the rows lacking the field
- **AND** `$eq`, `$in`, and the comparison operators MUST NOT
- **AND** the filter MUST NOT fail with a planner error for a
  schema-absent field

#### Scenario: Unfaithful engine serialisation is refused

- **WHEN** the engine's literal builder emits a fragment that fails its
  closed-form check or represents a different value
- **THEN** the translator MUST refuse the filter with an error naming
  the affected value class
- **AND** this MUST apply to string, byte, boolean, numeric, Decimal,
  date, and datetime values
- **AND** no SQL MUST reach the engine for that filter

#### Scenario: Absent fields do not bypass input validation

- **WHEN** a filter targets a schema-absent field with an invalid field
  name, invalid membership operand, or oversized membership list
- **THEN** the translator MUST reject the invalid input before folding
  the predicate to an absent-field constant

#### Scenario: Structural bounds are enforced

- **WHEN** a filter exceeds the nesting-depth, clause-count,
  membership-list, or serialised-length cap
- **THEN** the translator MUST refuse it with an error naming the
  crossed limit

### Requirement: LanceDB SHALL evolve the metadata struct on later writes

LanceDB fixes the Arrow `metadata` struct on the first write, and pylance
has no nested `add_columns`, so the store SHALL grow the struct itself in
`core/vectordb/lancedb/meta.py` when a later write introduces metadata keys
the struct lacks: existing rows gain nulls for the new fields (ChromaDB's
key-absent state), the schema metadata bag (identity triple, profile
tags) SHALL survive the growth, and no incoming metadata key SHALL be
silently dropped.

#### Scenario: A later write introduces a new metadata field

- **WHEN** a collection already exists and a write introduces a metadata
  key absent from its struct
- **THEN** the store MUST extend the struct before writing
- **AND** the new key MUST be retrievable through filters and paged reads
- **AND** existing rows and the stored identity/profile metadata MUST be
  preserved

#### Scenario: Adapter-internal struct fields

- **WHEN** the LlamaIndex adapter writes into a table created by
  `upsert_precomputed` (whose struct lacks the adapter's internal keys)
- **THEN** the store MUST add the internal keys to the struct before the
  adapter write so the write succeeds

### Requirement: LanceDB reads SHALL use bounded scanner pages

The store SHALL implement `iter_metadatas`, `iter_documents`, and
`fetch_all` over LanceDB's scanner in `core/vectordb/lancedb/paged.py`, using
bounded pages for the iterators. The BM25 sparse retriever SHALL read
through `iter_documents` unchanged, and the process-local generation counter
SHALL advance on every write, row delete, and collection drop so the
retriever rebuilds its index.

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

#### Scenario: Dropping a collection invalidates the BM25 cache

- **WHEN** a collection is dropped through the store (directly, without
  the ingestion writer's external bump)
- **THEN** the generation counter MUST advance so a cached BM25 index
  built over the collection is invalidated

### Requirement: The LanceDB filter adapter is the sole sanctioned exception to parameterised filtering

lancedb 0.37.x exposes no bind-parameter filter API, and its expression
objects cannot address the struct sub-fields where user metadata lives
(verified live; ADR-046). On that engine, a SQL filter string assembled
by `core/vectordb/lancedb/filter.py` with engine-owned quoting and
fail-closed verification is the sanctioned filter mechanism, for the
`search_documents` and `answer_documents` paths alike (ADR-058). The
exception SHALL NOT extend to any other store or code path: any backend
that accepts structured filters or offers bound parameters MUST filter
through those mechanisms, and client values MUST NOT be assembled into
query text outside this adapter. When a lancedb release offers a
parameterised path that can address user metadata, the adapter MUST
migrate to it and this exception SHALL lapse.

#### Scenario: Exception applies only to the LanceDB filter adapter

- **WHEN** any store other than the LanceDB adapter filters retrieved
  data by client-supplied values
- **THEN** it MUST use that store's structured or parameterised filter
  mechanism
- **AND** client values MUST NOT be assembled into query text

#### Scenario: A future parameterised path supersedes the exception

- **WHEN** a lancedb release offers bind parameters or expression
  objects that can address user metadata sub-fields
- **THEN** the adapter MUST migrate to that path
- **AND** the exception recorded in ADR-058 SHALL lapse
