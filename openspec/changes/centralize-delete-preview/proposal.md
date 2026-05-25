## Why

Dry-run delete preview logic is duplicated between the MCP tool and CLI command. Centralizing it reduces maintenance risk and ensures path, metadata, and collection dry-runs behave identically across both interfaces.

## What Changes

- Add a shared delete-preview helper near the existing delete functions in `ingestion.py`.
- Replace duplicate ChromaDB dry-run query blocks in `server.py` and `cli.py` with calls to the shared helper.
- Preserve current CLI and MCP response shapes, including CLI-specific display fields such as `path` and `metadata_filter`.
- Add tests for the shared helper and keep interface-level tests focused on validation/output.

## Capabilities

### New Capabilities

### Modified Capabilities
- `document-deletion`: Dry-run preview SHALL be provided by shared deletion logic and remain consistent across CLI and MCP interfaces.

## Impact

- Affected code: `src/rag_mcp/ingestion.py`, `src/rag_mcp/server.py`, `src/rag_mcp/cli.py`, deletion-related tests.
- No public CLI flags or MCP tool names change.
- No data migration or new dependencies.
