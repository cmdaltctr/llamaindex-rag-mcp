# ADR-014: Async Ingestion Path

**Status**: Accepted
**Date**: 2026-05-20
**Change**: `make-ingest-path-async`

## Context

The ingest path (`ingest_path` → `_read_and_chunk_file` →
`extract_metadata` → ChromaDB write) was synchronous end-to-end.
When triggered from the MCP server's event loop (via the watcher or
`ingest_documents` tool), the loop was occupied for the full duration,
making the server unresponsive to concurrent `search`, `list_collections`,
and `delete_documents` calls.

`_extract_llamaindex` surfaced this most visibly: `IngestionPipeline.run()`
is sync-over-async and refused to nest inside a running loop.  A
`ThreadPoolExecutor` workaround (ADR-013) unblocked correctness but still
blocked the loop on `.result()`.

## Decision

Make the ingest path `async def` end-to-end:

1. **`_extract_ollama_async`** uses `httpx.AsyncClient` (non-blocking HTTP)
   instead of `urllib.request.urlopen`.
2. **`_extract_llamaindex_async`** calls `IngestionPipeline.arun()` directly
   — no ThreadPoolExecutor, no nested-loop detection.
3. **`ingest_path_async`** is the canonical async entry point.  Sync
   `ingest_path`, `_read_and_chunk_file`, `extract_metadata`,
   `_extract_ollama`, and `_extract_llamaindex` were all removed.
4. **ChromaDB sync writes** are wrapped in `asyncio.to_thread()` to yield
   the loop (ChromaDB 0.5 has no async API).
5. **CLI** wraps async ingest in `asyncio.run()` at the entry point.
6. **Watcher** runs as a standalone CLI process (`rag-mcp watch`), not
   inside the MCP server loop.  All ingest is dispatched through
   `asyncio.run(ingest_path_async(...))` from the watcher thread.

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| `nest_asyncio.apply()` | Monkeypatches asyncio globally; `pipeline.run()` still blocks the loop during the LLM call. |
| Separate process for ingest | Adds IPC complexity; ChromaDB assumes single-process access to the SQLite store. |
| `asyncio.to_thread(urllib.request.urlopen, ...)` for Ollama | Works but `httpx` is cleaner — async + sync in one package, already in the LlamaIndex ecosystem. |

## Responsiveness Contract

The test `test_search_responsive_during_inflight_ingest` in
`tests/test_async_ingest_responsiveness.py` verifies the contract:
a concurrent `search` call must complete within 500 ms while an ingest
is in flight.  A regression test (`test_blocking_call_causes_responsiveness_failure`)
inserts `time.sleep(2)` into the async path and confirms the responsiveness
test catches it.

## Dependencies

- Added `httpx>=0.27.0` to `pyproject.toml` dependencies for async Ollama calls.
- No other new dependencies.

## References

- ADR-013: [Hybrid Category Taxonomy for Ollama Metadata](./013-hybrid-category-taxonomy-for-ollama-metadata.md) — the ThreadPoolExecutor workaround this replaces.
- OpenSpec change: `openspec/changes/make-ingest-path-async/`
- Spec: `openspec/changes/make-ingest-path-async/specs/async-ingestion/spec.md`
- Source:
  - `src/rag_mcp/ingestion.py` — `ingest_path_async`, `_read_and_chunk_file_async`
  - `src/rag_mcp/metadata_extractor.py` — `extract_metadata_async`, `_extract_*_async`
  - `src/rag_mcp/server.py` — `ingest_documents` tool handler
  - `src/rag_mcp/watcher.py` — `_dispatch_ingest`
  - `tests/test_async_ingest_responsiveness.py` — responsiveness regression tests
