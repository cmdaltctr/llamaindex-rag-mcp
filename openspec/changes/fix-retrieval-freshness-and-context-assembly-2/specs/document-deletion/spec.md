## ADDED Requirements

### Requirement: Stale-version selection is source-scoped

When replacing a source version, the selection of rows to delete SHALL be
scoped to that source's `source_id` at the store level. The implementation
SHALL NOT read the whole collection to find them.

The correctness guarantee is unchanged — only rows belonging to this
`source_id` and not to the current replacement attempt are deleted — but the
work performed SHALL be proportional to the source's own row count, not to the
collection's. The previous implementation iterated every row in the collection
for every replaced file, inside the global write lock, making re-ingestion
cost O(files × collection size) and blocking concurrent ingestion.

#### Scenario: Selection reads only the source's rows

- **GIVEN** a collection containing many sources
- **WHEN** one source is replaced
- **THEN** the number of rows read to select stale rows SHALL be proportional
  to that source's row count
- **AND** SHALL NOT be proportional to the collection's total row count

#### Scenario: Only stale rows of this source are deleted

- **GIVEN** a source with rows from a previous attempt and rows from the
  current verified attempt
- **WHEN** stale cleanup runs
- **THEN** exactly the previous attempt's rows SHALL be deleted
- **AND** no row of any other source SHALL be deleted, including a
  byte-identical file at another path

#### Scenario: Backends differing on missing-key inequality stay correct

- **GIVEN** a store whose filter semantics treat a missing metadata key
  differently under inequality
- **WHEN** stale selection runs
- **THEN** the attempt comparison SHALL be performed such that rows lacking
  the attempt key are not silently included or excluded by backend semantics

#### Scenario: Cleanup cost is observable

- **WHEN** a source is replaced
- **THEN** the existing `cleanup_seconds` stage timing SHALL continue to be
  reported for that source
