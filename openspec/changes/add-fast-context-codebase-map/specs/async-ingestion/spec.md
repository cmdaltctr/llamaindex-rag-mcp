## MODIFIED Requirements

### Requirement: Async ingestion entry point

The system SHALL expose `ingest_path_async(path, ...)` in `rag_mcp.ingestion`
as the primary ingestion function. The function SHALL be declared `async def`
and SHALL return the same result dictionary shape as the existing
`ingest_path()` (`files_indexed`, `chunks_created`, `file_details`, plus the
optional `error_type` / `message` fields). When ingesting Markdown files
(`.md` extension), ingestion SHALL route the chunking step to a heading-aware
node parser; for all other file types, ingestion SHALL use the existing
default splitter. **Additionally, when Magika content-type detection is
available, ingestion SHALL dispatch chunking based on the detected content
type: `CodeSplitter` for `code/*` files, skip for binary files, whole-file
for config files, and existing splitters for documents.**

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

#### Scenario: Async ingest reports embedding connection failures

- **WHEN** `await ingest_path_async("/path")` is called and Ollama is
  unreachable
- **THEN** the returned dict SHALL include `error_type: "connection"` and a
  human-readable `message`
- **THEN** the dict SHALL NOT raise — the async function SHALL never
  propagate the connection error as an exception

#### Scenario: Code file dispatched to CodeSplitter via Magika

- **WHEN** Magika detects a file as `code/typescript` during `ingest_path_async`
- **THEN** the ingestion pipeline SHALL use `CodeSplitter` with the `typescript` tree-sitter grammar
- **THEN** resulting chunks SHALL respect function/class boundaries

#### Scenario: Binary file skipped during ingestion

- **WHEN** Magika detects a file as `executable/elf` during `ingest_path_async`
- **THEN** the file SHALL be skipped — no reading, chunking, or embedding
- **THEN** an INFO log SHALL record the skip with filename and detected type
- **THEN** `file_details` SHALL include an entry with `status="skipped"` and `content_type="executable/elf"`

#### Scenario: Azure document backend dispatch

- **WHEN** `DOCUMENT_BACKEND=azure` is configured
- **AND** a PDF file is encountered during `ingest_path_async`
- **THEN** the file SHALL be sent to Azure Document Intelligence instead of LiteParse
- **THEN** the resulting structured JSON SHALL be converted to table-aware chunks

## ADDED Requirements

### Requirement: Type-aware dispatch integration in ingestion pipeline

The `_read_and_chunk_file_async()` function SHALL accept a `content_type` parameter (string, from Magika or suffix detection). The function SHALL use this parameter to select the chunking strategy before falling back to extension-based routing. The dispatch order SHALL be: content_type match → extension match → default `SentenceSplitter`.

#### Scenario: Content type takes precedence over extension

- **WHEN** a file named `utils.txt` is detected by Magika as `code/javascript`
- **THEN** the chunking strategy SHALL use `CodeSplitter(language="javascript")`, not `SentenceSplitter`

#### Scenario: Content type not available

- **WHEN** Magika is not installed and `content_type` is `None`
- **THEN** the dispatch SHALL fall through to extension-based routing (existing behaviour)
