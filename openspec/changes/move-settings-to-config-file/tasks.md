# Tasks

## 1. Prerequisite

- [x] 1.1 Confirm `add-web-power-menu` is merged into `v3` and `POST /v1/server/power` exists; verify with `git log v3 --oneline | grep power-menu` and `grep -n "server/power" src/omrg/transports/api/openapi.yaml`
- [x] 1.2 Create worktree `../llamaindex-rag-mcp-feat-move-settings-to-config-file` on `feat/move-settings-to-config-file` from `v3`; verify `git rev-parse --show-toplevel` and `git branch --show-current`, then run `uv sync --frozen --extra web`

## 2. Read every setting from omrg.jsonc

- [x] 2.1 Write failing tests in `tests/unit/test_settings_file.py` for the naming rule (nested and flat keys), deep merge, comments, and the source order env > dotenv > config-file > YAML > default; confirm they fail
- [x] 2.2 Add `config/settings_file.py` with `UserConfigSource` and wire it into `settings_customise_sources` (move code out of `config/__init__.py` to stay under 500 lines); verify 2.1 passes and `tests/test_file_size_ceiling.py` passes
- [x] 2.3 Record the `dotenv` source by key name from `dotenv_values()` of the loaded `.env`; test that a shell export reports `env` and a `.env` line reports `dotenv`, and that no value is stored
- [x] 2.4 Report problems (broken file, invalid value, unknown key, retired flat name with its replacement from `config/legacy.py`) without values; tests for each scenario in "Problems in omrg.jsonc do not stop the server" and "Unknown and old key names are reported"
- [x] 2.5 Update `compose_providers.locked_fields` so only `env` and `dotenv` lock, keeping the Ollama-embeddings lock; update its tests and confirm a test fails when `config-file` locks again
- [x] 2.6 Document the naming rule, source order and problem list in `docs/guides/configuration.md`; verify the example file in the guide parses with `parse_jsonc`

## 3. Key references

- [x] 3.1 Write failing tests for `file://~/...` expansion, `keychain://<provider>` returned unresolved by `config/`, literal key ignored and never logged, and the implicit `secrets/<provider>.key`
- [x] 3.2 Implement them in `config/user_config.py`; verify 3.1 passes and the existing `tests/unit/test_user_config.py` suite still passes
- [x] 3.3 Add the keychain resolver to `compose_providers` with a lazy `keyring` import; test that the CLI path resolves a fake keychain entry and that no `keyring` import happens without a `keychain://` reference
- [x] 3.4 Run `uv run lint-imports`; verify `config/` imports nothing from `integrations/` and no stale `ignore_imports` entry remains

## 4. Write omrg.jsonc safely

- [x] 4.1 Write failing tests for `config/jsonc_edit.py`: set existing, insert nested, remove with comma, comments and order kept, duplicate key refused; add a property test that random edit sequences keep every comment
- [x] 4.2 Implement `config/jsonc_edit.py`; verify 4.1 passes
- [x] 4.3 Write failing tests for `config/settings_file_write.py`: allowed keys only, revision mismatch gives a conflict, broken file refused, new file mode 0600 and folder 0700, mode kept, atomic replace on a simulated crash, no literal secret accepted
- [x] 4.4 Implement `config/settings_file_write.py`; verify 4.3 passes

## 5. Web server uses the file

