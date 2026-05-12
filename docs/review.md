# Codebase Review — LlamaIndex RAG MCP Server

**Reviewer**: a-review (build agent)
**Date**: 2026-05-12
**Commit scope**: Full `src/rag_mcp/` + `tests/`
**Test status**: 30/30 passing, 1 slow test (E2E stdio) deselected
**Coverage**: 92% overall

---

## Summary

This is a well-structured, focused MCP server that does one thing and does it
cleanly: ingest documents into a ChromaDB vector store via LlamaIndex, then
serve semantic search over them. The codebase is ~470 lines of source across
four modules, with 30 unit/integration tests achieving 92% coverage.

The architecture is sound — separation between ingestion, retrieval, reranking,
and the MCP server layer is clean. The test infrastructure (`conftest.py`) is
particularly well-thought-out for handling the tricky interaction between
module-level side effects and test isolation.

**Overall assessment**: Production-ready for personal/small-team use. A few
areas worth addressing are noted below.

---

## Architecture

```
server.py ─── FastMCP entry point, tool registration, delegates to ↓
  ├── ingestion.py ─── document loading, chunking, ChromaDB indexing
  ├── retrieval.py ─── semantic search + reranker orchestration
  └── reranker.py ─── cross-encoder ONNX inference (singleton)
```

### Strengths

1. **Clean separation of concerns**. Each module owns its own config
   (env vars), its own ChromaDB client creation, and its own embedding model
   setup. This makes them independently importable and testable.

2. **Singleton reranker with graceful fallback**. The `CrossEncoderReranker`
   class handles model loading failures without crashing. It retries on
   transient failures and falls back to un-reranked results permanently.
   Thread-safe via double-checked locking.

3. **Test infrastructure is excellent**. The `conftest.py` handles a genuinely
   tricky problem — ChromaDB's `EphemeralClient` shares in-memory state across
   instances, and both `ingestion.py` and `retrieval.py` set module-level
   constants at import time. The fix uses `sys.modules` patching to keep both
   modules in sync on collection naming, regardless of import order.

4. **No external service dependencies at runtime**. Everything runs locally:
   Ollama for embeddings, ONNX Runtime for reranking, ChromaDB for storage.
   No API keys, no cloud services.

5. **Error handling in MCP tools**. All tool handlers return dicts, never
   raise exceptions. This is the correct pattern for MCP — let FastMCP wrap
   errors as `TextContent` with `isError`.

### Concerns

1. **Duplicate embedding model initialisation**. Both `ingestion.py` and
   `retrieval.py` independently set `Settings.embed_model` at module import
   time. The AGENTS.md explains why (either may be imported first), but it
   means the `OllamaEmbedding` constructor runs twice on startup. This is
   harmless but slightly wasteful. A shared `embed.py` module that both import
   would be cleaner.

2. **`_get_chroma_collection()` is only in `ingestion.py`**. The `retrieval.py`
   module creates its own `PersistentClient` and `get_collection` inline rather
   than sharing the collection accessor. This means the connection logic is
   duplicated. A shared `db.py` or moving `_get_chroma_collection` to a common
   module would reduce coupling.

3. **`import numpy as np` inside `rerank()` method** (line 214). This import
   is inside the hot path of every rerank call. NumPy should be imported at
   the module level. It's already a hard dependency (via ONNX runtime), so
   there's no runtime cost to making it a top-level import.

4. **No async support**. All MCP tools are synchronous. For a local stdio
   server this is fine — the blocking calls (ChromaDB, ONNX inference) run
   on the server's event loop. But if the server ever moves to SSE transport
   or needs to handle concurrent requests, the blocking I/O will become a
   bottleneck.

5. **`list_documents()` fetches all metadata**. For large collections, calling
   `collection.get(include=["metadatas"])` loads every chunk's metadata into
   memory. This could be problematic with millions of chunks. Consider adding
   a `limit` parameter or using pagination.

---

## Module-by-Module Review

### `server.py` (95 lines, 89% coverage)

Clean MCP registration. The `main()` function and `if __name__` guard are
correctly structured. Missing lines 91 and 95 are the `main()` body and
the `__name__` guard — only exercised by the slow E2E test.

**Note**: The `description` strings in `@mcp.tool()` are duplicated with
the function docstrings. FastMCP uses the decorator's `description` for the
tool metadata shown to LLMs, and the docstring for Python help(). Having
both is technically correct but slightly redundant. Not a real issue.

### `ingestion.py` (130 lines, 95% coverage)

Solid ingestion pipeline. The `SUPPORTED_EXTENSIONS` set is well-chosen.
Missing lines are the actual ChromaDB write path (line 67 — `_get_chroma_collection`
body, lines 116/123 — the `VectorStoreIndex` construction and return). These
are exercised by integration tests but not by the fast unit tests in
`test_ingestion.py`.

