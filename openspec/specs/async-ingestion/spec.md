## Purpose

Define the asynchronous ingestion contract so document ingestion can run without blocking MCP tool handling while preserving existing ingestion result shapes and metadata extraction behaviour.
## Requirements
### Requirement: Async ingestion entry point

The system SHALL expose `ingest_path_async(path, ...)` in `rag_mcp.ingestion`
as the primary ingestion function. The function SHALL be declared `async def`
and SHALL return the same result dictionary shape as the existing
`ingest_path()` (`files_indexed`, `chunks_created`, `file_details`, plus the
optional `error_type` / `message` fields). When ingesting Markdown files
(`.md` extension), ingestion SHALL route the chunking step to a heading-aware
node parser; for all other file types, ingestion SHALL use the existing
default splitter.

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

### Requirement: Event loop responsiveness during ingest

When ingestion runs inside the MCP server's event loop, the loop SHALL remain
able to service other tool calls. A concurrent MCP `search` request issued
while a long ingest is in flight SHALL receive a response without waiting for
the ingest to complete. MCP search SHALL not execute blocking embedding or
ChromaDB retrieval work directly on the event-loop thread.

#### Scenario: Search responds during in-flight ingest

- **WHEN** an `ingest_path_async("/large/folder")` task is in progress
- **AND** an MCP client issues a `search(query="x", top_k=5)` call
- **THEN** the search SHALL return its result within 500 ms
- **THEN** the ingest SHALL continue to run uninterrupted to completion

#### Scenario: Search offloads synchronous retrieval

- **WHEN** `search_documents(...)` is called via MCP
- **THEN** the MCP handler SHALL be asynchronous
- **THEN** synchronous retrieval work SHALL be offloaded from the event-loop
  thread

#### Scenario: Chunk splitting is offloaded

- **WHEN** `ingest_path_async` splits loaded documents into nodes
- **THEN** the splitter call SHALL be offloaded from the event-loop thread
- **THEN** other tasks scheduled on the loop SHALL be eligible to run while splitting proceeds

#### Scenario: Multiple MCP tool calls interleave during ingest

- **WHEN** an ingest is in progress
- **AND** the MCP client issues `list_collections` and `search` calls in
  sequence
- **THEN** both calls SHALL return without waiting for ingest to finish
- **THEN** the result of each tool call SHALL be correct (no torn reads of
  ChromaDB state)

### Requirement: Async metadata extraction dispatch

The `extract_metadata_async(file_text, file_name)` function SHALL be the
async counterpart of `extract_metadata()`. It SHALL dispatch to async
variants of each extraction mode (`_extract_keyword_async`,
`_extract_ollama_async`, `_extract_llamaindex_async`) and SHALL return the
same metadata dict shape as the sync version.

#### Scenario: Async metadata extraction in ollama mode

- **WHEN** `METADATA__EXTRACTION_MODE=ollama` and `await
  extract_metadata_async(text, "doc.pdf")` is called
- **THEN** the function SHALL issue an HTTP request to Ollama using a
  non-blocking HTTP client
- **THEN** the function SHALL return a dict with `category`, `keywords`,
  `summary` (same shape as sync `extract_metadata()`)

