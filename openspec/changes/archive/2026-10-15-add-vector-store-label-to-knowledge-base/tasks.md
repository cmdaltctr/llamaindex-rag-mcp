## 1. Registry (tests first)

- [x] 1.1 Write failing tests: `describe("lancedb")["label"] == "LanceDB"`, `describe("chroma")["label"] == "ChromaDB"`, and a backend registered without `label` reports its name as the label.
- [x] 1.2 Add the optional `label` keyword to `register()`, return it from `describe()`, and set it for `chroma` and `lancedb`. Confirm the tests pass, and that 1.1 fails when the label code is removed.
- [x] 1.3 Confirm the existing `register()` calls in `tests/test_vectordb_registry_availability.py` still pass unchanged.

## 2. API

- [x] 2.1 Write failing route tests (patch `compose.configured_vector_store`): each item has `store: {name, label}` for `lancedb` and for `chroma`; with Chroma cloud settings the response contains no tenant, database or key.
- [x] 2.2 Add `store` to the `listCollections` response in `routes_documents.py`. Resolve the name with `compose.configured_vector_store()` and the label with `registry.describe()`.
- [x] 2.3 Add `store` to `CollectionInfo` in `openapi.yaml` (required, `additionalProperties: false`). Run `tests/unit/test_web_openapi_conformance*.py`.

## 3. Web

- [x] 3.1 Rename the logos to `lancedb.png` and `chroma.png` (the registered names) and place them in `web/public/integrations/vector-stores/`.
- [x] 3.2 Add `store` to `CollectionInfo` in `web/src/api/documents.ts`. Add it to every fake server and fixture that builds a collection (`grep -rln "chunk_count" web/src`).
- [x] 3.3 Write a failing Vitest test, then add `StoreBadge` (fixed `size-5` box, label text, hides a broken image).
- [x] 3.4 Show `StoreBadge` with logo in the `Project.tsx` header. Show `StoreBadge` with logo on the Home card, and the label as text in `CollectionPicker`.
- [x] 3.5 Add the Database column to `SourceTable` (name only). Pass the label in from `SourcesSection`. Update its test.
- [x] 3.6 Write failing tests for the Profile tab: stored `codebase` pre-selected; no profile gives the placeholder and a disabled button; a stored tag outside the list gives an empty list but still shows its badge; the badge shows in every case. Then change `ProfilePanel.tsx`.
- [x] 3.7 Run the web type check, lint and Vitest. Check the header at phone width and in light and dark themes.

## 4. Docs, TDR and verification

- [x] 4.1 Update `docs/guides/web-workspace.md` (Knowledge Base row, new column, Profile tab behaviour) and any other guide that lists the collection fields. Grep `docs/guides/` for `document_count`.
- [x] 4.2 Write TDR `032` (load `s-tdr`): label in the registry, logo by convention in `web/public`, why `store` is per collection, why `configured_vector_store()` and not a new Engine property, the Profile tab fix.
- [x] 4.3 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, then `./scripts/local_ci.sh`.
- [x] 4.4 Run `openspec validate add-vector-store-label-to-knowledge-base --strict`.
