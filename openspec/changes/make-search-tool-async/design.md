## Context

`ingest_documents` is an async MCP tool, but `search_documents` is currently synchronous. `retrieval.search()` opens ChromaDB and triggers query embedding through LlamaIndex/Ollama, which is synchronous and can block for network/model latency.

## Goals / Non-Goals

**Goals:**
- Make MCP `search_documents` explicitly async.
- Avoid blocking the MCP event loop during synchronous retrieval work.
- Preserve existing sync search API for CLI and internal callers.

**Non-Goals:**
- Rewriting `retrieval.search()` to be fully async.
- Changing ChromaDB or Ollama client libraries.
- Changing search scoring or result schema.

## Decisions

- Wrap the whole `search(...)` call in `asyncio.to_thread(...)` at the MCP tool boundary.
- Do not change CLI `rag-mcp search`, because CLI is single-command and does not need event-loop interleaving.
- Keep future fully async retrieval as a separate change if needed.

## Risks / Trade-offs

- Thread offload adds small overhead for fast searches → acceptable because embedding/search already performs blocking I/O.
- ChromaDB reads happen from a worker thread → consistent with existing ingestion use of `asyncio.to_thread` for sync ChromaDB calls.
- Existing FastMCP may already offload sync tools → explicit async still documents and tests the intended behavior.
