# ADR-015: RAG Reliability and Correctness Fixes

**Status**: Proposed
**Date**: 2026-05-27
**Change**: `rag-reliability-correctness-fixes`

## Context

After ADR-014 made the ingestion path async end-to-end, an audit found a
small set of correctness and reliability gaps that were independent of
larger algorithmic upgrades:

- `_read_and_chunk_file_async` still ran `SentenceSplitter.get_nodes_from_documents(...)`
  synchronously on the event-loop thread. On large documents the splitter
  blocks the loop for several seconds, so concurrent MCP `search`,
  `list_collections`, and `delete_documents` calls stall behind ingest.
- `retrieval.search()` already supports `metadata_filter`, but the MCP
  `search_documents` tool does not expose it — clients cannot use the
  feature.
- The two retrieval branches (filtered direct-ChromaDB, unfiltered
  LlamaIndex retriever) produced scores on different scales:
  the filtered branch used `1 / (1 + distance)`, the unfiltered branch
  surfaced whatever LlamaIndex returned. The same chunk could appear with
  visibly different `score` values depending on whether a filter was
  attached, which made `similarity_threshold` semantics inconsistent
  across paths.
- `_extract_ollama_async` failed closed on the first transient HTTP error
  and could not parse JSON wrapped in markdown code fences — qwen3:0.6b's
  default output shape.
- The MCP search handler had no explicit error envelope, so a ChromaDB
  validation failure (invalid `where` clause) propagated as a raw
  exception, contradicting the AGENTS.md rule "Never raise from MCP tool
  handlers".

These fixes do not touch the embedding model, ChromaDB collection
dimensionality, the calibrated ÷30 reranker threshold, or the retrieval
algorithm. They tighten correctness at module boundaries before larger
retrieval-quality work begins.

## Decision

This ADR captures five sub-decisions implemented as one OpenSpec change:

1. **Offload chunk splitting via `asyncio.to_thread`.** `_read_and_chunk_file_async`
   now wraps the `SentenceSplitter.get_nodes_from_documents(...)` call in
   `asyncio.to_thread(...)`, matching the pattern ADR-014 already
   established for file reading and ChromaDB writes. This is the last
   remaining synchronous step in the async ingest path.

2. **Expose optional `metadata_filter` on the MCP `search_documents` tool.**
   The tool now takes an optional `metadata_filter: dict | None = None`
   parameter and passes it through to `retrieval.search()` unchanged.
   Existing clients that omit the parameter see no behavioural change.

3. **Both retrieval paths use the same score formula `score = 1.0 / (1.0 + distance)`.**
   `retrieval.search()` was reworked so the metadata-filtered and
   metadata-free branches both issue a direct ChromaDB `query()` call
   and apply the same `_distance_to_score` conversion. The branches
   differ only in whether `where` is attached. The pre-threshold score
   is therefore byte-identical across paths for the same `(query, chunk)`
   pair (the OpenSpec contract is `≤ 1e-6`, and the implementation hits
   exact equality by construction). The reranker's sigmoid scale and the
   calibrated ÷30 threshold scaling are untouched.

4. **Ollama metadata extraction gains bounded retry, exponential backoff,
   and markdown fence stripping.** `_extract_ollama_async` now runs up to
   `OLLAMA_CLASSIFY_MAX_ATTEMPTS` attempts (default 3) with
   `await _retry_sleep(2 ** attempt)` between failures and a per-attempt
   `OLLAMA_CLASSIFY_TIMEOUT` (default 30 s). `_parse_ollama_json_response`
   strips a single surrounding markdown code fence (` ```json ... ``` `
   or bare ` ``` ... ``` `) before `json.loads`. Ollama JSON mode
   (`format: "json"`) is left off in this change — the open question is
   resolved in `design.md` open-questions.

5. **MCP `search_documents` returns errors as a single-element list.**
   The handler keeps its declared `list[dict]` return type on every path,
   including failures. On a caught exception it returns
   `[{"status": "error", "error_type": <category>, "message": <text>}]`,
   where `error_type` is one of:
   - `"validation"` — `ValueError` from ChromaDB, typically a malformed
     `where` clause;
   - `"retrieval"` — any other exception originating in the chromadb
     namespace, or any exception thrown while a `metadata_filter` was
     attached;
   - `"internal"` — anything else.

   Successful responses keep their existing list-of-result-dicts shape
   (`score`, `source`, `page_label`, `text`, `reranked`) and contain no
   `status` key.

