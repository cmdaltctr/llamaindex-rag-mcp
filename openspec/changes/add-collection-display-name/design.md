## Context

The collection name is the storage address: LanceDB writes `{lancedb_uri}/{name}.lance`, Chroma uses it as the collection key, and every search, ingest, delete and MCP call passes it. `VectorStore` has no rename method. Collection metadata already holds `profile` and is merged on write (`update_collection_metadata`).

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
Key `display_name`, next to `profile`. Clearing stores an empty string, and readers treat `""` as unset, because a metadata merge cannot be relied on to delete a key on every backend. Task 1.1 confirms behaviour on LanceDB and Chroma before the route is written.

### D2. Route follows the existing `/profile` convention
`PATCH /v1/collections/{collection}/display-name`, body `{display_name: string}`. It sits beside `PATCH .../profile`. It needs no preview and confirmation token, because the change is reversible and loses no data. It uses the same guard as the profile route: `require_session("manage")` (`routes_admin.py:36`). The API has no "write" scope. A bearer token or notebook credential cannot rename a project.

The route SHALL check `store.collection_exists(collection)` first and return 404 when it is false. Without this check the write creates data: Chroma's `update_collection_metadata` calls `get_or_create_collection` (`chroma.py:366`), and LanceDB parks the value as pending metadata for a collection that does not exist (`lancedb.py:461`).

### D2a. Side effect of a write on LanceDB
`_write_table_metadata` calls `update_schema_metadata`, which creates a new table version. Two things key on that version:
- the BM25 cache (Critical Gotcha 14), which rebuilds on the next search;
- preview tokens for delete and profile change (`confirmations.py:68`), which then fail closed and ask for a new preview.

The profile change already has the same effect, so this is accepted. The write is skipped when the value is unchanged (`lance_meta.py:193`), so saving the same name costs nothing. The TDR records this.

### D3. Validation at the boundary
Trim, then 1 to 80 characters, or empty to clear. Control characters are rejected. The text is data: the web app renders it as text and never as markup.

### D4. One helper for the shown name
`web/src/lib/collectionTitle.ts` exports `collectionTitle(info) => info.display_name ?? info.name`. Home, chips and header all call it. Three callers meet the Rule of Three, so the helper is justified. It stays one line, with no wider abstraction.

### D5. Editor behaviour
`DisplayNameEditor` is a small controlled input with a pencil button. Enter saves through a `useMutation` that invalidates the collections query. Escape cancels. It shows a pending state and keeps focus handling accessible: the pencil has an `aria-label` that names the collection, the input has a visible label for screen readers, and success or failure is announced with `role="status"` or `role="alert"`.

## Risks / Trade-offs

- Users may expect the display name to work in MCP calls. The grey "Collection name" line and the docs state the rule.
- Metadata write races: two tabs can overwrite each other. Last write wins. That is acceptable for a label.
- A rename on LanceDB makes an open delete or profile preview stale (D2a). The user sees the existing "preview again" message.
- About ten web test files and fake servers build `CollectionInfo` objects. Each needs `display_name`.
- Chroma metadata value rules: confirm empty strings are accepted (task 1.1). If not, the route stores a single space-free sentinel and tests cover it.

## Migration Plan

Additive. Existing collections have no `display_name` and show their collection name. Rollback is a revert; the extra metadata key is harmless.

## Open Questions

- None blocking. If task 1.1 shows a backend cannot store an empty string, use a documented sentinel and note it in the TDR.
