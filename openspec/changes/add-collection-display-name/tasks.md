## 1. Storage check and API (tests first)

- [ ] 1.1 Add a round-trip case to `TestCollectionMetadata` in `tests/test_vectordb_contract.py`: store, overwrite and clear (`""`) `display_name`, then read it back. It runs on LanceDB here; the Chroma case runs only in the chroma-extra CI job. Do not create a new Chroma-gated test file.
- [ ] 1.2 Write failing route tests: set, trim, clear, 81 code points gives 400, a control character gives 400, a bearer credential gives 403, an unknown collection gives 404 and creates nothing, the response is `{collection, display_name}`, and the collection name is unaffected.
- [ ] 1.3 Add `display_name` to the `listCollections` response, read from the same metadata read as `profile`. Treat `""` and a missing key as `null`. Extend the unreadable-metadata test so `display_name` is also `null`.
- [ ] 1.4 Add `PATCH /v1/collections/{collection}/display-name` in `routes_admin.py`: `require_session("manage")`, `async with admitted(runtime)`, a `collection_exists` check before the write, and the D3 validation. Widen the module docstring.
- [ ] 1.5 Update `openapi.yaml`: `CollectionInfo.display_name`, the new operation with session-only `manage` security, the `{collection, display_name}` response, and 400, 401, 403 and 404 responses. Run `tests/unit/test_web_openapi_conformance*.py`.

## 2. Web

- [ ] 2.1 Add `display_name` to `CollectionInfo` and to every fake server and fixture that builds a collection (`grep -rln "chunk_count" web/src`). Add a `setDisplayName` call in `web/src/api` and a mutation that invalidates the collections query.
- [ ] 2.2 Write failing Vitest tests for `collectionTitle`, then add it.
- [ ] 2.3 Write failing Vitest tests for `DisplayNameEditor` (pencil opens, Enter saves, Escape cancels, empty clears, 81 code points blocked before send, error stays open, accessible names), then add the component.
- [ ] 2.4 Use `collectionTitle` on the Home card, in `CollectionPicker` (Knowledge Base and Chat) and in the `Project.tsx` header. Add the grey `Collection name: <name>` line under the title. Keep the collection name in "Sources in <name>", the Chat input and the delete dialog. Add a Chat test that shows the display name in the picker.
- [ ] 2.5 Run the web type check, lint and Vitest. Check the header at phone width, with an 80-code-point name, and in light and dark themes.

## 3. Docs, TDR and verification

- [ ] 3.1 Update `docs/guides/web-workspace.md` (Home, Chat and Knowledge Base rows, the display-name rule, where the collection name stays, the route and its session-only guard) and any guide that lists the collection fields.
- [ ] 3.2 Write the next TDR after `032` (load `s-tdr`): why the collection name stays fixed, metadata storage, the empty-string rule, the 404 guard and why it differs from the profile route's 400, the LanceDB version side effect, the pending-collection edge case.
- [ ] 3.3 Re-pin `_BASE_EXECUTED` and, if the new contract case adds a Chroma skip, `_BASE_SKIPPED` in `tests/test_clean_base_tripwire.py`. Compute the effective expectation by importing the module, as in change 1.
- [ ] 3.4 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, then `./scripts/local_ci.sh`.
- [ ] 3.5 Run `openspec validate add-collection-display-name --strict`.