- [x] 5.1 Replace the shared `WorkspaceSettings` in `mcp_http.py::McpHttp` (line 109) with a settings-file store, and pass it to `ProviderState` (`provider_state.py:344`); move `routes/chat_settings.py` (own instance, line 97), `routes/mcp.py` (port, upload limit), `lifespan.py::_upload_limit` and the saves of `routes/llamacpp_server.py` onto it; every save route takes and returns `revision`; update their tests to assert the file content after each save
- [x] 5.2 Drop `saved_at` from key fields in `compose_connections.py` (line 199), `openapi.yaml` and `web/src/api/`; verify the OpenAPI conformance tests (`tests/unit/test_web_openapi_conformance*.py`) pass
- [x] 5.3 Key routes write the keychain and the `keychain://` reference, and delete both on Remove; tests for each scenario in "API keys live only in the system keychain" and "Key references and key files do not lock the key field"
- [x] 5.4 Replace `read_saved_web_port` in `transports/cli/web.py` and `web_login_item.py::_target_port` with the file value; tests for every scenario in "The web server listens on a stable port"
- [x] 5.5 Add live reload by file stamp in `ProviderState` and the restart-only snapshot; tests: hand edit of `answer.model` applies on the next request, hand edit of `retrieval.top_k` is reported and not applied
- [x] 5.6 Return the server rule message on every 400 and 409 settings answer without the value; test that no refused value appears in any response body
- [x] 5.7 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`; verify it passes

## 6. Move saved rows out of the database

- [x] 6.1 Write failing tests for `transports/api/settings_handover.py`: rows copied when the file lacks the key, file wins, `key_saved_at` becomes `keychain://`, rows deleted, folder not writable leaves rows and sets the notice, CLI and stdio never call it
- [x] 6.2 Implement the handover and call it from the lifespan before `ProviderState` starts, without growing `lifespan.py` past 500 lines; verify 6.1 passes

## 7. Configuration endpoint

- [x] 7.1 Add `routes/configuration.py` and its `openapi.yaml` entry; tests for masking, `applies`, `restart_pending`, problems and the handover notice; verify the OpenAPI contract test passes

## 8. CLI commands

- [x] 8.1 Write failing tests for `omrg config init` (template parses, sets nothing, covers every `Settings` field, refuses an existing file, `--force` keeps a dated copy) and `omrg config show` (masked keys, stderr only)
- [x] 8.2 Implement `transports/cli/config.py`; verify 8.1 passes and update `docs/guides/cli-reference.md`

## 9. Settings page

- [x] 9.1 Load the `omrg-design` skill; add `SettingRow.tsx` and the source words map with Vitest tests for each source text and the filled Edit input
- [x] 9.2 Move provider cards, the Chat section, the Ollama context window, the llama.cpp panel and Settings › Workspace to `SettingRow`; key fields use the summary row with Replace and Remove; update their tests for every changed scenario in the `workspace-settings` delta
- [x] 9.3 Add `describeSaveError` and use it in Settings forms; test the llama.cpp program rule message and the revision conflict with its Reload action
- [x] 9.4 Add the restart dialog using the power menu routes; tests for login-item, foreground and Later
- [x] 9.5 Add Settings › Configuration from `GET /v1/settings/configuration`; tests for grouping, masking, problems and "Restart to apply"
- [x] 9.6 Run `npm run lint`, `npm run typecheck`, `npm test` and `npm run build` in `web/`; verify all pass

## 10. Login item and docs

- [x] 10.1 Update the `omrg web install` plan text to name `omrg.jsonc`, call `~/.omrg/.env` optional, and suggest `omrg config init`; test the dry-run scenario
- [ ] 10.2 Write ADR-087 "Settings live in omrg.jsonc" and add an ADR-083 addendum that names the replaced rules; update `.env.example`, the root `AGENTS.md` and `src/omrg/AGENTS.md`; verify every `saved` source mention is gone with `grep -rn '"saved"' src web/src docs/guides`

## 11. Integration checks

- [ ] 11.1 Run `./scripts/local_ci.sh`; verify it passes
- [ ] 11.2 Run `openspec validate move-settings-to-config-file --strict` and `openspec validate --all --strict`; verify both pass
- [ ] 11.3 Live check in a throwaway `OMRG_CONFIG_DIR` and workspace: hand-edit then page-save (conflict), save a key (keychain plus reference, key absent from every file), change the port (dialog), break the file (problem shown, server up); check the page at 1280 px and 390 px in light and dark
