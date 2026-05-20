# ADR-011: Multi-Collection and Metadata Extraction

**Status**: Accepted
**Date**: 2026-05-19
**Change**: `add-multi-collection-metadata`

## Context

The RAG MCP server originally used a single ChromaDB collection (`documents`) for all
ingested content. Every document — whether a research paper, a code snippet, a
philosophy note, or a marketing brief — landed in the same vector space. While
semantic search works regardless of content type, users could not scope searches to
a specific domain or isolate content types from each other.

Adding a separate collection per domain (e.g., `research`, `code`, `marketing`) was
a natural solution, but it raised integration questions: where should the collection
name be configured, how should it be threaded through the existing ingestion and
retrieval pipeline, and how should it interact with the MCP protocol and CLI?

A secondary need emerged: automatically categorising documents during ingestion so
that users could filter search results by content type even within a single
collection. This required a metadata extraction system that was configurable, had
zero additional dependencies in its default mode, and could optionally leverage a
local LLM for smarter categorisation.

Constraints:
1. **No breaking changes** — existing `rag-mcp ingest ./docs` must keep working unchanged
2. **No new Python dependencies** — keyword mode uses `re` (stdlib), Ollama mode uses
   `urllib` (stdlib)
3. **No PyTorch** — ONNX Runtime only, per project boundaries
4. **All new MCP tool parameters must be optional with sensible defaults**
5. **British English** — all docs, comments, log messages

## Decision

**Implement multi-collection support by threading an optional `collection_name`
parameter through every function in the ingestion/retrieval/watcher pipeline,
defaulting to `"documents"`. Add a configurable metadata extraction system with
four modes — `disabled`, `keyword`, `ollama`, `llamaindex` — toggled by a single
`METADATA_EXTRACTION_MODE` environment variable.**

### Key design choices

| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|
| **Collection routing** | Parameter threading (`collection_name: str = "documents"`) through 8 functions across 4 modules | Each call can target a different collection independently — safest concurrency guarantee for an MCP server that handles concurrent client requests. | `Settings.collection_name` global (state conflicts with concurrent MCP clients); env var per command (worse UX than a `--collection` flag). |
| **ChromaDB collection lookup** | Dynamic `get_or_create_collection(collection_name)` — no global state mutation | ChromaDB's `get_or_create_collection` is idempotent — first call creates, subsequent calls return existing. No migration needed. All collections share the same embedding model from `config.py`, ensuring consistent vector dimensions. | Pre-creating collections at startup (unnecessary — ChromaDB handles it); separate ChromaDB directories per collection (wasteful, complicates persistence). |
| **Metadata extraction mode** | Single `METADATA_EXTRACTION_MODE` env var with four values (`disabled`, `keyword`, `ollama`, `llamaindex`) | One clear toggle; `keyword` is the sensible default (zero deps, instant); `ollama` upgrades accuracy for users with a chat model; `llamaindex` stubbed for future. | Always Ollama (adds 2s per file for users without a chat model); separate toggles per mode (over-engineered). |
| **Keyword rules** | Default hardcoded rules covering 5 domains (AI, Philosophy, Biology, Marketing, Programming); user-overridable via `METADATA_KEYWORD_RULES` JSON in `.env` | Zero deps, instant; regex scoring picks the category with the most keyword hits; falls back to `"uncategorised"` when nothing matches. Invalid JSON falls back to defaults with a WARNING log. | YAML config file (env var is simpler, matches existing `.env`-only pattern); CLI flag (keyword rules are set once, not per-invocation). |
| **Metadata attachment point** | `_read_and_chunk_file()` — one `extract_metadata()` call per file, result attached to every node's `.metadata` | One extraction per file (not per chunk) minimises overhead. The same category applies to all chunks of a single document. ChromaDB stores `.metadata` alongside each vector automatically. | Per-chunk extraction (wasteful — same text, repeated calls); post-ingestion metadata update (complex, requires ChromaDB upsert on metadata). |
| **Search filtering** | `metadata_filter: dict | None` parameter passed to ChromaDB's native `where` clause via `collection.query(where=...)`, bypassing the LlamaIndex retriever when active | Server-side filtering — only matching chunks leave ChromaDB. When no filter is active, the existing LlamaIndex retriever path is used unchanged. | Client-side post-retrieval filtering (wastes vector-store fetch on chunks that will be discarded; `top_k` may return fewer results than requested). |
| **Ollama classification** | Single POST to `OLLAMA_BASE_URL/api/generate` with `OLLAMA_CLASSIFY_MODEL` (default `qwen3:0.6b`). Only the first 2000 characters of the document are sent for efficiency. | Simple REST call; uses `urllib.request` (stdlib) — no new dependencies. Falls back to `"uncategorised"` on any error with a WARNING log. | Streaming response (unnecessary for single-word output); `requests` library (available transitively via httpx, but adds dependency weight); sending full document (slow for long papers). |
| **LlamaIndex stub** | `_extract_llamaindex()` logs INFO "not yet implemented" and falls back to keyword mode | Keeps the API surface consistent; zero implementation cost for v1; no `Settings.llm` configuration needed yet. | Full LlamaIndex MetadataExtractor integration (requires configuring `Settings.llm`, which is a larger change out of scope for v1). |

