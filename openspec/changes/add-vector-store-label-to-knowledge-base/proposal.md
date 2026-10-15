## Why

The Knowledge Base does not say which vector database holds a project. LanceDB is the default and Chroma is an optional extra, so a user cannot tell where the data lives. The Profile tab also reads as if a profile is saved when none is: its "New profile" list starts on `documents`, which is the same word as the collection name in the demo data.

## What Changes

- `GET /v1/collections` returns a `store` object for each collection: `{name, label}` (for example `{name: "lancedb", label: "LanceDB"}`). The `label` comes from the vector-store registry. The `name` is the registered backend name.
- `register()` in `core/vectordb/registry.py` takes a new optional `label` argument. A backend added later declares its label in its own `register()` call. Without a label, the registered name is shown. No web code changes.
- The route reads the store name with the existing `compose.configured_vector_store()`. The public `Engine` API does not change.
- The web workspace shows the database in four places:
  - project header: logo and name, in a fixed-size box;
  - Home card and project chips: name only;
  - `SourceTable`: a new **Database** column, name only.
- Logos live in `web/public/integrations/vector-stores/<name>.png`. Each file is named after the registered backend (`lancedb.png`, `chroma.png`). The supplied files change from `.webp` to `.png` because they hold PNG data. A backend with no logo file shows its name only.
- The Profile tab pre-selects the stored profile when one exists, and starts with no selection when none exists. "Preview profile change" stays disabled until a profile is selected. The status line shows a badge in both cases, including the neutral "No profile" badge.
- Docs (`docs/guides/web-workspace.md`, `docs/guides/mcp-tools.md` only if it lists the field, `openapi.yaml`) and a TDR record the behaviour.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-web-workspace`: the collection list returns the store; the Knowledge Base and Home show the database; the Profile tab shows the stored profile truthfully.
- `vector-store-registry`: each registered backend carries a human-readable label.

## Impact

- Python: `src/omrg/core/vectordb/registry.py`, `src/omrg/transports/api/routes_documents.py`, `src/omrg/transports/api/openapi.yaml`.
- Web: `web/src/api/documents.ts`, `web/src/knowledge-base/{Project,SourceTable,ProfilePanel}.tsx`, `web/src/components/CollectionPicker.tsx`, `web/src/home/HomeView.tsx`, new `web/src/components/StoreBadge.tsx`, `web/public/integrations/vector-stores/`.
- Tests: registry, API route, OpenAPI contract, Vitest for each changed component. Web fake servers and fixtures that build collections gain the `store` field.
- Docs: `docs/guides/web-workspace.md`, new TDR (next number `032`).
- No new dependency. No change to stored data. Additive API field.
