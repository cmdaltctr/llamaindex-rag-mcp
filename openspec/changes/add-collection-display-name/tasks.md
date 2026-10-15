## 1. Storage check and API (tests first)

- [ ] 1.1 Write a test that stores, overwrites and clears `display_name` through `update_collection_metadata` on LanceDB and, with the `chroma` extra, on Chroma. Record the empty-string result.
- [ ] 1.2 Write failing route tests: set, trim, clear, 81 characters rejected, control characters rejected, bearer credential rejected, unknown collection returns 404 and creates nothing, collection name unaffected.
- [ ] 1.3 Add `display_name` to the `listCollections` response. Treat `""` and a missing key as `null`.
- [ ] 1.4 Add `PATCH /v1/collections/{collection}/display-name` in `routes_admin.py`, with `require_session("manage")`, a `collection_exists` check before the write, and boundary validation.
- [ ] 1.5 Update `openapi.yaml` (`CollectionInfo.display_name`, the new operation with session-only security, 404 and 422 responses). Run `tests/unit/test_web_openapi_conformance*.py`.

## 2. Web

- [ ] 2.1 Add `display_name` to `CollectionInfo` and to every fake server and fixture that builds a collection (`grep -rln "chunk_count" web/src`). Add a `setDisplayName` call in `web/src/api` and a mutation that invalidates the collections query.
- [ ] 2.2 Write failing Vitest tests for `collectionTitle`, then add it.
- [ ] 2.3 Write failing Vitest tests for `DisplayNameEditor` (pencil opens, Enter saves, Escape cancels, empty clears, error stays open, accessible names), then add the component.
- [ ] 2.4 Use `collectionTitle` on the Home card, in `CollectionPicker` and in the `Project.tsx` header. Add the grey `Collection name: <name>` line under the title.
- [ ] 2.5 Run the web type check, lint and Vitest. Check the header at phone width, with an 80-character name, and in light and dark themes.

## 3. Docs, TDR and verification

- [ ] 3.1 Update `docs/guides/web-workspace.md` (Knowledge Base row, the display-name rule, the route and its session-only guard, the confirmation-table row if listed) and any guide that lists the collection fields.
- [ ] 3.2 Write the next TDR after `032` (load `s-tdr`): why the collection name stays fixed, metadata storage, the empty-string rule, the 404 guard, the LanceDB version side effect.
- [ ] 3.3 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, then `./scripts/local_ci.sh`.
- [ ] 3.4 Run `openspec validate add-collection-display-name --strict`.