## Consequences

**Positive**

- The MCP event loop stays responsive during ingest of large files.
  Concurrent `search` calls return well under the 500 ms responsiveness
  contract from ADR-014, even when the splitter is mid-flight.
- `similarity_threshold` now means the same thing on every non-reranked
  retrieval path. The unfiltered and filtered branches use the same
  formula and the same ChromaDB call, so threshold semantics, ranking,
  and scoring are uniform.
- Errors from the search tool have a deterministic, machine-readable
  shape. Clients can detect failures by checking `result[0]["status"]`
  on the first element.
- qwen3:0.6b responses wrapped in fenced JSON now parse correctly. A
  transient Ollama timeout no longer drops the document straight to
  `uncategorised`.

**Negative**

- When Ollama is genuinely unreachable, retry latency now compounds
  (1 s + 2 s for default 3 attempts ≈ 3 s of backoff) before the
  `uncategorised` fallback. Bounded by `OLLAMA_CLASSIFY_MAX_ATTEMPTS`
  and capped by `OLLAMA_CLASSIFY_TIMEOUT` per attempt.

**Neutral**

- The unfiltered retrieval path no longer goes through
  `VectorStoreIndex.as_retriever()` — it issues a direct ChromaDB query
  exactly like the filtered path did before. This collapses two code
  paths into one and simplifies retrieval, but it does mean we no
  longer rely on LlamaIndex for retriever scoring on the default path.
  Existing on-disk ChromaDB collections continue to work with no
  migration.

## Alternatives Considered

| Decision | Alternative | Rejected because |
|----------|-------------|-----------------|
| 3 — score formula | Recreate ChromaDB collections with `hnsw:space = cosine` so distances are already in `[0, 1]`. | Requires a destructive migration of every persisted collection, and breaks ADR-014's "no rebuild" promise. |
| 3 — score formula | Leave both paths as-is and document the divergence. | "Documented divergence" is the status quo and is precisely the bug this ADR fixes. |
| 5 — error envelope | Change `search_documents` to return `dict | list[dict]`. | Changes the declared MCP tool schema and breaks clients that iterate the list. |
| 5 — error envelope | Raise from the handler and let FastMCP wrap as `TextContent` with `isError`. | Forbidden by AGENTS.md rule 1 ("Never raise from MCP tool handlers"). |
| 4 — retry library | Adopt `tenacity`. | A small manual loop is enough; adding a runtime dependency for a few lines of retry logic is not worth it. |

## References

- ADR-014: [Async Ingestion Path](./014-async-ingestion-path.md) — this
  ADR extends the responsiveness contract to the splitter.
- ADR-013: [Hybrid Category Taxonomy for Ollama Metadata](./013-hybrid-category-taxonomy-for-ollama-metadata.md)
  — the taxonomy logic that the retry loop now wraps.
- OpenSpec change: `openspec/changes/1-rag-reliability-correctness-fixes/`
- Specs:
  - `specs/async-ingestion/spec.md` — splitter offload scenario
  - `specs/mcp-search-filtering/spec.md` — metadata_filter parameter and
    error envelope
  - `specs/score-normalisation/spec.md` — `1 / (1 + d)` parity contract
  - `specs/metadata-extraction/spec.md` — Ollama retry and fence handling
- Source:
  - `src/rag_mcp/ingestion.py` — `_read_and_chunk_file_async`
  - `src/rag_mcp/retrieval.py` — `search`, `_distance_to_score`
  - `src/rag_mcp/server.py` — `search_documents`
  - `src/rag_mcp/metadata_extractor.py` — `_extract_ollama_async`,
    `_parse_ollama_json_response`, `_strip_markdown_fence`
  - `src/rag_mcp/config.py` — `OLLAMA_CLASSIFY_MAX_ATTEMPTS`,
    `OLLAMA_CLASSIFY_TIMEOUT`
- Experiment: `experiments/4-async-chunking-responsiveness-2026-05-27/`
  — under-load vs idle-baseline P95 latency comparison
