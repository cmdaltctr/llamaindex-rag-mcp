# TDR-033: The collection name was the only project title, so add an editable display name and keep the collection name fixed

- **Date:** 2026-10-15
- **Status:** Accepted (OpenSpec change `add-collection-display-name`; browser check at 390 px and 1200 px, light and dark, against a real LanceDB store)
- **Deciders:** Aizat
- **Tags:** web | knowledge-base | collection-metadata | api
- **Related:** [TDR-032](032-knowledge-base-hid-the-database-and-the-profile-list-implied-a-stored-profile.md), `openspec/changes/add-collection-display-name/`

## Context

The web workspace used the collection name as the project title. That name is
also the storage address: LanceDB writes `{lancedb_uri}/{name}.lance`, Chroma
uses it as the collection key, and every search, ingest, delete and MCP call
passes it. In the demo data the collection is called `documents`, so the title,
the "4 documents" count and the profile preset all read the same.

`VectorStore` has no rename method. A real rename would need new code in each
backend and would break every caller that passes the old name.

## Decision

1. **Add an optional display name, and never rename the collection.** The
   display name is a label in the collection metadata (`display_name`), next to
   `profile`. It works on LanceDB and Chroma with no new storage code.
2. **Show the real name beside the label.** The project header shows
   `Collection name: <name>` in small grey mono text, and each Home card shows
   the same line under its counts. That is the name for MCP, CLI and API calls. "Sources in <name>", the Chat question box and the delete
   dialog keep the collection name, because the user may need to type or match
   it. The address bar keeps it too.
3. **A clear stores an empty string.** A metadata merge cannot be relied on to
   delete a key on every backend. Readers treat `""` and a missing key as unset.
   LanceDB JSON-encodes each value, so `""` round-trips. The Chroma result comes
   from the chroma-extra CI job (see Consequences).
4. **The route is `PATCH /v1/collections/{collection}/display-name`.** It lives in
   `routes_admin.py` beside the profile route and uses the same guard,
   `require_session("manage")`. A bearer or notebook credential gets 403. The
   work runs inside `admitted(runtime)`, so a shutdown waits for it. It returns
   `{collection, display_name}`, with `null` after a clear. It has no preview and
   no token, because it loses no data and can be undone.
5. **An unknown collection returns 404 and creates nothing.** The route checks
   `collection_exists` first. Without that, Chroma's `update_collection_metadata`
   calls `get_or_create_collection` and makes an empty collection, and LanceDB
   keeps the value as pending metadata for a name that has no data. The profile
   route returns 400 for the same case; the 404 here is deliberate and matches
   the other "unknown" routes.
6. **Validation.** The server trims the value. Empty clears. A control character
   (U+0000 to U+001F, U+007F) or more than 80 Unicode code points gives 400. The
   server maps request validation errors to 400, not 422. The web editor counts
   with `[...value].length` so both sides agree on emoji, and blocks a longer
   name before it sends.
7. **One metadata read per collection.** The listing reads `profile` and
   `display_name` from the same `get_collection_metadata` call. When the read
   fails, both are `null` and the list still loads.
8. **Where it shows.** The Home card, the project list in the Knowledge Base and
   in Chat, and the project title show the display name, falling back to the
   collection name. Chat shares `CollectionPicker`, so it changes with it.

## Consequences

### Positive

- Users can give a project a friendly name, and the real name stays visible.
- Retrieval, ingestion, MCP tools and the CLI are untouched.
- No new storage code, and no new dependency.

### Negative

- On LanceDB a write calls `update_schema_metadata`, which creates a new table
  version. The BM25 cache keys on that version (Critical Gotcha 14), so the next
  keyword search rebuilds its index. Open delete and profile previews key on it
  too (`confirmations.py`), so they fail closed and must be made again. The
  profile change already behaves this way. Saving the same value writes nothing
  (`lance_meta.py`).
- A rename on a LanceDB collection that has only a pending creation, with no
  table yet, is held in memory and lost on restart. The web app lists only
  collections with data, so this is accepted.
- Two browser tabs can overwrite each other. The last write wins.
- About ten web test files and fake servers build collection objects and each
  needed `display_name`.
- The Chroma half of the round-trip test runs only in the chroma-extra CI job.
  If Chroma rejects `""`, switch to a documented sentinel and update this record.

### Neutral

- The display name is not unique. The collection name tells collections apart.
- The CLI and MCP tools do not show display names.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Rename the stored collection | It breaks every caller that passes the old name, and it needs a rename method in each backend. |
| Store the display name in the workspace database | It would not travel with the collection and would need a second store to keep in step. |
| A preview and token for the rename | The change loses no data and can be undone, so the extra step only adds friction. |
| Hide the collection name | Users need it for MCP, CLI and API calls. |

## How to Recognise / Handle This Again

- Symptom: a rename on LanceDB makes a delete or profile preview fail with "preview again". Cause: the new table version. Make a new preview.
- Symptom: a project shows its collection name after you set a display name. Check that the name is not empty after trimming, and that the collection list was refreshed.
- Symptom: the chroma-extra CI job fails the display name round-trip. Chroma rejects an empty string. Use a documented sentinel for a clear, and update `routes_admin.py` and this record.
- Re-evaluate when a collection rename is wanted. It needs a `rename_collection` method on `VectorStore`, in both backends, and a migration story for callers.

## References

- `src/omrg/transports/api/routes_admin.py`, `src/omrg/transports/api/routes_documents.py`, `src/omrg/transports/api/openapi.yaml`
- `tests/test_vectordb_contract.py` (`TestCollectionMetadata`), `tests/unit/test_web_display_name.py`
- `web/src/knowledge-base/DisplayNameEditor.tsx`, `web/src/lib/collectionTitle.ts`, `web/src/components/CollectionPicker.tsx`, `web/src/home/HomeView.tsx`
- `docs/guides/web-workspace.md` ("Display name and collection name")
- `openspec/changes/add-collection-display-name/`
