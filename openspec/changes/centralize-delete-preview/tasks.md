## 1. Shared Helper

- [ ] 1.1 Add a `preview_delete(...)` helper in `ingestion.py` for path, metadata, and collection modes.
- [ ] 1.2 Preserve current missing-collection dry-run behavior unless tests document otherwise.
- [ ] 1.3 Add unit tests for helper counts in all three modes.

## 2. Interface Refactor

- [ ] 2.1 Replace MCP `delete_documents` dry-run ChromaDB query blocks with the helper.
- [ ] 2.2 Replace CLI `delete --dry-run` ChromaDB query blocks with the helper.
- [ ] 2.3 Keep CLI-specific fields (`path`, `metadata_filter`) and display behavior intact.
- [ ] 2.4 Keep MCP result shape compatible with existing callers.

## 3. Verification

- [ ] 3.1 Run deletion-related tests.
- [ ] 3.2 Run MCP tool tests that cover dry-run deletion.
- [ ] 3.3 Validate the OpenSpec change.