### Architecture

```
config.py (METADATA_EXTRACTION_MODE, METADATA_KEYWORD_RULES, OLLAMA_CLASSIFY_MODEL)
    │
    ├── metadata_extractor.py
    │       ├── extract_metadata(file_text, file_name) → {"category": "AI"}
    │       ├── _extract_keyword(text)      ← default mode
    │       ├── _extract_ollama(text)        ← local chat model
    │       ├── _extract_llamaindex(...)     ← stubbed for future
    │       └── _extract_disabled()          ← returns {}
    │
    ├── ingestion.py
    │       ├── _read_and_chunk_file()  → calls extract_metadata, attaches to nodes
    │       ├── _get_chroma_collection(collection_name)  ← dynamic lookup
    │       ├── ingest_path(collection_name="documents")  ← CLI + MCP entry
    │       └── list_documents(collection_name="documents")
    │
    ├── retrieval.py
    │       ├── search(collection_name, metadata_filter)
    │       │       └── if filter: collection.query(where=filter)  ← server-side
    │       │           else:    LlamaIndex retriever path           ← no filter
    │       └── list_collections() → name + counts
    │
    └── watcher.py
            └── DocumentIngestHandler(collection_name) → ingest_path(collection_name)
```

## Consequences

### Positive

- **Content isolation**: Research papers, code documentation, and marketing materials
  live in separate ChromaDB collections — searches are scoped and precise.
- **Zero breaking changes**: All existing commands (`rag-mcp ingest ./docs`), MCP
  tools (all three without `collection`), and ChromaDB data continue to work unchanged.
- **Zero new Python dependencies**: Keyword mode uses `re` (stdlib); Ollama mode uses
  `urllib` (stdlib); `json` for rule parsing. No `pip install` needed.
- **Auto-categorisation**: Keyword mode categorises documents instantly at ingest time.
  Metadata is stored as ChromaDB metadata on every chunk, enabling filtered searches.
- **Extensible**: Users can override keyword rules via JSON env var for their own
  domains. Ollama mode provides smarter, LLM-driven classification when a chat model
  is available. The llamaindex mode is reserved for future integration.
- **Backward-compatible search**: `metadata_filter` defaults to `None` — all searches
  without a filter return results from all categories (unchanged behaviour).
- **CLI parity with MCP**: Every CLI command has an equivalent MCP tool parameter;
  every new feature works identically from the terminal and from MCP clients.
- **Performance-conscious**: `list_documents()` and `list_collections()` cap metadata
  fetches at 10,000 chunks to avoid memory pressure on large collections. The
  `document_count` field is documented as "approximate".

### Neutral

- **Collection dimension lock**: All collections share the same embedding model from
  `config.py`, guaranteeing consistent vector dimensions. However, changing
  `EMBED_MODEL` between ingest and search still requires rebuilding collections.
- **Single-category metadata**: v1 assigns one `category` tag per document. Future
  versions could support multi-label classification, confidence scores, or
  user-defined metadata schemas beyond `category`.
- **No cross-collection search**: Searching two collections at once requires two
  separate `search_documents` calls. A `RouterQueryEngine` or LLM-based query routing
  could be added in v2.

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Ollama classification slow for large batches** | Medium | Medium | `keyword` mode is the default (instant). Users opt into `ollama` mode explicitly. |
| **Ollama chat model not pulled** | Medium | Low | If `ollama` mode is selected but no chat model exists, the Ollama call fails gracefully → returns `{"category": "uncategorised"}` and logs a WARNING. |
| **Keyword rules too narrow for niche domains** | Medium | Low | Users can override rules via `METADATA_KEYWORD_RULES` JSON env var. The default set covers 5 common domains. |
| **ChromaDB metadata migration** | None | N/A | New fields are additive — existing chunks without `category` metadata remain searchable (just not filterable by that field). No migration needed. |
| **Collection dimension mismatch on model change** | Low | High | All collections use the same embedding model from `config.py` — same dimension guaranteed. Risk only if user changes `EMBED_MODEL` between ingest and search, which already breaks single-collection mode. |