#### Scenario: Async metadata extraction in llamaindex mode

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex` and
  `await extract_metadata_async(text, "doc.pdf")` is called
- **THEN** the function SHALL call `IngestionPipeline.arun()` directly
  (not the sync `pipeline.run()` with a thread offload)
- **THEN** the function SHALL not raise "Detected nested async" regardless
  of the surrounding event-loop context

### Requirement: ChromaDB writes do not block the loop

All ChromaDB sync calls in the async ingest path SHALL be wrapped in
`asyncio.to_thread(...)` (or an equivalent loop-yielding mechanism) and
SHALL NOT be invoked directly on the loop thread. This applies to
`chroma_collection.add(...)`, `chroma_collection.delete(...)`, and
`chroma_collection.get(...)`. ChromaDB's `PersistentClient` is sync-only,
so this wrapping is the only way to keep the loop responsive while writes
run.

#### Scenario: Loop yields during ChromaDB write

- **WHEN** `ingest_path_async` writes a batch of chunks to ChromaDB
- **THEN** the loop SHALL be yielded for the duration of the write
- **THEN** other tasks scheduled on the loop SHALL be eligible to run

### Requirement: Watcher dispatches via running loop

The file watcher (`rag_mcp.watcher`) SHALL submit ingestion work to the MCP
event loop via `asyncio.run_coroutine_threadsafe(...)` rather than calling
ingestion synchronously from the watcher thread. The watcher SHALL capture
a reference to the running loop at startup.

#### Scenario: Watcher runs ingest on the MCP loop

- **WHEN** the watcher is started by the MCP server and a supported file is
  modified
- **THEN** the watcher SHALL submit `ingest_path_async(file_path)` to the
  MCP loop via `run_coroutine_threadsafe`
- **THEN** the ingest SHALL execute on the MCP loop, not on the watcher
  thread

#### Scenario: Ingest exceptions surface to the watcher

- **WHEN** an ingest scheduled via `run_coroutine_threadsafe` raises an
  exception
- **THEN** the watcher SHALL log the exception at WARNING level via a
  `Future.add_done_callback`
- **THEN** the exception SHALL NOT crash the MCP loop or the watcher

### Requirement: CLI wraps async ingest

The CLI subcommand `rag-mcp ingest` SHALL invoke `ingest_path_async(...)`
via `asyncio.run(...)` at the entry point. CLI flags, output format, exit
codes, and report generation SHALL describe only controls that affect
current async ingestion behavior. The CLI SHALL NOT present a file-reader
`--workers` option as effective unless file-level parallel reading is
implemented.

#### Scenario: CLI ingest uses async entry point

- **WHEN** the user runs `rag-mcp ingest /path/to/docs`
- **THEN** the CLI SHALL invoke `asyncio.run(ingest_path_async("/path/to/docs"))`
- **THEN** stderr output, exit code, and `--report` output SHALL reflect the
  async implementation

#### Scenario: Ingest help omits ineffective workers option

- **WHEN** the user runs `rag-mcp ingest --help`
- **THEN** the help output SHALL NOT advertise file-reader workers as an
  effective throughput control
- **THEN** the help output SHALL continue to document effective chunking,
  collection, report, and JSON options

#### Scenario: Ingest report omits ineffective workers setting

- **WHEN** `rag-mcp ingest /docs --report report.json` runs
- **THEN** the generated report SHALL NOT claim a file-reader worker count
  affected the run
- **THEN** the report MAY include effective embedding batch size and embedding
  concurrency settings

### Requirement: Sync `ingest_path` retired

The async path SHALL be the sole supported ingestion entry point. Once all
callers (CLI, watcher, MCP server) use `ingest_path_async`, the sync
`ingest_path()` function SHALL be removed from `rag_mcp.ingestion`, and
the `ThreadPoolExecutor` workaround in
`rag_mcp.metadata_extractor._extract_llamaindex` SHALL also be removed.

#### Scenario: Sync ingestion entry point no longer exists

- **WHEN** code attempts to import `ingest_path` (without the `_async`
  suffix) from `rag_mcp.ingestion`
- **THEN** the import SHALL fail with `ImportError`

#### Scenario: ThreadPoolExecutor workaround removed

- **WHEN** `_extract_llamaindex_async` is called
- **THEN** the function SHALL NOT contain a
  `concurrent.futures.ThreadPoolExecutor` branch for nested-loop avoidance
- **THEN** the function SHALL call `IngestionPipeline.arun()` directly

### Requirement: Tests verify responsiveness contract

The test suite SHALL include an integration test that verifies the
event-loop-responsiveness contract directly. The test SHALL be marked with
`@pytest.mark.asyncio` and SHALL fail if a future change re-introduces a
blocking sync call into the async ingest path.

#### Scenario: Responsiveness regression test

- **WHEN** the responsiveness test starts an `ingest_path_async` task on a
  fixture folder containing at least one file with non-trivial metadata
  extraction
- **AND** the test issues a concurrent mock-MCP `search` call after 100 ms
- **THEN** the search SHALL complete within 500 ms while the ingest is
  still running
- **THEN** the test SHALL await the ingest task to completion to confirm
  functional correctness was not sacrificed

### Requirement: Backward-compatible result data

The async migration SHALL preserve existing on-disk ChromaDB collections and
existing public result dict shapes. No schema migration SHALL be required to
read data written by the previous sync implementation. Ingestion reports and
CLI flags SHALL only include controls supported by the current async ingestion
implementation.

#### Scenario: Existing ChromaDB data continues to work

- **WHEN** a ChromaDB persisted by the sync `ingest_path` is opened by the
  async-only build
- **THEN** all collections, embeddings, and metadata SHALL be readable
  unchanged
- **THEN** subsequent `await ingest_path_async(...)` calls SHALL upsert
  into the same collections without schema migration

#### Scenario: `--report` output preserves core report structure

- **WHEN** `rag-mcp ingest /docs --report report.json` runs against the
  async build
- **THEN** the JSON report SHALL include `timestamp`, `config`, `input_path`,
  `summary`, and `files`
- **THEN** `config` SHALL NOT include ineffective file-reader worker settings

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

### Requirement: Unchanged files skip expensive reprocessing using complete index identity

The ingestion pipeline SHALL persist a source-content identity and an index-shaping identity for each stored source version. A file MAY be skipped as unchanged only when its content identity and every index-shaping input that affects stored chunks/vectors match the existing indexed version.

Index-shaping identity SHALL cover at least effective embedding provider/model, parser/document backend where relevant, and chunking configuration/strategy that affects emitted text boundaries. A content-only hash SHALL NOT cause stale vectors/chunks to be reused after these values change. Files with different, missing, or mixed identities and files with no existing chunks SHALL be ingested normally. Binary files SHALL retain the existing `status: "skipped"` behaviour and SHALL NOT participate in change detection.

#### Scenario: Same bytes and same index identity
- **GIVEN** a previously indexed file whose content and index-shaping identity are unchanged
- **WHEN** the same path is ingested again
- **THEN** parse, chunk, embed and store-write work SHALL be skipped for that file

#### Scenario: Unchanged file is skipped on re-ingest
- **WHEN** a directory containing one file is ingested into a collection
- **AND** `ingest_path_async` is called again on the same directory and collection with the file unmodified and the index-shaping inputs unchanged
- **THEN** the file SHALL NOT be re-chunked or re-embedded
- **THEN** the collection's chunk count for that file SHALL remain unchanged

#### Scenario: File with no stored chunks is ingested
- **WHEN** an eligible non-binary file has no existing chunks in the target collection (never ingested, or its previous ingest produced zero chunks)
- **AND** `ingest_path_async` is called on its path
- **THEN** the file SHALL be ingested normally
- **AND** the file SHALL NOT be classified as `skipped_unchanged`

#### Scenario: Same bytes but embedding model changes
- **GIVEN** the source bytes are unchanged
- **BUT** the effective embedding model differs from the stored index identity
- **WHEN** ingestion runs
- **THEN** the file MUST be reprocessed rather than skipped

#### Scenario: Same bytes but parser or chunk settings change
- **GIVEN** the source bytes are unchanged
- **BUT** parser/document backend or chunk-shaping settings differ
- **WHEN** ingestion runs
- **THEN** the file MUST be reprocessed

#### Scenario: Modified file is re-ingested
- **WHEN** a previously ingested file is modified on disk
- **AND** `ingest_path_async` is called on the same path and collection
- **THEN** the file's previous chunks SHALL be deleted
- **THEN** the file SHALL be re-chunked and re-embedded
- **THEN** the stored source and index identities for the file SHALL be updated

#### Scenario: Legacy chunks without a stored hash are re-ingested once
- **WHEN** `ingest_path_async` runs against a collection persisted before content hashing existed (chunks carry no content-hash metadata)
- **THEN** all eligible non-binary files SHALL be re-ingested on that call
- **THEN** the re-ingested chunks SHALL carry `source_content_hash`
- **AND** a subsequent call with no file or index-shaping changes SHALL skip all eligible non-binary files

#### Scenario: Mixed directory skips only unchanged files
- **WHEN** a directory contains three previously ingested eligible non-binary files and exactly one has been modified
- **AND** `ingest_path_async` is called on the directory
- **THEN** only the modified file SHALL be re-ingested
- **THEN** the two unchanged files SHALL be skipped

#### Scenario: Mixed or missing chunk hashes force re-ingestion
- **WHEN** a file's existing chunks contain mixed hashes or a missing `source_content_hash`
- **AND** `ingest_path_async` is called with that file unmodified
- **THEN** the file SHALL be re-ingested
- **THEN** every replacement chunk SHALL carry the current hash

#### Scenario: Hash-read failure does not abort sibling files
- **WHEN** `sha256_file` raises `FileNotFoundError` or `OSError` for one file in a multi-file ingestion
- **THEN** that file SHALL be reported in `file_details` with `status: "failed"` and `chunks: 0`
- **THEN** its existing chunks SHALL remain untouched
- **AND** ingestion SHALL continue for the sibling files

#### Scenario: Binary files retain the existing skip behaviour
- **WHEN** a discovered supported-extension file is detected as binary
- **THEN** the file SHALL appear in `file_details` with `status: "skipped"`
- **THEN** the file SHALL NOT contribute to `files_skipped_unchanged`

### Requirement: Content hash stored in chunk metadata

For every ingested file, the system SHALL store the file's SHA-256 content
hash as `source_content_hash` in the ChromaDB metadata of every chunk belonging
to that file. Hash stamping SHALL occur whether `skip_unchanged` is `true` or
`false`. The field SHALL be additive: existing metadata fields (including
`file_path`) SHALL retain their names and types. A file whose content changes
between two ingests SHALL have every chunk's stored hash replaced with the new
hash.

#### Scenario: Chunks carry the content hash after ingest

- **WHEN** a supported non-binary file is ingested into a collection
- **THEN** every chunk written for that file SHALL include
  `source_content_hash` whose value is the SHA-256 hex digest of the file's
  bytes at ingest time

#### Scenario: Hash reflects the latest ingest

- **WHEN** a file is modified and re-ingested
- **THEN** the stored hash on all of the file's chunks SHALL equal the hash
  of the new content
- **THEN** no chunk SHALL retain the previous hash

### Requirement: Ingestion result reports skipped files

The ingestion result dict SHALL report skipped files additively. The result
SHALL carry a top-level `files_skipped_unchanged` integer counting eligible
non-binary files skipped by change detection. The key SHALL be present with
an integer value on every result dict, error returns included, and SHALL be
`0` when no file was skipped. Each file skipped by change
detection SHALL appear in `file_details` with `status: "skipped_unchanged"`
and `chunks: 0`. This status is distinct from the existing `"skipped"` status
for unsupported-extension and binary files. All existing result keys
(`status`, `files_indexed`, `chunks_created`, `chunks_removed`, `collection`,
`file_details`, `metadata_degraded`, `warnings`) and all existing
`file_details` keys SHALL retain their current names and types. Skipped files
SHALL NOT be counted in `files_indexed`, and their chunks SHALL NOT be counted
in `chunks_removed`.

#### Scenario: Fully unchanged directory reports all files skipped

- **WHEN** `ingest_path_async` is called on a directory where every eligible
  non-binary file is unchanged since the previous ingest into the collection
- **THEN** the result dict SHALL contain `files_skipped_unchanged` equal to
  the number of eligible non-binary files
- **THEN** `files_indexed` SHALL be `0` and `chunks_created` SHALL be `0`
- **THEN** the result `status` SHALL be `"ok"`

#### Scenario: Partially changed directory reports mixed counts

- **WHEN** a directory contains three eligible non-binary files, exactly one
  of which has been modified since the previous ingest
- **AND** `ingest_path_async` is called on the directory
- **THEN** `files_skipped_unchanged` SHALL be `2` and `files_indexed` SHALL
  be `1`
- **THEN** exactly two `file_details` entries SHALL have
  `status: "skipped_unchanged"`

#### Scenario: Existing result keys are unchanged

- **WHEN** any ingestion completes with change detection active
- **THEN** the result dict SHALL retain all existing keys with their
  existing types
- **THEN** `files_skipped_unchanged` SHALL be present and SHALL be `0` when
  no file was skipped

#### Scenario: Error results carry the skip counter

- **WHEN** `ingest_path_async` returns an error result dict
- **THEN** the dict SHALL include `files_skipped_unchanged` as an integer
- **AND** the value SHALL be `0` unless eligible files were skipped before
  the error

### Requirement: Change detection can be disabled per call

The system SHALL expose a `skip_unchanged` ingestion setting, configurable
via the nested environment variable `INGESTION__SKIP_UNCHANGED` with default
`true`. When set to `false`, `ingest_path_async` SHALL re-ingest every
eligible non-binary file regardless of stored hashes, while still stamping
every chunk with the current `source_content_hash`. This covers forced
re-embeds after changing the embedding model or chunking parameters, which
alter desired vectors without altering file content.

#### Scenario: Opt-out forces full re-ingest

- **WHEN** `INGESTION__SKIP_UNCHANGED=false` is set
- **AND** `ingest_path_async` is called on an unchanged, previously ingested
  directory
- **THEN** every eligible non-binary file SHALL be re-chunked and re-embedded
- **THEN** `files_skipped_unchanged` SHALL be `0`

#### Scenario: Default leaves change detection active

- **WHEN** no `INGESTION__SKIP_UNCHANGED` value is configured
- **THEN** change detection SHALL be active (behaviour identical to `true`)

### Requirement: Directory ingestion has bounded in-memory node lifetime

`ingest_path_async()` SHALL NOT retain every emitted node for an arbitrarily large directory before the first write. The pipeline SHALL process and persist explicitly bounded units, with one source file at a time as the minimum acceptable bound unless a smaller batch is required for a single large file.

#### Scenario: Corpus size increases by file count
- **GIVEN** a generated corpus of many independent files
- **WHEN** the corpus is ingested
- **THEN** the number of simultaneously retained source-file node sets MUST remain bounded independently of total file count
- **AND** successful earlier files MAY become durable before later files have been parsed

### Requirement: Replacement preserves the last durable searchable version on failure

Updating an already-indexed source SHALL NOT delete the last durable searchable version merely because a later parse, chunk, embedding or store-write step fails. New-version rows SHALL become durable and be verified before stale-version rows are removed, or another store-neutral mechanism SHALL provide the same safety property.

#### Scenario: Parse failure during update
- **GIVEN** version A of a source is indexed and searchable
- **AND** a replacement ingest fails during parsing
- **WHEN** the operation returns an error for that source
- **THEN** version A MUST remain searchable

#### Scenario: Embedding failure during update
- **GIVEN** version A is indexed
- **AND** replacement version B parses/chunks but embedding fails
- **THEN** version A MUST remain searchable

#### Scenario: Store-write failure during update
- **GIVEN** version A is indexed
- **AND** writing version B fails before durability is verified
- **THEN** version A MUST remain searchable

#### Scenario: Successful replacement
- **GIVEN** version A is indexed
- **WHEN** version B is written and verified successfully
- **THEN** stale version A rows SHALL be removed
- **AND** public retrieval SHALL resolve the source to version B without persistent duplicates

### Requirement: Ingestion exposes stage timing without changing correctness

The pipeline SHALL expose enough internal timing/diagnostic data for experiments to distinguish parse/chunk, embedding, store write, lock wait and total time. Instrumentation SHALL NOT change ordering or error semantics.

#### Scenario: Performance experiment
- **WHEN** the bounded-ingestion experiment runs
- **THEN** it MUST be able to attribute wall time to parse/chunk, embedding and store-write stages rather than reporting only one undifferentiated total

### Requirement: Concurrency optimisation follows evidence

The correctness implementation SHALL not claim that `embed_concurrency` provides concurrent file-level embedding unless the measured implementation actually allows it. If a later optimisation moves embedding outside a narrow mutation lock, tests SHALL prove replacement safety, store mutation safety and generation correctness remain intact.

#### Scenario: Configured concurrency is not effective
- **GIVEN** the current lock structure serialises the full embed+write operation
- **WHEN** diagnostics describe effective ingestion concurrency
- **THEN** the system MUST NOT report multiple concurrent file-level embedding jobs merely because the configured integer is greater than one

