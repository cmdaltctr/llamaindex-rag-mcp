## ADDED Requirements

### Requirement: Ingestion result reports metadata degradation

The async ingestion result dict SHALL report when metadata extraction degraded from the configured LLM-backed mode to a fallback tier for one or more files. The result SHALL carry a top-level `metadata_degraded` integer counting the files whose metadata was produced by a fallback. Each affected entry in `file_details` SHALL carry a marker (`metadata_degraded: true`) so the caller can identify which files were affected. Files whose metadata extraction succeeded in the configured mode SHALL NOT set the marker, and SHALL NOT be counted.

These fields SHALL be additive: all existing result keys (`status`, `files_indexed`, `chunks_created`, `chunks_removed`, `collection`, `file_details`, and any `warnings`) and all existing `file_details` keys (`file`, `status`, `chunks`) SHALL retain their current names and types. The `metadata_degraded` count SHALL be present on every ingestion result dict (including error responses) and SHALL be `0` when no file degraded.

#### Scenario: No degradation reports zero

- **WHEN** ingestion runs and every file's metadata is extracted in the configured mode
- **THEN** the result dict SHALL contain `metadata_degraded` equal to `0`
- **THEN** no `file_details` entry SHALL carry a `metadata_degraded` marker

#### Scenario: One file degrades

- **WHEN** ingestion runs over three files and one file's metadata extraction falls back to keyword mode
- **THEN** the result dict SHALL contain `metadata_degraded` equal to `1`
- **THEN** exactly the affected `file_details` entry SHALL carry `metadata_degraded: true`

#### Scenario: Existing result keys are unchanged

- **WHEN** ingestion completes
- **THEN** the result dict SHALL still contain `files_indexed`, `chunks_created`, `chunks_removed`, `collection`, and `file_details` with their existing types
- **THEN** each `file_details` entry SHALL still contain `file`, `status`, and `chunks`

#### Scenario: Embedding failure preserves degradation count

- **WHEN** ingestion reads files (some degrading) and then the embedding step fails
- **THEN** the error result dict SHALL contain `metadata_degraded` reflecting the count of files that degraded before the failure
