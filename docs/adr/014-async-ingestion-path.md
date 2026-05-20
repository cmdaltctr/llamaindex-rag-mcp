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
- `llama-index-llms-ollama>=0.4.0` moved from optional extras (`[metadata]`) to
  core `[project.dependencies]` on 2026-05-20.  The `llamaindex` metadata
  extraction mode requires this package; having it as an optional extra meant
  `uv sync` never installed it and the mode silently fell back to keyword
  extraction.  Making it a core dependency ensures `uv sync` always provisions
  it and `llamaindex` mode works out of the box.

## Degradation Ladder

The async metadata extraction follows a three-tier degradation ladder
(`llamaindex → ollama → keyword`):

1. **`_extract_llamaindex_async`** — the richest path.  Calls
   `IngestionPipeline.arun()` with `TitleExtractor`, `KeywordExtractor`, and
   `SummaryExtractor` per chunk.  Produces `category`, `document_title`,
   `keywords`, and `summary`.

   **Fallback**: if `llama-index-llms-ollama` is not importable (unlikely now
   that it is a core dependency, but possible in constrained environments),
   the function falls back to `_extract_ollama_async`.  If the pipeline itself
   raises (Ollama timeout, bad model response), the same fallback applies.

2. **`_extract_ollama_async`** — the middle tier.  Issues a single
   classification prompt to Ollama's `/api/generate` endpoint via
   `httpx.AsyncClient`.  Produces `category`, `keywords`, and `summary`.
   Uses the hybrid category taxonomy from ADR-013.

   **Fallback**: if Ollama is unreachable, returns `{"category": "uncategorised",
   "keywords": [], "summary": ""}`.

3. **`_extract_keyword_async`** — regex-only, no network.  Last resort.

This ladder replaced the previous incorrect behaviour (2026-05-20) where
`_extract_llamaindex_async` fell back directly to keyword mode on
`ImportError`, skipping the richer ollama path entirely.

## LLM Output Noise Handling

`_strip_llm_prefix` was extended (2026-05-20) to handle three additional LLM
output artefacts commonly seen in `document_title` and `summary` fields:

- **Surrounding markdown bold markers** (`** "value" **`) — stripped via greedy
  `(?:\*{1,2}\s*)+` regex.
- **Trailing explanation paragraphs** — truncated at the first `\n\n`.
- **Surrounding quotes** — stripped after bold markers are removed.

Before this fix, `document_title` would store values like
`** "Hallucinations in Language Models: Training, Evaluation..." **\n\nThis title encapsulates...`
instead of the clean title string.

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
