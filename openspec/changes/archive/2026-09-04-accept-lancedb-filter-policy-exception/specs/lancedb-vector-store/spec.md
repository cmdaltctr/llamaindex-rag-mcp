# Spec: lancedb-vector-store

## MODIFIED Requirements

### Requirement: LanceDB SHALL translate ChromaDB where clauses safely

The store SHALL translate the ChromaDB-style `where` dict into LanceDB
filters in `core/vectordb/lance_filter.py`, with every VALUE serialised
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

## ADDED Requirements

### Requirement: The LanceDB filter adapter is the sole sanctioned exception to parameterised filtering

lancedb 0.37.x exposes no bind-parameter filter API, and its expression
objects cannot address the struct sub-fields where user metadata lives
(verified live; ADR-046). On that engine, a SQL filter string assembled
by `core/vectordb/lance_filter.py` with engine-owned quoting and
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
