## Why

When the MCP server is running and ingestion is triggered (via the watcher,
re-ingest, or upcoming MCP `ingest_path` tool), the ingest path is synchronous
end-to-end — it occupies the event loop for the full duration of the run.
For a folder with PDFs and `METADATA_EXTRACTION_MODE=llamaindex`, that means
the server is unresponsive to `search`, `list_collections`, `delete_documents`,
and every other MCP request until the last file finishes processing (often
several minutes).

`_extract_llamaindex` recently surfaced this most visibly: `IngestionPipeline.run()`
is sync-over-async and refuses to nest inside a running loop. We worked around
the *correctness* problem in `metadata_extractor.py` by offloading
`pipeline.run()` to a worker thread (see ADR-013, "Implementation Notes"), but
that workaround still blocks the calling thread on `.result()`, which is the
MCP server's event loop. The right fix is to make the ingest path
`async def` end-to-end so the loop can interleave other requests while LLM
calls and file I/O are in flight.

## What Changes

- Convert `ingest_path` and `_read_and_chunk_file` in `ingestion.py` to
  `async def` and use `await` on all I/O- or LLM-bound operations.
- Add an async variant of `_extract_llamaindex` (e.g. `_extract_llamaindex_async`)
  that calls `IngestionPipeline.arun()` directly instead of using the
  thread-offload workaround. Drop the `ThreadPoolExecutor` branch once
  the async path is in place.
- Add an async variant of `_extract_ollama` that uses `aiohttp` (or `httpx`)
  instead of `urllib.request.urlopen`. **Note**: this introduces a new
  dependency — flag for confirmation per AGENTS.md "ask before adding new
  core dependencies".
- Update the MCP `ingest_path` tool handler in `server.py` to `await` the
  async ingest function instead of calling it synchronously.
- Update the watcher in `watcher.py` to schedule async ingest on the running
  loop via `asyncio.run_coroutine_threadsafe(...)` instead of calling sync
  ingest from the watcher thread.
- Keep the CLI path (`cli.py`) working by wrapping the async ingest in
  `asyncio.run(...)` at the entry point — the CLI has no enclosing loop.
- Remove the nested-loop detection and `ThreadPoolExecutor` branch in
  `_extract_llamaindex` once the async path is the default; preserve the
  sync `pipeline.run()` call only as a fallback for the CLI.

## Capabilities

### New Capabilities
- `async-ingestion`: Specifies that ingestion runs as `async def` so the MCP
  server event loop remains responsive to other tool calls during long
  ingest operations. Covers the contract between watcher/server callers and
  the ingestion module, error propagation through `await`, and cancellation
  semantics.

### Modified Capabilities
<!-- None. CLI flags, watcher debounce/idempotency, and return-dict shapes
     are all preserved. The async refactor is internal plumbing. -->

## Impact

**Code:**
- `src/rag_mcp/ingestion.py` — convert `ingest_path` and helpers to async
- `src/rag_mcp/metadata_extractor.py` — add `_extract_*_async` variants;
  retire the thread-offload workaround in `_extract_llamaindex`
- `src/rag_mcp/server.py` — `await` async ingest from the MCP tool handler
- `src/rag_mcp/watcher.py` — schedule via `run_coroutine_threadsafe`
- `src/rag_mcp/cli.py` — `asyncio.run(...)` at entry point

**Dependencies (asks user confirmation):**
- Add `httpx` (or `aiohttp`) for async HTTP to Ollama. `httpx` is preferred —
  smaller surface, sync+async in one package, already common in the LlamaIndex
  ecosystem.

**Tests:**
- All ingestion tests need `@pytest.mark.asyncio` and `async def` versions.
- `conftest.py` autouse fixtures stay; they don't need async-ifying.
- Add tests verifying MCP `search` completes promptly while a long ingest
  is in flight (responsiveness contract).

**ADRs:**
- Update ADR-013 "Implementation Notes" once the workaround is retired,
  pointing the reader to the new async path.
- Possibly new ADR documenting the async-end-to-end decision.

**Backward compatibility:**
- CLI flags, MCP tool names/parameters, `.env` variables — all unchanged.
- Watcher behaviour observable to users — unchanged (same debounce,
  same idempotency).
- Existing ChromaDB data — unchanged.

**Risk:**
- Async refactors are easy to get half-right (a single sync call in the
  middle of an async chain blocks the loop). Verification needs an
  end-to-end test that asserts loop responsiveness, not just functional
  correctness.
- LlamaIndex's `arun()` may have its own bugs or behaviour drift vs `run()`.
  Worth a smoke test with a real Ollama before committing to the cutover.
