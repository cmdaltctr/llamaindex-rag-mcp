# Tasks

Start these tasks after `organise-backend-folders` is applied. Route files then live in `src/omrg/transports/api/routes/` (`routes_connections.py` becomes `routes/connections.py`, `routes_mcp.py` becomes `routes/mcp.py`).

Test-first rule for each task that changes behaviour: write the test, run it, see it fail on the current code, then write the code and see it pass.

Line ceiling: `src/omrg/engine.py` has 498 lines and `src/omrg/compose.py` has 428. Put new code in the modules named below. `uv run pytest tests/test_file_size_ceiling.py -q` must pass after each group.

## 1. Preconditions, approval and decision record

- [x] 1.1 Confirm `src/omrg/transports/api/routes/connections.py` and `routes/mcp.py` exist. Verify with `git ls-files src/omrg/transports/api/routes/`.
- [x] 1.2 Check that `studio-profiles-gallery` is merged and its route list includes `#/settings/<section>`. If it is not merged, stop and report, because this change needs that route.
- [x] 1.3 Confirm that no file in `docs/adr/` or `openspec/changes/` claims ADR-083. Use the next free number if it is taken, and update design.md D9.
- [x] 1.4 Write `docs/adr/083-llm-provider-settings-in-the-web-workspace.md` with status Proposed. Record design D1 to D7, the rejected storage options with their reasons, the precedence rule and the list of values that do not apply live. Verify that `docs/adr/ADR_README.md` lists it.
- [x] 1.5 The user chose keychain plus environment override (option 1). Ask the user to approve adding `keyring` to the `web` extra (design D1) before any install. Record the approval in the ADR.
- [x] 1.6 After approval, run `uv add --optional web "keyring>=<locked minor>"` in the feature worktree. Confirm `git rev-parse --show-toplevel` names the worktree first. Verify with `uv run pytest tests/test_dependency_floors.py -q`, confirm the licence is MIT, and confirm that `uv.lock` lists `pywin32-ctypes` with a Windows marker and `SecretStorage` and `jeepney` with a Linux marker.

## 2. Provider descriptors in the registry

- [ ] 2.1 Write `tests/unit/test_llm_connection_descriptors.py`. Assert that `registry.describe_all()` returns `ollama`, `llamacpp`, `openrouter` in registration order, each with display name, locality, fields, `test_targets`, `models_target` and `parse_models`. Assert that a fake provider registered in the test appears with no other change. Run it and see it fail.
- [ ] 2.2 Add a `CONNECTION` descriptor to `src/omrg/core/providers/llm/ollama.py`, `llamacpp.py` and `openrouter.py` (design D5). Use `GET /api/v1/key` as the OpenRouter test target.
- [ ] 2.3 Add `describe_all()` to `src/omrg/core/providers/llm/registry.py`. Verify that test 2.1 passes and `uv run lint-imports` passes.
- [ ] 2.4 Add `parse_models` tests with recorded payloads: Ollama `models[].name`, OpenAI-style `data[].id`, and a malformed payload that returns an empty list. Verify that they pass.

## 3. Value sources and precedence

- [ ] 3.1 Write `tests/unit/test_provider_value_sources.py`. For each editable field, assert the source is `env` when set in the environment, `env` when set in `.env`, and `default` when set only in profile YAML or `defaults.yaml`. Cover the nested `ANSWER__PROVIDER` form. Run it and see it fail.
- [ ] 3.2 Record the explicit sources of the five editable fields in `src/omrg/config/__init__.py`, beside `_explicit_vector_store_sources`. Verify with test 3.1 and `uv run pytest tests/test_config.py -q`.
- [ ] 3.3 Write `tests/unit/test_compose_providers.py`. Assert that `apply_provider_values` keeps a locked field, applies an unlocked saved field, falls back to the default when cleared, applies the Chat choice to `answer.provider` and `answer.model`, and refuses the Ollama address while embeddings use Ollama. Run it and see it fail.
- [ ] 3.4 Create `src/omrg/compose_providers.py` with `ProviderValues`, `apply_provider_values` and `provider_effective_settings`. Re-export from `src/omrg/compose.py`. Verify with test 3.3 and the file size test.
- [ ] 3.5 Write tests in `tests/unit/test_connection_summary.py` for the new entry shape: fields with source, lock, `set`, `last4` (only for keys of 16 or more characters), `state`, plus `read_only`, `installed`, `install_hint`, roles and the top-level `keychain`. Run them and see them fail.
- [ ] 3.6 Rewrite `src/omrg/compose_connections.py` to loop over `describe_all()` with no branch on a provider name. Verify with test 3.5 and `grep -n '== "ollama"\|== "llamacpp"\|== "openrouter"' src/omrg/compose_connections.py` printing nothing.
- [ ] 3.7 Comment out `LLAMACPP_CHAT_URL` in `.env.example` and add one line that says Settings can set it. Verify that the default value in `src/omrg/config/__init__.py` equals the old line.

