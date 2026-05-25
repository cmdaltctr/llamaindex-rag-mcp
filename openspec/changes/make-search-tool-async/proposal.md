## Why

The async ingestion work was intended to keep MCP tool calls responsive during long-running operations, but `search_documents` still exposes a synchronous handler that performs blocking embedding/search work. Making the MCP search tool explicitly async aligns the tool surface with the responsiveness contract and removes reliance on FastMCP implementation details.

## What Changes

- Change the MCP `search_documents` handler to `async def`.
- Offload the existing synchronous `retrieval.search()` call with `asyncio.to_thread(...)`.
- Preserve the synchronous CLI search path and `retrieval.search()` public function for now.
- Add or update tests to verify search can be invoked concurrently with an in-flight ingest/tool call.

## Capabilities

### New Capabilities

### Modified Capabilities
- `async-ingestion`: MCP search SHALL not block the event loop while performing synchronous embedding/retrieval work.

## Impact

- Affected code: `src/rag_mcp/server.py`, async responsiveness tests.
- No MCP tool name or parameter changes.
- No changes to ranking, reranking, or search result shape.
