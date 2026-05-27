## Purpose

Define the asynchronous ingestion contract so document ingestion can run without blocking MCP tool handling while preserving existing ingestion result shapes and metadata extraction behaviour.

## Requirements

### Requirement: Async ingestion entry point

The system SHALL expose `ingest_path_async(path, ...)` in `rag_mcp.ingestion`
as the primary ingestion function. The function SHALL be declared `async def`
and SHALL return the same result dictionary shape as the existing
`ingest_path()` (`files_indexed`, `chunks_created`, `file_details`, plus the
optional `error_type` / `message` fields).

#### Scenario: Async ingest produces same result shape as sync ingest

- **WHEN** `await ingest_path_async("/path/to/folder")` completes successfully
- **THEN** the returned dict SHALL contain `files_indexed`, `chunks_created`,
  and `file_details` with the same keys and types as `ingest_path()`'s return
  dict
- **THEN** the `file_details` entries SHALL contain `file`, `status`, `chunks`
  fields, and `error` only when `status == "failed"`

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

- **WHEN** `METADATA_EXTRACTION_MODE=ollama` and `await
  extract_metadata_async(text, "doc.pdf")` is called
- **THEN** the function SHALL issue an HTTP request to Ollama using a
  non-blocking HTTP client
- **THEN** the function SHALL return a dict with `category`, `keywords`,
  `summary` (same shape as sync `extract_metadata()`)

#### Scenario: Async metadata extraction in llamaindex mode

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex` and
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