## Alternatives Considered

1. **`Settings.collection_name` global** — Like `Settings.embed_model`, set a global
   default collection name. Rejected because the MCP server handles concurrent client
   requests — two MCP clients could set different collections and overwrite each
   other's state.

2. **Separate ChromaDB directories per collection** — Each collection gets its own
   `chroma_db` directory with a separate SQLite file. Rejected: wasteful (multiple
   database files), complicates persistence management, and ChromaDB already supports
   multiple named collections within the same directory natively.

3. **Always use Ollama for metadata** — One Ollama call per file for classification.
   Rejected: adds ~2s per file for users who don't have a chat model or don't want the
   overhead. For 100 files, that's ~3 minutes of extra processing.

4. **YAML config for keyword rules** — Store keyword rules in a separate YAML file
   instead of a JSON env var. Rejected: env var is simpler, matches the project's
   existing `.env`-only configuration pattern, and avoids adding a YAML parser
   dependency.

5. **Client-side metadata filtering** — Apply the `metadata_filter` after fetching
   all chunks from the vector store. Rejected: wastes vector-store bandwidth on
   chunks that will be discarded, and `top_k` may return fewer results than
   requested. **Note: the initial implementation used this approach but was revised
   during code review to use ChromaDB's native `where` clause for server-side
   filtering.**

## References

- OpenSpec change: `openspec/changes/add-multi-collection-metadata/`
- Specs:
  - `openspec/changes/add-multi-collection-metadata/specs/multi-collection/spec.md`
  - `openspec/changes/add-multi-collection-metadata/specs/metadata-extraction/spec.md`
  - `openspec/changes/add-multi-collection-metadata/specs/watch-command/spec.md`
- Source:
  - `src/rag_mcp/config.py` — new env vars
  - `src/rag_mcp/metadata_extractor.py` — extraction logic
  - `src/rag_mcp/ingestion.py` — collection-aware ingestion + metadata attachment
  - `src/rag_mcp/retrieval.py` — collection-aware search + metadata filtering + list_collections
  - `src/rag_mcp/watcher.py` — collection routing for auto-ingestion
  - `src/rag_mcp/cli.py` — `--collection` flags + `list-collections` subcommand
  - `src/rag_mcp/server.py` — MCP tool collection parameter + `list_collections` tool
- Tests:
  - `tests/test_metadata_extractor.py` — 13 tests
  - `tests/test_ingestion.py` — 5 collection/metadata tests
  - `tests/test_retrieval.py` — 5 collection/filter/list tests
  - `tests/test_mcp_tools.py` — 7 MCP collection tests
  - `tests/test_watcher.py` — updated mock signatures
- AGENTS.md conventions: multi-collection support, metadata extraction
- `.env.example`: new `METADATA_EXTRACTION_MODE`, `METADATA_KEYWORD_RULES`, `OLLAMA_CLASSIFY_MODEL`

## Post-Review Revision

A code review of the initial implementation identified 7 issues across
`metadata_extractor.py`, `retrieval.py`, `ingestion.py`, `watcher.py`, and tests.
These were addressed within the same change.

### Key fixes

| # | Fix | Rationale |
|---|-----|-----------|
| 1 | **Server-side metadata filtering** — Changed from client-side `_matches_filter()` to ChromaDB's native `where` clause via `collection.query(where=...)`. | Spec and design both call for server-side filtering. Client-side filtering wastes vector-store bandwidth and can return fewer than `top_k` results. |
| 2 | **Misleading Ollama comment** — Fixed comment from "Use requests" to "Use urllib.request". | The code uses stdlib `urllib`, not the `requests` library. Inaccurate comments mislead maintainers. |
| 3 | **Performance cap on metadata fetches** — Added `limit=10000` to `list_documents()` and `list_collections()` metadata `get()` calls. | Prevents memory pressure on large collections (100k+ chunks). |
| 4 | **Empty-document debug log** — Added `logger.debug()` when `documents` is empty in `_read_and_chunk_file()`. | Helps diagnose why metadata extraction was skipped for a file. |
| 5 | **Typo fix** — "llmaindex" → "llamaindex" in `extract_metadata()` docstring. | — |
| 6 | **Watcher class docstring** — Added `_collection_name` to the Attributes list. | Missing from initial implementation. |
| 7 | **Test cleanup** — Removed unused `tmp_path` parameter from `test_ingest_into_named_collection`. | — |
