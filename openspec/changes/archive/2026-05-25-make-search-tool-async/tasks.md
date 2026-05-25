## 1. MCP Search Handler

- [x] 1.1 Change `search_documents` in `server.py` from sync `def` to `async def`.
- [x] 1.2 Wrap the existing `search(...)` invocation in `asyncio.to_thread(...)`.
- [x] 1.3 Preserve all parameters and returned list-of-dicts shape.

## 2. Tests

- [x] 2.1 Add or update an MCP tool test proving `search_documents` still returns expected results.
- [x] 2.2 Add or update a responsiveness test for concurrent search during an in-flight async operation.
- [x] 2.3 Confirm CLI search remains unchanged.

## 3. Verification

- [x] 3.1 Run retrieval, MCP tool, and async responsiveness tests.
- [x] 3.2 Validate the OpenSpec change.
