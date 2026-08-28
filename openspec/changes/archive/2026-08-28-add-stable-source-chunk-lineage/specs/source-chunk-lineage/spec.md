# source-chunk-lineage Specification

## Purpose

Define stable source and chunk identities for production ingestion, ordered
chunk membership, LlamaIndex source relationships, persistence, and retrieval
without weakening failure-safe replacement.

## ADDED Requirements

### Requirement: Production sources have deterministic logical identities

For every file processed by `ingest_path_async`, the system SHALL derive
`source_id` from the canonical absolute `file_path` already resolved by the
ingestion pipeline. The formula SHALL be `"src_" + SHA-256("file\0" +
canonical_file_path)`, using UTF-8 input, a NUL separator, and lower-case
hexadecimal output. The collection name SHALL NOT participate in the formula.
The canonical path SHALL remain stored separately as `file_path`.

#### Scenario: Editing one source preserves its logical identity

- **GIVEN** a file remains at the same canonical path
- **WHEN** its bytes change and it is ingested again
- **THEN** its `source_id` MUST remain unchanged
- **AND** its `source_content_hash` and `source_version` MUST change

#### Scenario: Equal bytes at different paths remain distinct sources

- **GIVEN** two files have byte-identical content at different canonical paths
- **WHEN** both files are ingested
- **THEN** they MUST have the same `source_content_hash`
- **AND** they MUST have different `source_id` values

#### Scenario: One source is indexed into two collections

- **GIVEN** one canonical file path
- **WHEN** it is ingested into two collections
- **THEN** both collections MUST store the same `source_id` for that source

#### Scenario: A move or rename is a new logical source

- **GIVEN** a file is moved to a different canonical path
- **WHEN** the destination is ingested
- **THEN** the destination MUST receive a different `source_id`
- **AND** the system MUST NOT claim identity preservation across the move

### Requirement: Existing content and index-version identities remain canonical

The system SHALL retain `source_content_hash` as the SHA-256 identity of exact
original source bytes. It SHALL retain `source_version` as SHA-256 over
`source_content_hash`, a NUL separator, and `source_index_identity`. It SHALL
NOT add a duplicate `document_hash` metadata field or alias.

#### Scenario: Same bytes under different index settings produce a new version

- **GIVEN** a source's bytes and `source_id` are unchanged
- **BUT** an index-shaping parser, chunker, metadata, or embedding input changes
- **WHEN** the source is ingested again
- **THEN** `source_content_hash` MUST remain unchanged
- **AND** `source_version` MUST change

#### Scenario: Production metadata uses one content-hash name

- **WHEN** a new production-ingested chunk is persisted
- **THEN** it MUST contain `source_content_hash`
- **AND** it MUST NOT contain a duplicate `document_hash` alias

### Requirement: Chunks have deterministic identities within one source version

After parsing, chunking, and metadata extraction, the system SHALL derive the
text-only chunk content with `MetadataMode.NONE`. It SHALL calculate the
text hash as SHA-256 over that UTF-8 text and calculate `chunk_id` as
`"chk_" + SHA-256(source_id + NUL + source_version + NUL + decimal
source_chunk_index + NUL + chunk_text_hash)`. Every chunk index SHALL be
zero-based.

#### Scenario: Forced re-ingestion reproduces stable chunk identities

- **GIVEN** source bytes, index-shaping inputs, emitted chunk text, and chunk order are unchanged
- **WHEN** a forced re-ingestion processes that source
- **THEN** every chunk MUST reproduce its prior `chunk_id`

#### Scenario: Changed chunk text changes the chunk identity

- **GIVEN** one chunk occupies the same ordinal in a later source version
- **BUT** its emitted text changes
- **WHEN** its `chunk_id` is calculated
- **THEN** the new `chunk_id` MUST differ from the prior chunk's ID

#### Scenario: Repeated equal text at different positions remains distinguishable

- **GIVEN** two chunks in one source version contain identical text
- **BUT** they have different `source_chunk_index` values
- **WHEN** their IDs are calculated
- **THEN** their `chunk_id` values MUST differ

### Requirement: Stable chunk identity is separate from replacement row identity

