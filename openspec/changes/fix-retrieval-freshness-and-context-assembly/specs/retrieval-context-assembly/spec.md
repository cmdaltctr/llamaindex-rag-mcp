## ADDED Requirements

### Requirement: Retrieval has an explicit context-assembly stage

The retrieval pipeline SHALL run a named assembly stage between final ranking
and return. The stage SHALL be the single place where returned evidence is
reshaped, and it SHALL NOT re-rank, re-score, or drop evidence.

#### Scenario: Assembly runs after ranking

- **WHEN** a search completes ranking and truncation
- **THEN** assembly SHALL run on the final result set
- **AND** the relative order established by ranking SHALL be preserved unless a
  scenario below states otherwise

#### Scenario: Assembly never removes evidence

- **WHEN** assembly runs
- **THEN** every distinct chunk present before assembly SHALL still be
  represented afterwards, either as its own row or as part of a merged row
- **AND** no chunk's unique text SHALL be lost

### Requirement: Overlapping adjacent chunks are merged, not returned twice

When two returned chunks are adjacent in the same source and the same source
version, the assembly stage SHALL emit one row whose text contains the union
of their content with the chunker's overlap present once, rather than two rows
repeating the overlap.

#### Scenario: Adjacent chunks are merged

- **GIVEN** a result set containing chunks at indices i and i+1 of one source
  version, produced with a non-zero `chunking.chunk_overlap`
- **WHEN** assembly runs
- **THEN** one merged row SHALL be emitted
- **AND** its text SHALL contain each source sentence once
- **AND** its character length SHALL be less than the sum of the two inputs

#### Scenario: Non-adjacent chunks are not merged

- **GIVEN** a result set containing chunks at indices i and i+3 of one source
- **WHEN** assembly runs
- **THEN** two rows SHALL be emitted

#### Scenario: Chunks from different sources are not merged

- **GIVEN** two chunks with different `source_id` values
- **WHEN** assembly runs
- **THEN** they SHALL NOT be merged, whatever their indices

#### Scenario: A merged row reports its constituents

- **WHEN** a merged row is returned
- **THEN** it SHALL expose the `chunk_id` of every constituent chunk
- **AND** its `source_chunk_index` SHALL be the lowest constituent index
- **AND** its score SHALL be the best (highest) constituent score
- **AND** its `score_kind` SHALL be the kind of that best-scoring constituent

#### Scenario: Citations remain verifiable after merging

- **GIVEN** a merged row
- **WHEN** any of its reported constituent `chunk_id` values is used as a
  metadata filter
- **THEN** exactly the corresponding stored chunk SHALL be retrievable

#### Scenario: Zero overlap is a no-op

- **GIVEN** a collection ingested with `chunking.chunk_overlap = 0`
- **WHEN** adjacent chunks are returned
- **THEN** merging SHALL still concatenate them into one row
- **AND** no text SHALL be removed, because there is no overlap to remove

### Requirement: Neighbour expansion is opt-in and bounded

The assembly stage SHALL be able to add a chunk's neighbours to the returned
context. Expansion SHALL be off by default, SHALL be requested explicitly per
operation, and SHALL be bounded by a configured window.

#### Scenario: Expansion is off by default

- **WHEN** a search runs without requesting expansion
- **THEN** no chunk absent from the ranked result set SHALL be returned

#### Scenario: Expansion adds neighbours

- **WHEN** a search runs with expansion requested and window 1
- **THEN** the immediate neighbours of each retrieved chunk SHALL be added
- **AND** added rows SHALL be marked as expansion rather than retrieval
- **AND** added rows SHALL NOT carry a retrieval score

#### Scenario: Expanded rows do not displace retrieved rows

- **GIVEN** a search with `top_k` = k and expansion requested
- **WHEN** assembly runs
- **THEN** all k retrieved chunks SHALL still be present
- **AND** expansion SHALL NOT cause a retrieved chunk to be dropped to honour
  `top_k`

#### Scenario: Expansion composes with merging

- **GIVEN** expansion adds a chunk adjacent to a retrieved chunk
- **WHEN** assembly runs
- **THEN** the two SHALL be merged under the merging rules above

### Requirement: Assembly behaviour is observable

The assembly stage SHALL report what it did under the existing diagnostics
flag, using the established per-stage timing surface.

#### Scenario: Diagnostics report assembly

- **WHEN** a search runs with diagnostics enabled
- **THEN** each row SHALL report whether it was merged and from how many
  chunks, and whether it was added by expansion
- **AND** the timing report SHALL include an assembly duration

#### Scenario: Public results stay stable

- **WHEN** a search runs without diagnostics
- **THEN** assembly-internal fields SHALL be stripped exactly as other
  internal fields are
