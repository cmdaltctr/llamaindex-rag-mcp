## 1. Shared Helper

- [x] 1.1 Add a `preview_delete(...)` helper in `ingestion.py` for path, metadata, and collection modes.
- [x] 1.2 Preserve current missing-collection dry-run behavior unless tests document otherwise.
- [x] 1.3 Add unit tests for helper counts in all three modes.

## 2. Interface Refactor

- [x] 2.1 Replace MCP `delete_documents` dry-run ChromaDB query blocks with the helper.
- [x] 2.2 Replace CLI `delete --dry-run` ChromaDB query blocks with the helper.
- [x] 2.3 Keep CLI-specific fields (`path`, `metadata_filter`) and display behavior intact.
- [x] 2.4 Keep MCP result shape compatible with existing callers.

## 3. Verification

- [x] 3.1 Run deletion-related tests.
- [x] 3.2 Run MCP tool tests that cover dry-run deletion.
- [x] 3.3 Validate the OpenSpec change.
