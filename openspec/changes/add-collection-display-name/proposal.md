## Why

The collection name is both the project title in the web app and the storage address that retrieval, ingestion, the CLI and MCP tools use. In the demo data the collection is called `documents`, so the title, the "4 documents" count and the profile preset all read the same. Users also cannot give a project a friendly name, and a real rename would break every caller that passes the old name.

## What Changes

- A collection gets an optional **display name**. It is stored in the collection metadata next to `profile`, so it works on LanceDB and Chroma with no new storage code.
- `GET /v1/collections` returns `display_name` (string or `null`) for each collection.
- New route `PATCH /v1/collections/{collection}/display-name` sets or clears it, and returns `{collection, display_name}`.
  - It uses the same session-only `manage` guard as the profile change. Bearer and notebook credentials get 403.
  - It returns 404 for an unknown collection and creates nothing.
  - The server trims the value. An empty value clears the display name.
  - More than 80 Unicode code points, or a control character, gives 400.
  - No preview step, because the change loses no data.
- The web workspace shows the display name when set, otherwise the collection name. This applies to the Home card, the project chips in the Knowledge Base and in Chat, and the project header.
- The project header gets a pencil button. Click, type, Enter to save, Escape to cancel.
- Under the title the header shows `Collection name: <name>` in small grey mono text. That is the name MCP, CLI and API calls use.
- Places where the name acts as an identifier keep the collection name: "Sources in <name>", the Chat input "Ask <name> a question", and the delete dialog.
- The collection name itself never changes. No rename of stored data.
- Docs (`web-workspace.md`, `openapi.yaml`) and a TDR record the rule.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-web-workspace`: collections carry a display name that users can edit; the collection name stays visible and stable.

## Impact

- Python: `src/omrg/transports/api/routes_admin.py` (new route beside the profile route; module docstring widened), `routes_documents.py` (listing), `openapi.yaml`.
- On LanceDB a rename creates a new table version. The BM25 cache rebuilds on the next search, and an open delete or profile preview must be repeated. The profile change already behaves this way.
- Web: `web/src/api/documents.ts`, `web/src/api/mutations.ts`, `web/src/knowledge-base/Project.tsx`, `web/src/components/CollectionPicker.tsx` (used by Knowledge Base and Chat), `web/src/home/HomeView.tsx`, new `web/src/lib/collectionTitle.ts`, new `web/src/knowledge-base/DisplayNameEditor.tsx`.
- Tests: metadata round-trip in `tests/test_vectordb_contract.py` (LanceDB here, Chroma in the chroma-extra CI job), route tests, OpenAPI contract, Vitest for the editor and each place the name shows. The clean-base tripwire counts need a re-pin.
- Docs: `docs/guides/web-workspace.md`, new TDR.
- No new dependency. Additive API. Stored vectors and collection names are untouched.
