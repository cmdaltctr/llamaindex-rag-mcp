## Context

`delete_documents(..., dry_run=True)` and `rag-mcp delete --dry-run` each open ChromaDB, fetch matching IDs/counts, catch exceptions, and construct a preview result. The core ChromaDB logic is structurally identical but lives in two files.

## Goals / Non-Goals

**Goals:**
- Provide one implementation for dry-run counts by path, metadata filter, and collection.
- Keep all user-visible behavior the same.
- Make future delete behavior changes testable in one place.

**Non-Goals:**
- Changing destructive delete semantics.
- Changing CLI validation or confirmation prompts.
- Changing MCP tool parameter names.

## Decisions

- Add `preview_delete(...)` in `ingestion.py` next to `remove_document`, `remove_by_metadata`, and `remove_collection`.
- Use explicit mutually exclusive inputs rather than overloading too much implicit behavior: path preview, metadata preview, and collection preview.
- Return a base result with `status`, `dry_run`, `mode`, `collection`, and `would_delete`; callers may add interface-specific fields.
- Match current behavior where missing collections preview as `would_delete: 0` rather than an error, unless tests reveal a stronger existing contract.

## Risks / Trade-offs

- Extracting helper incorrectly could alter CLI JSON fields → mitigate with snapshot-style assertions on current response keys.
- Keeping missing-collection dry-run as success may hide typos → preserve current behavior in this refactor and leave policy changes for a separate proposal.
