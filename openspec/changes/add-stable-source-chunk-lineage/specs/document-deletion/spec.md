# document-deletion Specification Delta

## MODIFIED Requirements

### Requirement: Delete chunks by source file path

The system SHALL provide a
`core/ingestion/writer.py::remove_document(file_path: str,
collection_name: str = "documents") -> dict` function that applies the same
canonical path resolution and deterministic `source_id` derivation as
production ingestion, then deletes all chunks whose `source_id` matches. The
function SHALL be idempotent: calling it for a source with no indexed chunks
SHALL return success with `chunks_removed: 0`. The existing general metadata
deletion operation MAY delete a source directly with a `source_id` filter.

#### Scenario: Delete existing file chunks

- **WHEN** `remove_document("/path/to/file.pdf", collection_name="research")` is called on a source with 12 indexed chunks
- **THEN** the function MUST derive the same `source_id` used during ingestion
- **AND** all 12 chunks for that `source_id` SHALL be removed from the `"research"` collection
- **AND** the result SHALL include `"chunks_removed": 12` and `"status": "ok"`

#### Scenario: Delete non-existent file chunks

- **WHEN** `remove_document("/path/to/unknown.pdf")` is called
- **THEN** the result SHALL include `"chunks_removed": 0` and `"status": "ok"`
- **AND** no error SHALL be raised

#### Scenario: Delete from non-existent collection

- **WHEN** `remove_document("/path/to/file.pdf", collection_name="nonexistent")` is called
- **THEN** the result SHALL include `"status": "error"` and a descriptive message

### Requirement: Re-ingestion replaces old chunks (upsert semantics)

When `ingest_path_async` processes a source whose `source_id` already has
durable rows, the system SHALL retain the last searchable attempt while it
parses, chunks, embeds, writes, and verifies the complete candidate attempt.
Only after verification SHALL it remove stale row IDs for that `source_id`.
Stable `chunk_id` values SHALL remain separate from attempt-specific vector-row
IDs so an identical forced re-ingestion cannot overwrite durable rows early.

#### Scenario: Re-ingest replaces chunks after verification

- **GIVEN** `paper.pdf` previously produced eight durable chunks
- **WHEN** `ingest_path_async("paper.pdf", collection_name="research")` writes and verifies a replacement
- **THEN** the old eight chunks SHALL remain searchable until verification succeeds
- **AND** stale rows for that `source_id` SHALL then be removed
- **AND** the result SHALL include the new `chunks_created` count and `"chunks_removed": 8`

#### Scenario: First-time ingest has nothing to remove

- **WHEN** `ingest_path_async("new_file.pdf")` processes a source whose `source_id` is absent
- **THEN** no stale rows SHALL be selected
- **AND** the result SHALL include `"chunks_removed": 0`

#### Scenario: Failed replacement preserves durable chunks

- **GIVEN** one source has a complete durable attempt
- **WHEN** its candidate parse, embedding, validation, write, or verification fails
- **THEN** the durable attempt MUST remain searchable
- **AND** no stale-row cleanup MUST delete it
