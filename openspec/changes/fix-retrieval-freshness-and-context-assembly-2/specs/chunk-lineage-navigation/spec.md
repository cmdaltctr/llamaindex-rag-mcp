## ADDED Requirements

### Requirement: Chunk neighbours are resolvable from persisted metadata

The system SHALL provide neighbour, span and ordered-set lookup for stored
chunks using only metadata already persisted by ingestion — `source_id`,
`source_chunk_index` and `source_chunk_count` — and the vector store's bounded filtered row-read contract.

This is the project's equivalent of a document store's
`PREVIOUS`/`NEXT` node relationships. It is deliberately not a document
store: a second store would have to be kept consistent with the vector store
across every failure path in `replacement.py`, which is the drift risk that
was rejected when change detection was designed. Persisted lineage is strictly
more capable for this purpose, because a relationship can only be walked
whereas lineage metadata can be queried directly.

#### Scenario: Neighbours of a chunk

- **GIVEN** a stored chunk with `source_id` S and `source_chunk_index` i
- **WHEN** its neighbours are requested with window w
- **THEN** the chunks of S with index in `[i-w, i+w]`, excluding i and clamped
  to `[0, source_chunk_count)`, SHALL be returned in ascending index order

#### Scenario: Neighbour lookup crosses no source boundary

- **GIVEN** two sources whose chunks are interleaved in storage order
- **WHEN** neighbours are requested for a chunk of one source
- **THEN** no chunk of the other source SHALL be returned, even where indices
  coincide

#### Scenario: Edges of a source are handled

- **GIVEN** the first (index 0) or last (index `source_chunk_count - 1`) chunk
- **WHEN** neighbours are requested
- **THEN** only the existing side SHALL be returned
- **AND** no error SHALL be raised

#### Scenario: Rows without lineage are inert

- **GIVEN** a row lacking `source_id` or `source_chunk_index`, such as an
  experiment precomputed row
- **WHEN** neighbour lookup encounters it
- **THEN** it SHALL be skipped rather than raising
- **AND** the retrieved row itself SHALL still be returned to the caller

#### Scenario: Lookup is bounded

- **WHEN** neighbours are requested for a result set
- **THEN** the number of rows read SHALL be bounded by the requested window
  and result count
- **AND** the implementation SHALL NOT read the whole collection

### Requirement: Contiguity is decidable

The system SHALL be able to determine whether two stored chunks are adjacent
in their source, so that assembly can act on contiguity rather than on text
similarity heuristics.

#### Scenario: Adjacent chunks are recognised

- **GIVEN** two chunks sharing a `source_id` with indices i and i+1
- **WHEN** contiguity is evaluated
- **THEN** they SHALL be reported adjacent

#### Scenario: Chunks of different sources are never adjacent

- **GIVEN** two chunks with different `source_id` values
- **WHEN** contiguity is evaluated
- **THEN** they SHALL NOT be reported adjacent, whatever their indices

#### Scenario: Chunks of different source versions are never adjacent

- **GIVEN** two chunks sharing a `source_id` but carrying different
  `source_version` values
- **WHEN** contiguity is evaluated
- **THEN** they SHALL NOT be reported adjacent, because they describe
  different versions of the document
