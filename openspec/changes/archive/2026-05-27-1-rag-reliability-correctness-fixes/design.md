## Context

The current architecture is a local-only RAG MCP server using LlamaIndex, ChromaDB, Ollama embeddings, optional ONNX reranking, and metadata extraction. The audit found that several reliability issues are independent of larger algorithmic choices: chunking is synchronous inside the async ingestion path, metadata filtering exists internally but is not exposed through MCP search, filtered and unfiltered search paths can produce differently scaled scores, and Ollama metadata extraction fails closed after a single HTTP/JSON failure.

This design keeps the existing architecture intact. It improves correctness at module boundaries before introducing larger retrieval changes such as hybrid BM25 or changed chunking algorithms.

## Goals / Non-Goals

**Goals:**

- Keep the MCP event loop responsive during ingestion, including the chunk-splitting phase.
- Make metadata-filtered search available to MCP clients through an optional parameter.
- Preserve comparable score-threshold behaviour across filtered, unfiltered, and reranked search paths.
- Ensure MCP search handlers return explicit error envelopes rather than leaking raw exceptions.
- Make Ollama metadata extraction resilient to transient failures and common malformed JSON wrappers.

**Non-Goals:**

- No reranker model change.
- No embedding model change.
- No ChromaDB collection rebuild or vector-dimension migration.
- No semantic chunking, hierarchical chunking, late chunking, or proposition chunking in this change.
- No BM25/hybrid retrieval implementation in this change.

## Decisions

### Decision 1: Offload chunk splitting with `asyncio.to_thread`

The current async ingestion path already offloads file reading and ChromaDB writes. Chunk splitting should follow the same pattern because `SentenceSplitter.get_nodes_from_documents(...)` is synchronous and can become CPU-bound for large files.

Alternative considered: replace the splitter now. Rejected for this change because splitter algorithm choice belongs in a separate retrieval-quality proposal.

### Decision 2: Expose `metadata_filter` as an optional MCP parameter

`retrieval.search()` already accepts `metadata_filter`; the MCP tool simply does not expose it. The change should add `metadata_filter: dict | None = None` to `search_documents` and pass it through unchanged.

Alternative considered: add a new specialised search tool. Rejected because it would duplicate the existing search API for no benefit.

### Decision 3: Both paths convert ChromaDB L2 distance via `1 / (1 + distance)`

Non-reranked similarity scores SHALL be computed identically on both retrieval paths using

```
score = 1.0 / (1.0 + distance)
```

against the raw L2 distance returned by ChromaDB. The filtered path already uses this formula via direct ChromaDB queries (see `retrieval.search()` in the metadata-filtered branch) and is the canonical reference. The unfiltered path SHALL be reworked to surface the same conversion — either by issuing the ChromaDB query directly (skipping `VectorStoreIndex.as_retriever()`) or by post-processing the LlamaIndex retriever output to reapply `1.0 / (1.0 + distance)` before threshold filtering. Reranker scores remain on the sigmoid-normalised cross-encoder scale, untouched, with the calibrated ÷30 threshold scaling preserved.

Tests SHALL include at least one query that traverses both paths against the same chunk and asserts the pre-threshold scores match within `1e-6`.

Alternative considered: recreate collections with `hnsw:space = cosine`. Rejected for this change because it would require migration and could break existing persisted ChromaDB collections.

Alternative considered: leave both paths as-is and document the divergence. Rejected because "documented divergence" is the status quo and produces the bug this decision exists to fix.

### Decision 4: Retry Ollama metadata extraction without adding a dependency

Ollama classification should use a bounded manual async retry loop with configurable attempts and timeout. The parser should strip common markdown code fences before JSON parsing. Prefer using the existing `/api/generate` endpoint unless JSON-mode support is straightforward and tests prove compatibility.

Alternative considered: add `tenacity`. Rejected unless manual retry becomes too complex; a small local loop avoids a new dependency.

### Decision 5: Error envelope is a single-element list, not a dict

`search_documents` SHALL keep its declared return type `list[dict]` on all paths, including failures. On a caught retrieval exception, the handler SHALL return a one-element list containing an error dict shaped as

```python
[{"status": "error", "error_type": "<category>", "message": "<human-readable>"}]
```

where `error_type` is one of `"validation"` (e.g. invalid `metadata_filter`), `"retrieval"` (ChromaDB query failure), or `"internal"` (anything else). Successful responses keep their existing list-of-result-dicts shape and field set unchanged. Clients distinguish error responses by checking `"status" in result and result["status"] == "error"` on the first element.

This shape was chosen because it preserves the existing MCP tool's declared `list[dict]` contract (no schema change for clients), aligns with the AGENTS.md rule "Always return `{"status": "error", "message": "..."}` from MCP tool handlers" by carrying that envelope as the single list element, and keeps the success path byte-identical.

Alternative considered: switch the return type to `dict | list[dict]`. Rejected because it changes the declared MCP tool schema and breaks existing clients that iterate the list without type-checking.

Alternative considered: raise from the handler and let FastMCP wrap. Rejected by AGENTS.md rule 1 ("Never raise from MCP tool handlers").

## Risks / Trade-offs

- **Risk: MCP clients break if the success result shape changes.** → Mitigated by Decision 5: errors are returned as a one-element list whose sole entry carries `status: "error"`. Successful responses keep their existing shape; iterating clients only need to check the first element for `"status"` to detect errors.
- **Risk: changing the unfiltered path's score formula shifts user-visible thresholds.** → Mitigated by Decision 3 fixing both paths to `1.0 / (1.0 + distance)` and by targeted regression tests; the calibrated ÷30 reranker scaling is explicitly preserved.
- **Risk: retries increase metadata ingestion latency when Ollama is down.** → Mitigated with low default retry count, exponential backoff, and configurable per-attempt timeout.
- **Risk: `metadata_filter` accepts invalid ChromaDB where clauses.** → Mitigated by catching ChromaDB validation errors and returning the Decision 5 error envelope with `error_type: "validation"`.

## Migration Plan

No data migration is required. Existing collections, embeddings, and metadata remain readable. Rollback is a code rollback only.

## Open Questions

- Should Ollama structured JSON mode (`format: "json"`) be enabled immediately or only after compatibility is confirmed against the minimum supported Ollama version? Default decision: leave it off in this change; markdown-fence stripping in the JSON parser handles the common failure mode without depending on a specific Ollama version.

## Resolved Questions

- **Error envelope shape** — resolved in Decision 5: single-element list `[{"status": "error", "error_type": ..., "message": ...}]`.
- **Score normalisation conversion** — resolved in Decision 3: both paths use `score = 1.0 / (1.0 + distance)` against ChromaDB L2 distance.
