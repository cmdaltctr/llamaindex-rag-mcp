## Context

One server runs one `Engine`, and the `Engine` owns one vector store. Every collection in the Knowledge Base is therefore in the same database today. The user wants the display to stay correct if several databases appear later. The Profile tab starts its list on `documents` (`ProfilePanel.tsx:29`) and shows plain text when no profile is stored.

## Goals / Non-Goals

**Goals**
- Show the database for each collection, using data from the server.
- Adding or removing a backend touches the registry and one logo file only.
- Remove the false impression that `documents` is a saved profile.

**Non-Goals**
- Running several databases in one server. The `store` field is per collection so the API does not change when that arrives.
- Editing the collection name. That is `add-collection-display-name`.
- Showing paths, URIs or credentials.

## Decisions

### D1. `store` is a per-collection field
Each item from `GET /v1/collections` carries `store: {name, label}`. All items hold the same value today. A global field would force an API break later. The route does not branch on a store name.

### D2. The registry owns the label, the web folder owns the logo
`register(..., label=...)` gains an optional keyword `label`. `describe()` returns it, or the registered name when no label was given. The two built-in backends set `LanceDB` and `ChromaDB`. An optional argument keeps the existing `register()` calls in `tests/test_vectordb_registry_availability.py` working. The logo is found by convention at `/integrations/vector-stores/<name>.png`. This keeps image concerns out of `core/` and gives one rule for adding a backend: one module, one `register()` line, one PNG. The `<img>` hides itself on load error, so a missing file shows the label only.

Alternative rejected: a `logo` argument on `register()`. It puts a web asset name in `core/`.

### D3. Where the route gets the store name
`compose.configured_vector_store()` already exists for this purpose (`compose_engine.py:168`). It is the sanctioned way for a transport to read the adapter name without calling `get_settings()`, and `install_login_watcher.py` already uses it. The route calls it, then `registry.describe(name)["label"]`. No change to the public `Engine` surface (architecture invariant 10). Chroma cloud and local both report `chroma`. Cloud details stay out of the response.

Alternative rejected: a new `Engine.store_name` property. It widens the public API for a display value, and every fake Engine in the web tests would need it.

### D4. Fixed logo box
`StoreBadge` renders a `size-5` box with `object-contain` for the image and `text-meta` for the label. The two supplied logos differ in shape (246×159 and 385×385), so a fixed box keeps the header height equal.

### D5. Profile tab state
The selected value is `Profile | null`. It starts as `storedProfile` when that value is one of the selectable profiles (`documents`, `codebase`), and as `null` otherwise. A stored tag outside that list still shows in the status badge, but the list starts empty. The value resets when the collection changes (the component already has a `key` per collection). `Select` gets the placeholder "Choose a profile". The button is disabled while the value is `null` or a flow is open. The status line always renders `Stored profile` plus a badge: `hue` for a profile, `neutral` for "No profile".

## Risks / Trade-offs

- `configured_vector_store()` reads settings, not the live Engine. A test that injects a fake Engine must also patch this function. In production both come from the same settings at startup.
- About ten web test files and fake servers build `CollectionInfo` objects (`web/src/test/fakeDocumentsServer.ts`, `web/src/studio/test/fakeServer.ts`, `web/src/experiments/test/runRouter.ts` and others). Each needs the new `store` field.
- Logo files are trademarks of their owners. Keep them in `web/public` with the source noted in the TDR, and do not alter them.
- Chip text grows by one label. If the chips wrap badly on narrow screens, the task list includes a visual check at phone width.

## Migration Plan

Additive API field and additive UI. No data migration. Rollback is a revert.

## Open Questions

- None.