## 4. Storage of saved values and keys

- [ ] 4.1 Write tests in `tests/unit/test_workspace_settings.py` for the keys `chat.provider`, `chat.model`, `provider.<name>.<field>` and `provider.<name>.key_saved_at`. Assert that an unknown key raises and that a damaged value reads as unset. Run them and see them fail.
- [ ] 4.2 Extend `src/omrg/integrations/workspace_sqlite/settings.py` with the new keys, checked against the allowed set from the descriptors. Update the module docstring that says provider settings stay in `.env`. Verify with test 4.1.
- [ ] 4.3 Write `tests/unit/test_keychain.py` with an in-memory fake backend of priority 5, installed through `keyring.set_keyring` in a fixture, so CI on any operating system is deterministic and never touches a real keychain. Assert save, read and delete under the service `omrg` with the provider name as user name, the `keychain-missing` state, and that `repr` of the store and of `ProviderValues` hides the key. Run it and see it fail.
- [ ] 4.4 Add tests to `tests/unit/test_keychain.py` for "no keychain": `keyring.backends.fail.Keyring`, the null keyring, a chainer with no backends, a fake backend of priority below 1, and a fake backend class whose module is `keyrings.alt.file` (the plaintext refusal), also when `PYTHON_KEYRING_BACKEND` forces it. Assert each reports unavailable and that a save raises and writes nothing through that backend. Run them and see them fail.
- [ ] 4.5 Create `src/omrg/integrations/keychain.py`. Import `keyring` inside functions only, so the base install and the stdio server never import it. Run each call in a worker thread with a time limit. Verify with tests 4.3 and 4.4 and `uv run lint-imports`.
- [ ] 4.6 Write a test that saves a key through the store and then scans every row of the workspace database, every file under the workspace and the working directory `.env` for the key. Assert no match. Run it and see it pass only with the keychain store in place.

## 5. Live provider values in the Engine

- [ ] 5.1 Write `tests/unit/test_engine_provider_update.py`. Assert that after `use_provider_settings(new)` the next answer builds a new model, the next ingest resolves settings with the new key, and the graph judge cache is empty. Assert that an answer waiting on a slow fake model and a graph run already started keep the old values. Assert that a change to an embedding field raises and keeps the old settings. Assert that embedder, store and reranker stay the same objects. Run it and see it fail.
- [ ] 5.2 Create `src/omrg/engine_providers.py` with the generation holder, the embedding-field guard and the answer-model slot. Move `_get_answer_llm` and its fields there. Add `Engine.use_provider_settings()`. Verify with test 5.1, `uv run pytest tests/test_engine.py -q` and the file size test.
- [ ] 5.3 Write tests in `tests/test_compose.py`. Assert that `build_engine(provider_source=...)` still runs the environment safeguards, starts with the saved values, and builds the answer model, the judge and the profile resolver from the values the source returns at build time. Assert that `build_engine()` without the keyword behaves as today. Run them and see them fail.
- [ ] 5.4 Add the `provider_source` keyword to `build_engine` in `src/omrg/compose_engine.py`. Verify with test 5.3.
- [ ] 5.5 Wire the web lifespan in `src/omrg/transports/api/lifespan.py`: read the saved values and the keychain keys after the database is prepared, keep them on `WebRuntime`, and pass a source to the Engine factory. Keep test fakes that take no argument working. Verify with `uv run pytest tests/unit/test_web_lifespan.py -q`.

## 6. Redaction of saved keys

- [ ] 6.1 Write tests in `tests/unit/test_web_logs.py`. Save a key through the key route, log a message that holds it, and assert the buffer, `GET /v1/logs` and the stream show it removed. Repeat with a replaced key. Run them and see them fail.
- [ ] 6.2 Add an append-only `SecretSet` to `src/omrg/transports/api/security.py`. Make `RedactingFilter` and `LogBuffer` (`log_buffer.py`) read it at filter time. Create it in `src/omrg/transports/cli/web.py` with the launch keys and the keychain keys. Verify with test 6.1 and `uv run pytest tests/unit/test_web_security.py -q`.
- [ ] 6.3 Write a test that an answer result whose `error` text holds a saved key comes back from `answerCollection` with the key removed. Run it and see it fail, then redact the `error` field in `src/omrg/transports/api/routes/documents.py`. Verify that it passes.