The system SHALL retain a unique `source_attempt` for each replacement. The
vector-store row ID SHALL be attempt-specific and SHALL be derived from
`source_id`, `source_attempt`, and `chunk_id`. A stable `chunk_id` SHALL NOT be
used as the vector-store primary key. Candidate and prior attempts SHALL be
allowed to coexist until the candidate is durably verified.

#### Scenario: Identical forced replacement does not overwrite durable rows early

- **GIVEN** a complete source version is already durable
- **WHEN** an identical version is forcibly re-ingested
- **THEN** candidate chunks MUST retain the same public `chunk_id` values
- **AND** candidate vector-row IDs MUST differ from the durable row IDs
- **AND** prior rows MUST remain until the complete candidate attempt is verified

#### Scenario: Failed replacement preserves the last durable version

- **GIVEN** an existing source version is searchable
- **WHEN** parsing, embedding, validation, writing, or durability verification of a candidate fails
- **THEN** the prior version MUST remain searchable
- **AND** stable lineage MUST NOT weaken ADR-048 replacement safety

### Requirement: Lineage is stamped before embedding but excluded from model text

The system SHALL calculate and stamp all source, version, attempt, count,
index, and chunk identity fields after parsing/chunking and metadata extraction
but before embedding. Every machine identity and replacement field SHALL be
present in both `excluded_embed_metadata_keys` and
`excluded_llm_metadata_keys`. Lineage stamping SHALL NOT change the text sent
to the embedding model or an LLM.

#### Scenario: Lineage metadata does not change an embedding payload

- **GIVEN** one chunk has completed ordinary metadata extraction
- **WHEN** production lineage is stamped
- **THEN** `node.get_content(metadata_mode=MetadataMode.EMBED)` MUST remain unchanged
- **AND** the persisted node MUST still contain every lineage field

#### Scenario: Lineage metadata is not sent to an LLM

- **WHEN** LLM-visible content is derived from a lineage-stamped node
- **THEN** `source_id`, `chunk_id`, source version/order fields, and attempt identity MUST be absent from that content

### Requirement: LlamaIndex source relationships use the stable source identity

Every production-ingested chunk SHALL carry one
`NodeRelationship.SOURCE` whose `RelatedNodeInfo.node_id` equals `source_id`.
The human-readable path SHALL remain in `file_path` metadata. Code SHALL use the
`SOURCE` relationship as the maintained LlamaIndex contract rather than build
new logic around the deprecated `ref_doc_id` property.

#### Scenario: Five chunks share one source relationship

- **GIVEN** one source emits five chunks
- **WHEN** lineage is stamped
- **THEN** all five chunks MUST have the same `SOURCE` relationship node ID
- **AND** that node ID MUST equal their shared `source_id`

### Requirement: One source version is a complete ordered chunk set

For one `source_id` and `source_version`, every production attempt with `N`
chunks SHALL stamp `source_chunk_count=N` on every chunk. It SHALL assign
unique, contiguous `source_chunk_index` values from `0` through `N-1` and one
unique `chunk_id` per index. These fields SHALL be sufficient to select,
validate, and order the indexed chunk representation.

#### Scenario: Five chunks reconstruct one ordered indexed representation

- **GIVEN** source A emits five chunks for one `source_version`
- **WHEN** its persisted chunks are selected and sorted by `source_chunk_index`
- **THEN** the indices MUST be exactly `0, 1, 2, 3, 4`
- **AND** every chunk MUST declare `source_chunk_count=5`
- **AND** every chunk MUST have a unique `chunk_id`

#### Scenario: Missing or duplicate indices are not a complete set

- **GIVEN** persisted rows for one source version omit an expected index or repeat one index
- **WHEN** completeness is evaluated
- **THEN** the set MUST NOT be represented as a complete ordered source version

#### Scenario: Reconstruction does not claim original-file recovery

- **WHEN** a consumer orders all chunks for one source version
- **THEN** the result MAY reconstruct the indexed chunk sequence
- **BUT** it MUST NOT be described as a byte-perfect reconstruction of the original source, PDF layout, or parser input

### Requirement: Lineage persists and survives every public retrieval path

