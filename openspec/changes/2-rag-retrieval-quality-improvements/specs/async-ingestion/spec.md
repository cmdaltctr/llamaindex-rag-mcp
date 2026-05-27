## MODIFIED Requirements

### Requirement: Async ingestion entry point

The system SHALL expose `ingest_path_async(path, ...)` in `rag_mcp.ingestion`
as the primary ingestion function. The function SHALL be declared `async def`
and SHALL return the same result dictionary shape as the existing
`ingest_path()` (`files_indexed`, `chunks_created`, `file_details`, plus the
optional `error_type` / `message` fields). When ingesting Markdown files
(`.md` extension), ingestion SHALL route the chunking step to a
heading-aware node parser; for all other file types, ingestion SHALL use the
existing default splitter.

#### Scenario: Async ingest produces same result shape as sync ingest
- **WHEN** `await ingest_path_async("/path/to/folder")` completes successfully
- **THEN** the returned dict SHALL contain `files_indexed`, `chunks_created`,
  and `file_details` with the same keys and types as `ingest_path()`'s return
  dict
- **THEN** the `file_details` entries SHALL contain `file`, `status`, `chunks`
  fields, and `error` only when `status == "failed"`

#### Scenario: Markdown file is routed to heading-aware parser
- **WHEN** `await ingest_path_async("/docs/notes.md")` is called
- **THEN** the chunking step for that file SHALL use the heading-aware node parser
- **THEN** the returned `file_details` entry SHALL still contain the standard `file`, `status`, and `chunks` fields

#### Scenario: Non-Markdown file uses default splitter
- **WHEN** `await ingest_path_async("/docs/report.pdf")` is called
- **THEN** the chunking step for that file SHALL use the existing default splitter
- **THEN** the resulting chunk count SHALL match the previous default behaviour for the same file