## 7. Provider routes

- [ ] 7.1 Write tests in `tests/unit/test_web_connections.py` for `PUT /v1/connections/{provider}`: save, clear, 400 bad address (scheme, user info, query, fragment, length), 404 unknown provider or field, 409 locked by `env`, 409 Ollama address while embeddings use Ollama, 403 for a bearer credential, and the next answer using the new address with no restart. Run them and see them fail.
- [ ] 7.2 Add the route to `src/omrg/transports/api/routes/connections.py`. Write the database, update the runtime values, then call `use_provider_settings()`; restore both and return 409 when the Engine refuses. Verify with test 7.1.
- [ ] 7.3 Write tests for `PUT` and `DELETE /v1/connections/{provider}/key`: `credentials` scope, session only, 409 when the key comes from `env`, 409 with no keychain and nothing written, 400 for a bad key without the value in the message. Run them and see them fail. Then add the routes and verify they pass.
- [ ] 7.4 Write a test that every response of the provider and Chat routes holds no five consecutive characters of a saved 64-character key, and that `last4` equals its last four characters. Run it and see it pass.
- [ ] 7.5 Mutation check for the secret rule: patch the summary in the test to return the whole key. Confirm test 7.4 fails. Remove the patch and confirm it passes. Record the result in the PR description.
- [ ] 7.6 Write tests for `POST /v1/connections/{provider}/test` with typed values: a typed address is tested and not saved, a typed key is sent and not saved or logged, a bad typed address gets 400 with no request sent. Use `httpx.MockTransport`. Run them and see them fail. Then extend the route and `connection_probe.py`, and verify they pass.
- [ ] 7.7 Write tests for `POST /v1/connections/{provider}/models`: names only, sorted, at most 1,000 with `truncated`, the 8 MiB read limit, invalid names dropped, failure reasons as the test route. Run them and see them fail. Then add the route and verify they pass.
- [ ] 7.8 Update `src/omrg/transports/api/openapi.yaml` for `getConnections` and the five new operations. Verify with `uv run pytest tests/unit/test_openapi_contract.py -q`.

## 8. Chat settings routes

- [ ] 8.1 Write `tests/unit/test_web_chat_settings.py` for `GET` and `PUT /v1/settings/chat`: sources, lock and 409 naming the variable, 400 unknown provider and bad model name, every `ready` reason, no provider request on `GET`, and the next answer using the saved model with no restart. Run it and see it fail.
- [ ] 8.2 Create `src/omrg/transports/api/routes/chat_settings.py` with both routes and register it in the app. Verify with test 8.1.
- [ ] 8.3 Write tests for `POST /v1/settings/chat/test` with fake LLMs that raise connection, time-out, 401 and 404 errors, return empty text, or return text. Assert the fixed reasons, no reply text, no exception text, and no save. Run them and see them fail. Then add the route and verify they pass.
- [ ] 8.4 Update `openapi.yaml` for `getChatSettings`, `setChatSettings` and `testChatModel`. Verify with the OpenAPI contract test.

## 9. Web client and routes

- [ ] 9.1 `studio-profiles-gallery` already routes `#/settings/<section>` for the old sections. Write tests in `web/src/lib/routes.test.ts` for `#/settings/providers` and `#/settings/chat`. Run them with `cd web && npx vitest run src/lib/routes.test.ts` and see them fail. Then add the two section ids to the list in `web/src/lib/routes.ts` and verify they pass.
- [ ] 9.2 Write tests in `web/src/api/settings.test.ts` and `settingsMutations.test.tsx` for the new shapes and calls. Run them and see them fail. Then extend `web/src/api/settings.ts`, `queries.ts` and `settingsMutations.ts`, and verify they pass.

## 10. Providers section

- [ ] 10.1 Update `web/src/settings/SettingsView.test.tsx` for the seven chips and the route per section. Run it and see it fail. Then update `SettingsView.tsx` and verify it passes.
- [ ] 10.2 Write `web/src/settings/ProvidersSection.test.tsx` with Testing Library: cards from the server list, Local and Cloud badges with text, "Set from environment (read-only here)" with the variable name, save of an address, key input emptied after save with "Key set" and the last four characters, the no-keychain line with no key input, Test with a typed value, the "leaves this machine" line for cloud and for a non-loopback address, and no restart banner. Run it and see it fail.
- [ ] 10.3 Replace `ConnectionsSection.tsx` and `ConnectionCard.tsx` with `ProvidersSection.tsx`, `ProviderCard.tsx`, `ProviderAddressField.tsx`, `ProviderKeyField.tsx` and `ProviderTest.tsx` (design D8). Remove `PROVIDER_NAMES` from `connectionWords.ts`. Verify with test 10.2 and `cd web && npm run lint && npm run typecheck`.