**Observation**: The `SimpleDirectoryReader` with `filename_as_id=True` is
a good choice — it means re-ingesting the same file updates rather than
duplicates the chunks. However, there's no explicit deduplication or
"remove old version before re-indexing" logic. LlamaIndex handles this
internally via the node ID, but it's worth being aware of.

### `retrieval.py` (109 lines, 98% coverage)

The `top_k * 2` strategy when reranking is a good heuristic. The score
filtering happens after reranking, which is correct — you want the reranker
to see all candidates before the threshold cuts any.

Missing line 67 is the empty-collection early return path, which is tested
indirectly through the MCP tools but not by a direct unit test.

### `reranker.py` (229 lines, 88% coverage)

The most complex module, and the one with the most interesting test coverage
story. The 88% coverage reflects the real ONNX inference path (lines 145-147,
214-221) which requires downloading a 23MB model. The test suite mocks this
with `MagicMock`, which is the right call for fast tests.

The sigmoid function uses a numerically stable two-branch implementation
that avoids overflow for both large positive and large negative values.
The tests verify this with boundary values at ±1000.

**Platform-aware ONNX variant selection** is a nice touch — the
`_select_onnx_variant()` function picks the quantised ARM64 model on
Apple Silicon, which is ~23MB vs ~90MB for the fp32 variant.

---

## Test Suite Assessment

| File | Tests | Coverage Focus | Quality |
|------|-------|---------------|---------|
| `test_reranker.py` | 16 | Sigmoid, ONNX variant, singleton, fallback, mock inference | ★★★★★ |
| `test_ingestion.py` | 4 | Path validation, empty dir, list empty | ★★★☆☆ |
| `test_mcp_tools.py` | 5 | Tool discovery, ingest, search, list, param validation | ★★★★☆ |
| `test_retrieval.py` | 5 | Empty store, threshold, rerank flag, default search | ★★★★☆ |
| `test_e2e_stdio.py` | 1 | JSON-RPC handshake over stdio subprocess | ★★★★★ |

### What the tests cover well

- **Reranker edge cases**: The 16 reranker tests are comprehensive — sigmoid
  edge cases, monotonicity, boundary values, platform variant selection,
  singleton identity, fallback behaviour, mock inference with score
  normalisation and sorting.

- **MCP tool routing**: The integration tests go through the real FastMCP
  client-server stack (in-memory), not just function calls. This catches
  serialisation issues, parameter validation, and response format problems.

- **Test isolation**: The `conftest.py` handles the genuinely tricky problem
  of ChromaDB state leaking between tests. Each test gets a fresh store.

### What the tests don't cover

- **Real Ollama embeddings**: All tests use `MockEmbedding`. There are no
  tests that verify real embedding quality or dimension mismatches between
  models.

- **Actual reranker model inference**: The ONNX session is mocked. No test
  downloads the real model and runs inference. This is a trade-off between
  test speed and coverage realism.

- **Concurrent access**: No tests for thread safety of the singleton
  reranker under concurrent calls.

- **Large document ingestion**: No stress tests for ingesting hundreds of
  files or very large documents.

- **Score quality / retrieval accuracy**: No tests that measure whether
  the search actually returns relevant results for known queries. This is
  the gap that the planned experiment should address.

---

## Security Considerations

- No secrets or API keys in code. All config via `.env`.
- No user input sanitisation for file paths — `ingest_documents` accepts
  arbitrary paths. In an MCP context, the host (Claude Desktop, OpenChamber)
  is trusted, but if this were exposed to untrusted input, path traversal
  would be a concern.
- No rate limiting on ingestion or search. Acceptable for a local tool.
- ChromaDB data is stored unencrypted on disk. Acceptable for local use.

---

## Recommendations (Priority Order)

1. **Move `import numpy` to module level** in `reranker.py` — trivial fix,
   removes redundant import per call.

2. **Add retrieval accuracy experiments** — the test suite validates
   mechanics (does it run? does it return the right shape?) but not quality
   (does it return the *right* results?). See `experiments.md` for a plan.

3. **Consider a shared config module** to eliminate the duplicate
   `Settings.embed_model` and `CHROMA_PERSIST_DIR`/`COLLECTION_NAME` setup
   in `ingestion.py` and `retrieval.py`.

4. **Add a test with real Ollama embeddings** (marked `@pytest.mark.slow`)
   to catch dimension mismatches or model availability issues that MockEmbedding
   won't surface.

5. **Document the re-ingestion behaviour** — what happens when you ingest
   the same file twice? Does it update, duplicate, or replace?
