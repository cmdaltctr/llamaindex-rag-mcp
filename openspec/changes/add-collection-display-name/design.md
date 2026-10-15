## Context

The collection name is the storage address: LanceDB writes `{lancedb_uri}/{name}.lance`, Chroma uses it as the collection key, and every search, ingest, delete and MCP call passes it. `VectorStore` has no rename method. Collection metadata already holds `profile` and is merged on write (`update_collection_metadata`). `GET /v1/collections` already reads that metadata for each collection to return `profile`, and returns `store` since `add-vector-store-label-to-knowledge-base`.

## Goals / Non-Goals

**Goals**
- Friendly, editable project names in the web app.
- Keep the real name visible so users know what to pass to MCP, CLI and API.
- Work on both backends with no new storage code.

**Non-Goals**
- Renaming the stored collection. It would break callers and needs a rename method in each backend. A later change can add it.
- Display names in the CLI or MCP tool output.
- Unique display names. The collection name already tells collections apart.

## Decisions

### D1. Display name lives in collection metadata
Key `display_name`, next to `profile`. Clearing stores an empty string, and readers treat `""` and a missing key as unset, because a metadata merge cannot be relied on to delete a key on every backend.

LanceDB JSON-encodes each value (`lancedb.py:462`), so `""` round-trips. The round-trip test goes in `TestCollectionMetadata` in `tests/test_vectordb_contract.py`. That suite already runs on both backends and is on the tripwire's list of Chroma-gated files. A new test file with a Chroma skip would fail the tripwire's file check (`test_clean_base_tripwire.py:461`). Chroma is not installed in the base environment, so only the chroma-extra CI job shows the Chroma result. If Chroma rejects `""`, the route stores a documented sentinel instead, and the TDR records it.

### D2. Route sits beside the profile route
`PATCH /v1/collections/{collection}/display-name`, body `{display_name: string}`, in `routes_admin.py` beside `PATCH .../profile`. The module docstring changes from "Preview-bound destructive routes" to cover collection metadata changes, and states that this route has no preview step.

- **Guard.** `require_session("manage")` (`routes_admin.py:36`), the same guard as the profile route. The API has no "write" scope. A bearer token or notebook credential gets 403.
- **Admission.** The work runs inside `async with admitted(runtime)`, like the profile route, so a shutdown waits for it.
- **No preview.** The change is reversible and loses no data, so it needs no confirmation token.
- **Existence check.** The route checks `store.collection_exists(collection)` first and returns 404 when it is false. Without this check the write creates data: Chroma's `update_collection_metadata` calls `get_or_create_collection` (`chroma.py:366`), and LanceDB parks the value as pending metadata (`lancedb.py:461`). The profile route returns 400 for an unknown collection (`contract.py:218`). This route returns 404 on purpose, to match the other "unknown" routes (`routes_jobs.py`, `routes_graphs.py`, `routes_inspect.py`).
- **Response.** `200` with `{collection: string, display_name: string | null}`. `null` means cleared.

### D2a. Side effect of a write on LanceDB
`_write_table_metadata` calls `update_schema_metadata`, which creates a new table version. Two things key on that version:
- the BM25 cache (Critical Gotcha 14), which rebuilds on the next search;
- preview tokens for delete and profile change (`confirmations.py:68`), which then fail closed and ask for a new preview.

The profile change already has the same effect, so this is accepted. The write is skipped when the value is unchanged (`lance_meta.py:193`), so saving the same name costs nothing. The TDR records this.

### D3. Validation at the boundary
1. Trim leading and trailing whitespace.
2. Empty after trimming: clear the display name.
3. Reject any control character (U+0000 to U+001F and U+007F).
4. Reject more than 80 Unicode code points. Python `len(str)` counts code points. The web counts with `[...value].length`, not `value.length`, so both sides agree on emoji.

A rejected value returns 400 with `error_type: "validation"`. The server maps request validation errors to 400, not 422 (`errors.py:93`). The text is data: the web app renders it as text and never as markup.

### D4. One helper for the shown name
`web/src/lib/collectionTitle.ts` exports `collectionTitle(info) => info.display_name ?? info.name`. Callers: the Home card, `CollectionPicker` (used by the Knowledge Base and by Chat), and the project header. Three callers meet the Rule of Three. The helper stays one line, with no wider abstraction.

These places keep the collection name, because there it is an identifier the user may need to type or match: "Sources in <name>", the Chat input "Ask <name> a question", the delete dialog, and URLs.

### D5. Editor behaviour
`DisplayNameEditor` is a small controlled input with a pencil button. Enter saves through a `useMutation` that invalidates the collections query. Escape cancels. It shows a pending state and keeps focus handling accessible: the pencil has an `aria-label` that names the collection, the input has a visible label for screen readers, and success or failure is announced with `role="status"` or `role="alert"`. The input checks the 80-code-point limit before sending. The server stays the authority.

### D6. One metadata read per collection
The listing already reads `get_collection_metadata` for `profile`. It reads `display_name` from the same result, so each collection costs one read. When the read fails, both `profile` and `display_name` are `null` and the listing still succeeds.

## Risks / Trade-offs

- Users may expect the display name to work in MCP calls. The grey "Collection name" line and the docs state the rule.
- Metadata write races: two tabs can overwrite each other. Last write wins. That is acceptable for a label.
- A rename on LanceDB makes an open delete or profile preview stale (D2a). The user sees the existing "preview again" message.
- LanceDB counts a collection that has only a pending creation, and no table yet, as existing (`lancedb.py:161`). A rename on it is held in memory and lost on restart. This is accepted: the web app lists only collections with data.
- About ten web test files and fake servers build `CollectionInfo` objects. Each needs `display_name`.
- New tests change the clean-base tripwire counts. They must be re-pinned.

## Migration Plan

Additive. Existing collections have no `display_name` and show their collection name. Rollback is a revert; the extra metadata key is harmless.

## Open Questions

- None blocking. The Chroma `""` result comes from the chroma-extra CI job. If it fails, use a documented sentinel (D1).