## 11. Chat section

- [ ] 11.1 Write `web/src/settings/ChatSection.test.tsx`: provider select with not-ready reasons, free-text model, List models fills the field without saving, Test result as badge and sentence, Save and Clear, locked state with no Save, cloud statement only for a cloud provider. Query the select with `getByRole("combobox", { name })`. Run it and see it fail.
- [ ] 11.2 Create `ChatSection.tsx` and `ChatModelForm.tsx` in `web/src/settings/`. Verify with test 11.1 and `npm run lint && npm run typecheck`.

## 12. Chat view notice

- [ ] 12.1 Add tests to `web/src/chat/ChatView.test.tsx`: not ready shows one line with a link to `#/settings/chat` and disables Send; reason `disabled` shows the turned-off line; a `generation` failure shows the link beside Retry; no server error text in the DOM. Run them and see them fail.
- [ ] 12.2 Update `ChatView.tsx`, `AssistantTurn.tsx` and `answerStatus.ts`. Verify with test 12.1.

## 13. Documentation

- [ ] 13.1 Update `docs/guides/web-workspace.md`: the route table rows for the changed and new routes, the Settings row, the source order, the keychain, the no-keychain path, how to remove keys from the keychain, and what stdio and the CLI do not see. Verify that every route in the table exists in `openapi.yaml`.
- [ ] 13.2 Update `docs/guides/configuration.md`: "Providers", "Answering" and "Web workspace settings" state the precedence, the lock, the keychain and that saved values apply at once. Verify with `grep -n "read-only\|restart" docs/guides/configuration.md` that no stale statement about provider settings remains.
- [ ] 13.3 Update `web/DESIGN.md` and the screen list in the repository copy of the `omrg-design` skill (`.agents/skills/omrg-design/references/screens.md`) for the Providers and Chat sections. Copy it over the global copy and verify with `diff` that both match.

## 14. Final verification

- [ ] 14.1 Run `uv run pytest -n auto -m "not slow" tests/unit/test_web_connections.py tests/unit/test_web_chat_settings.py tests/unit/test_connection_summary.py tests/unit/test_compose_providers.py tests/unit/test_keychain.py tests/unit/test_engine_provider_update.py tests/unit/test_web_logs.py tests/test_compose.py -q` and `uv run lint-imports`. Verify that both pass.
- [ ] 14.2 Run `cd web && npm run lint && npm run typecheck && npm run test && npm run build`. Verify that all pass.
- [ ] 14.3 Browser check with a throwaway `omrg web` in the session scratch directory and no real key. Open Settings > Providers and Settings > Chat in light and dark at 1280 px and at a 390 px viewport. Confirm no horizontal scroll, every status has text, and no key shows in screenshots or the console. Save the evidence in the PR.
- [ ] 14.4 With Ollama running, choose an Ollama model in Settings > Chat, ask one question in Chat, and confirm the answer uses it with no restart. Mark the step BLOCKED with the reason if no local model is available.
- [ ] 14.5 Check once against the real OpenRouter service, with a key the user supplies, that a wrong key gets `unauthorised` from the Test action. Record whether `GET /api/v1/models` also rejects a wrong key, to close the open question in design.md.
- [ ] 14.6 Manual check on macOS: save a test key through the page, confirm Keychain Access shows it under the service `omrg` with the account `openrouter`, restart `omrg web` and confirm the card still shows "Key set", then remove it through the page and confirm it is gone.
- [ ] 14.7 Optional, if a Windows machine is available: repeat 14.6 on Windows and confirm Credential Manager shows the entry and the removal. Mark the task skipped with the reason if no Windows machine is available.
- [ ] 14.8 Manual check of the no-keychain path: start `omrg web` with `PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring`, confirm the card shows the one-line message naming `OPENROUTER_API_KEY`, and confirm a key in `.env` then works.
- [ ] 14.9 Ask the user, then run `./scripts/local_ci.sh`. Verify that it passes.
- [ ] 14.10 Run `openspec validate add-llm-provider-settings --strict`. Verify that it passes.
