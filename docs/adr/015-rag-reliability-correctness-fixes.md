# ADR-015: RAG Reliability and Correctness Fixes

**Status**: Proposed
**Date**: <TODO: YYYY-MM-DD on archive>
**Change**: `rag-reliability-correctness-fixes`
**Deciders**: Dr Muhammad Aizat Bin Md Hawari
**Git Commits**: <TODO: list relevant SHAs once landed>

## Context

ADR-014 made the ingest path async end-to-end, but four reliability gaps
remained in the surrounding pipeline. Chunk splitting (`SentenceSplitter`)
still ran synchronously inside the otherwise-async ingest path and could
block the event loop on large documents. The MCP `search_documents` tool
did not expose `metadata_filter` even though `retrieval.search()` already
accepted one internally. Filtered and unfiltered retrieval paths used
different score conversions (filtered: `1.0 / (1.0 + L2_distance)`;
unfiltered: whatever LlamaIndex returned), so the same
`similarity_threshold` filtered different chunks on each path. Ollama
metadata extraction failed closed after a single HTTP or JSON-parsing
error, even though qwen3 frequently wraps its JSON in ```` ```json ```` fences.

These four issues are independent of larger algorithmic choices (hybrid
retrieval, semantic chunking) and should ship before them so subsequent
changes inherit a correct baseline.

## Decision

Adopt five sub-decisions, each independent in code but bundled in this
change for shared test infrastructure and documentation:

1. **Offload chunk splitting via `asyncio.to_thread`.** Wrap
   `SentenceSplitter.get_nodes_from_documents(...)` in
   `asyncio.to_thread(...)` inside `_read_and_chunk_file_async` so the
   event loop stays responsive during ingestion of large files. Extends
   ADR-014's pattern (file reads, ChromaDB writes already offload this way).

2. **Expose optional `metadata_filter` on the MCP `search_documents` tool.**
   `retrieval.search()` already accepts a ChromaDB-compatible `where`
   clause; the MCP tool gains an optional `metadata_filter: dict | None
   = None` parameter and passes it through unchanged. Default
   behaviour is preserved.

3. **Both retrieval paths convert ChromaDB L2 distance via
   `score = 1.0 / (1.0 + distance)`.** The unfiltered path is reworked to
   surface this conversion either by querying ChromaDB directly or by
   post-processing LlamaIndex retriever output. A regression test asserts
   pre-threshold scores agree within `1e-6` for the same chunk traversed
   on both paths. Reranker scores remain on the sigmoid-normalised
   cross-encoder scale; ADR-005's calibrated ÷30 threshold scaling is
   explicitly preserved.

4. **Ollama metadata extraction gains bounded retry, exponential backoff,
   and markdown fence stripping.** `_extract_ollama_async` is wrapped in
   a manual async retry loop with `OLLAMA_CLASSIFY_MAX_ATTEMPTS` and
   `OLLAMA_CLASSIFY_TIMEOUT` env vars; successive attempts use
   `await asyncio.sleep(2 ** attempt)` so retries cannot pile up against
   a slow Ollama. `_parse_ollama_json_response` strips ```` ```json ```` and
   ```` ``` ```` fences before `json.loads(...)`. JSON mode (`format: "json"`)
   is intentionally left off in this change because fence-stripping
   handles the common failure mode without depending on a specific
   Ollama version.

5. **MCP `search_documents` returns errors as a single-element list.**
   The handler keeps its declared `list[dict]` return type on every path.
   On caught exception, returns
   `[{"status": "error", "error_type": "<category>", "message": "<text>"}]`
   where `error_type` is one of `validation` (invalid `metadata_filter`),
   `retrieval` (ChromaDB query failure), or `internal`. Successful
   responses keep their existing field set with no `status` key. This
   preserves the MCP tool contract while satisfying the AGENTS.md rule
   that handlers never raise.

## Consequences

### Positive

- Filtered and unfiltered searches now apply `similarity_threshold`
  against the same score scale; the long-standing comparability bug is
  closed.
- Event loop no longer blocks on chunk splitting for large files;
  responsiveness contract from ADR-014 now holds for the full ingest path.
- `search_documents` errors are deterministic and machine-readable
  rather than raised exceptions; MCP clients can branch on
  `result[0].get("status") == "error"`.
- qwen3-style ```` ```json ```` fence-wrapped JSON now parses correctly
  through `_parse_ollama_json_response`.
- Bounded retry with exponential backoff makes transient Ollama failures
  recoverable without piling up requests.

### Negative

- Adds modest latency to metadata extraction when Ollama is degraded
  (bounded by `OLLAMA_CLASSIFY_MAX_ATTEMPTS × OLLAMA_CLASSIFY_TIMEOUT`).
- The score-normalisation rework on the unfiltered path replaces the
  LlamaIndex retriever-chain with a direct `collection.query(...)` call;
  callers depending on LlamaIndex-specific behaviour on the unfiltered
  path see a narrower API surface.

### Neutral

- New env vars (`OLLAMA_CLASSIFY_MAX_ATTEMPTS`, `OLLAMA_CLASSIFY_TIMEOUT`)
  added with backwards-compatible defaults.
- Error-envelope shape adds a `status` key only on failure responses;
  existing clients that iterate the list and check field presence are
  unaffected.

## Alternatives Considered

| Option | Rejected because |
|--------|------------------|
| Recreate ChromaDB collections with `hnsw:space = cosine` for unified scoring | Forces a migration, breaks existing persisted collections |
| Switch the MCP error response to a top-level dict (`dict \| list[dict]`) | Changes the declared MCP tool schema and breaks clients that iterate the list |
| Use `tenacity` for retry | New dependency; a small manual loop avoids it |
| Enable Ollama JSON mode (`format: "json"`) immediately | Introduces a version-specific dependency on minimum Ollama; fence-stripping addresses the common failure mode without it |
| Leave both retrieval paths with divergent score formulas and document the divergence | Status quo — produces the bug this ADR exists to fix |

## References

- ADR-005: [Cross-Encoder Reranker with ONNX Runtime](./005-cross-encoder-reranker-with-onnx-runtime.md) — the ÷30 threshold calibration this ADR explicitly preserves
- ADR-014: [Async Ingestion Path](./014-async-ingestion-path.md) — the foundation this ADR extends to the chunking step
- OpenSpec change: `openspec/changes/rag-reliability-correctness-fixes/`
- Specs:
  - `openspec/changes/rag-reliability-correctness-fixes/specs/async-ingestion/spec.md`
  - `openspec/changes/rag-reliability-correctness-fixes/specs/mcp-search-filtering/spec.md`
  - `openspec/changes/rag-reliability-correctness-fixes/specs/score-normalisation/spec.md`
  - `openspec/changes/rag-reliability-correctness-fixes/specs/metadata-extraction/spec.md`
- Source:
  - `src/rag_mcp/ingestion.py` — `_read_and_chunk_file_async` with `to_thread` chunking
  - `src/rag_mcp/retrieval.py` — unified `score = 1.0 / (1.0 + distance)` on both paths
  - `src/rag_mcp/server.py` — `search_documents` error envelope and `metadata_filter` parameter
  - `src/rag_mcp/metadata_extractor.py` — retry loop, exponential backoff, fence stripping
- Tests: <TODO: list the regression tests added>