Every production-ingested chunk SHALL persist `source_id`,
`source_content_hash`, `source_index_identity`, `source_version`, `chunk_id`,
`source_attempt`, `source_chunk_count`, `source_chunk_index`, and `file_path` in
node metadata through ChromaDB and LanceDB. Public search results SHALL expose
`source_id`, `source_version`, `chunk_id`, `source_chunk_index`, and
`source_chunk_count` as additive top-level fields. Dense, BM25, hybrid fusion,
and successful or failed reranking SHALL preserve those values. Ordinary
public results SHALL continue to hide the attempt-specific vector-row ID.

#### Scenario: Dense and BM25 results expose the same lineage

- **GIVEN** one indexed chunk is returned by dense and BM25 retrieval
- **WHEN** each result is adapted to the core result shape
- **THEN** both results MUST expose identical stable lineage fields

#### Scenario: Fusion and reranking preserve lineage

- **GIVEN** candidate results contain stable lineage
- **WHEN** hybrid fusion and optional reranking reorder or rescore them
- **THEN** their lineage values MUST remain unchanged

#### Scenario: Public result hides the replacement row ID

- **WHEN** a caller searches without internal diagnostics
- **THEN** the result MUST contain stable `chunk_id`
- **AND** it MUST NOT expose the attempt-specific vector-row `id`

#### Scenario: Existing metadata filters select lineage

- **WHEN** a search uses an existing metadata filter on `source_id`, `source_version`, or `chunk_id`
- **THEN** only matching chunks MUST be eligible
- **AND** no new lineage-specific query API MUST be required

### Requirement: Listing and lifecycle operations use stable source identity

Document listing SHALL group production-ingested chunks by `source_id` while
retaining the associated human-readable `file_path`. Unchanged-version
selection, replacement cleanup, deletion preview, and path deletion SHALL use
the same canonical source-ID derivation. A metadata deletion MAY select
`source_id` through the existing general filter operation.

#### Scenario: Listing groups five chunks as one source

- **GIVEN** five chunks share one `source_id`
- **WHEN** documents are listed
- **THEN** they MUST appear as one source with a chunk count of five
- **AND** the listing MUST include both `source_id` and the human-readable source path

#### Scenario: Replacement cleanup is source scoped

- **GIVEN** two sources have equal bytes but different `source_id` values
- **WHEN** one source is successfully replaced
- **THEN** stale cleanup MUST remove only rows belonging to that `source_id`

### Requirement: Production lineage does not retrofit experiment precomputed rows

The stable source/chunk lineage contract SHALL apply to nodes produced by
`ingest_path_async`. It SHALL NOT require experiment-only
`upsert_precomputed()` rows to invent file lineage, migrate existing experiment
indexes, or change frozen experiment-owned row IDs.

#### Scenario: Existing experiment index remains governed by its manifest

- **GIVEN** an experiment builds rows through `upsert_precomputed()` with its own stable IDs
- **WHEN** production lineage is introduced
- **THEN** the experiment MUST remain governed by its frozen corpus and index manifest
- **AND** no production lineage migration MUST run against that index

### Requirement: Unexpected pre-lineage production rows fail before mutation

The system SHALL NOT silently mix current lineage rows with rows for the same
canonical `file_path` that lack or disagree on `source_id`. Before parsing,
embedding, or store mutation, production ingestion SHALL detect that
incompatible state and return a clear instruction to rebuild the affected
collection or source. It SHALL NOT add aliases, infer missing IDs, dual-write
schemas, or automatically migrate the rows.

#### Scenario: A path has rows without source identity

- **GIVEN** a collection contains rows for a canonical `file_path`
- **AND** those rows lack the derived `source_id`
- **WHEN** production ingestion processes that path
- **THEN** ingestion MUST fail before parsing, embedding, or store mutation
- **AND** the error MUST instruct the operator to rebuild the affected data
- **AND** the existing rows MUST remain unchanged

#### Scenario: Experiment-only rows are not scanned as production sources

- **GIVEN** an experiment collection contains precomputed rows with no production `file_path`
- **WHEN** production lineage is introduced
- **THEN** no startup scan or migration MUST inspect or modify that collection
