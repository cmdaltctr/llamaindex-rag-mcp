## Why

The collection name is both the project title in the web app and the storage address that retrieval, ingestion, the CLI and MCP tools use. In the demo data the collection is called `documents`, so the title, the "4 documents" count and the profile preset all read the same. Users also cannot give a project a friendly name, and a real rename would break every caller that passes the old name.

## What Changes

- A collection gets an optional **display name**. It is stored in the collection metadata next to `profile`, so it works on LanceDB and Chroma with no new storage code.
- `GET /v1/collections` returns `display_name` (string or `null`) for each collection.
- New route `PATCH /v1/collections/{collection}/display-name` sets or clears it. It uses the same session-only `manage` guard as the profile change, and returns 404 for an unknown collection. An empty or whitespace value clears it. The value is trimmed and limited to 80 characters. No preview step: the change loses no data.
- The web workspace shows the display name when set, otherwise the collection name, on the Home card, the project chips and the project header.
- The project header gets a pencil button. Click, type, Enter to save, Escape to cancel.
- Under the title the header shows `Collection name: <name>` in small grey mono text. That is the name MCP, CLI and API calls use.
- The collection name itself never changes. No rename of stored data.
- Docs (`web-workspace.md`, `openapi.yaml`) and a TDR record the rule.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-web-workspace`: collections carry a display name that users can edit; the collection name stays visible and stable.

## Impact

- Python: `src/omrg/transports/api/routes_admin.py` (new route, beside the profile route), `routes_documents.py` (listing), `openapi.yaml`.
- On LanceDB a rename creates a new table version. The BM25 cache rebuilds on the next search, and an open delete or profile preview must be repeated. The profile change already behaves this way.
- Web: `web/src/api/documents.ts`, `web/src/api/mutations.ts`, `web/src/knowledge-base/Project.tsx`, `web/src/components/CollectionPicker.tsx`, `web/src/home/HomeView.tsx`, new `web/src/knowledge-base/DisplayNameEditor.tsx`.
- Tests: route tests on both stores, OpenAPI contract, Vitest for the editor and each place the name shows.
- Docs: `docs/guides/web-workspace.md`, new TDR.
- No new dependency. Additive API. Stored vectors and collection names are untouched.
- Order: this change builds on `add-vector-store-label-to-knowledge-base` (same `CollectionInfo` type and header). Merge that one first, or rebase this one onto it.
