## Context

See proposal.md (Why). Facts that shape the approach, first found with graphify and then checked line by line with grep and ast-grep against `v3` at `a1c9bcc`:

- `config/user_config.py` (356 lines) reads `omrg.jsonc` for provider keys only (`_ADDRESS_KEYS`, `_TEXT_KEYS`, `_SECRET_KEYS`, the context-window and idle-sleep integers, and `answer.provider` / `answer.model`) and `secrets/<provider>.key`. `config/provider_sources.py::ProviderSourceMixin._record_provider_sources` records which fields came from the file. `compose_providers.locked_fields` locks a field from `config-file` or the environment, and keeps the ADR-083 rule that the Ollama address is fixed while Ollama makes embeddings.
- `integrations/workspace_sqlite/settings.py::WorkspaceSettings` holds the saved rows. `mcp_http.py::McpHttp` builds the one shared instance (`mcp_http.py:109`), and `ProviderState` is built from `mcp_http.settings` (`provider_state.py:344`). Other readers: `routes/chat_settings.py` (its own instance, line 97), `routes/mcp.py` (port, upload limit), `transports/api/lifespan.py::_upload_limit` (the limit at start), `transports/cli/web.py:309` and `transports/cli/web_login_item.py:79` (both `read_saved_web_port`). `routes/llamacpp_server.py` saves through `ProviderState`.
- `compose_connections.py` sends `key_saved_at` to the page as the `saved_at` field of each key (line 199).
- `integrations/keychain.py` is imported only by `transports/api/`: `app.py` builds the `KeychainStore` (line 148), and `provider_state.py` and `routes/connections.py` use it. `keyring` is imported only inside `keychain.py`. The CLI and the stdio server never read the keychain today.
- `config/__init__.py`, `transports/api/lifespan.py` are at 500 lines and `transports/cli/web_login_item.py` is at 497. New code goes in new files.
- The restart dialog needs `POST /v1/server/power` from `add-web-power-menu`, which is implemented first.

## Goals / Non-Goals

**Goals:**

- One file holds every setting. The page and a text editor edit the same file, and each sees the other's change.
- No setting value lives in the workspace database.
- The source of every value is visible on the page and in `omrg config show`.

**Non-Goals:**

- Editing engine settings (embedding, vector store, chunking, retrieval, metadata, OCR) on the page. The Configuration section lists them read-only; the file is the editor. A later change can add edit rows, because the writer and the row component will exist.
- Applying engine settings without a restart. `EffectiveSettings` stays frozen per launch (ADR-037).
- Removing `.env` support. CI, tests and worktrees depend on it.
- A cross-process file lock. Only `omrg web` writes the file (gotcha 17: the web server owns the workspace).

## Decisions

### D1. The page writes `omrg.jsonc`; the database holds no settings

The OMMS model: the file is the store, and the page is a second editor of it. Alternatives:
- **Database values override the file, with a Reset button.** Two stores again. A hand edit is hidden by an older page save. Rejected by the user on 2026-10-19.
- **File locks its field (status quo).** The page cannot edit what the file sets, so the cards are read-only for exactly the values the user cares about.

### D2. One naming rule for file keys

File key = environment name in lower case, `__` nests one level. `RETRIEVAL__TOP_K` → `retrieval.top_k`, `EMBED_PROVIDER` → `embed_provider`, `ANSWER__MODEL` → `answer.model`. Every key the file accepts today (for example `ollama_base_url`, `llamacpp_server_binary`, `ollama_context_window`, `answer.model`) already follows it, so existing files keep working. `web_port` and `mcp_http_enabled` have no environment twin and are file-only. `web_max_upload_mib` keeps its `WEB_MAX_UPLOAD_MIB` launch twin, which locks. One rule means the docs need no mapping table, and `omrg config init` derives the template from the `Settings` model, so it cannot drift.

### D3. Source order and the `dotenv` source

A new pydantic-settings source, `UserConfigSource`, in a new `config/settings_file.py`, sits between the `.env` source and the YAML sources in `settings_customise_sources`. It deep-merges like the YAML source. It records provenance for every field it supplies. `.env` keys are told apart from process environment keys by reading `dotenv_values()` of the same path that `load_dotenv(find_dotenv(usecwd=True))` loads, once at import, and keeping the key names (never the values). Only `env` and `dotenv` lock.

### D4. A small in-house JSONC editor, no new dependency

`config/jsonc_edit.py` reuses the tokeniser behind `parse_jsonc` and offers `set_value(text, path, value)` and `remove_value(text, path)`. It replaces the value span of an existing member, inserts a new member before the closing brace of its object (creating a nested object when needed), and removes a member with its comma. All other bytes stay. Alternatives:
- `json5` / `commentjson`: they parse JSONC but write plain JSON, which drops comments.
- Rewriting the whole file from a dict: drops comments. OMMS avoids this with `jsonc-parser` `modify`, which has no Python port.
The editor is about 150 lines with property-style tests (round trip of random edits keeps every comment).

### D5. Writes: allowed keys, revision, atomic replace

`config/settings_file_write.py` holds the allowed-key list (the fields the page edits), the revision (SHA-256 of the file bytes, or `absent`), and the write: re-read, compare revision, edit, write `omrg.jsonc.tmp` with the original mode (0600 for a new file), `fsync`, `os.replace`. A `threading.Lock` serialises writes inside the process. A broken file is never written (409). The page never writes `secrets/` or `.env`.

### D6. Keychain references resolve at the composition root

`config/` stays a leaf: it returns a `keychain://<provider>` reference unresolved. `compose_providers` gains a resolver that calls `integrations/keychain.py`, so the web server, the CLI and the stdio server resolve the same reference. `keyring` is imported only when a `keychain://` reference exists, so a CLI run without one pays no import cost and sees no keychain prompt. `ProviderState` stops loading the keychain itself and reads through the resolver.

### D7. Live reload by file stamp; restart-only keys by snapshot

Before a request that reads settings, `ProviderState` compares `(st_mtime_ns, st_size, st_ino)` of `omrg.jsonc` with the last read. On a change it re-parses and swaps the live values (provider addresses, keys, Chat choice, context windows, llama.cpp server values, upload limit, MCP on/off) under its existing lock. No watcher thread. At launch the server keeps a snapshot of the restart-only values. `GET /v1/settings/configuration` compares the current file with the snapshot and marks each difference "Restart to apply". A stat per request costs microseconds. A watcher would add a thread and platform differences for no visible gain.

### D8. Handover from the database once, without dropping the table

A new `transports/api/settings_handover.py` runs in the web lifespan before `ProviderState` starts. It reads the rows through `WorkspaceSettings`, writes each valid row the file does not set, adds `keychain://<provider>` for each `key_saved_at` row whose keychain entry exists, then deletes the copied rows. The table stays (empty) so no schema migration destroys data, and an older build still opens the database. A later release can drop it. If the write fails, the rows stay and are retried at the next start. The CLI and stdio server never touch the rows (gotcha 17).

### D9. One row component on the page

`web/src/settings/SettingRow.tsx` renders label, value, source text and Edit (or Replace and Remove for keys). Provider cards, the Chat section, the llama.cpp panel and Settings › Workspace use it. The source words come from one map in `connectionWords.ts`. `describeError` keeps its generic text for other pages. A new `describeSaveError` shows the server message for 400 and 409 when the body has one. Settings forms use it.

### D10. Configuration endpoint

`GET /v1/settings/configuration` (read scope) returns `{ path, revision, settings: [{ key, value, source, applies: "live" | "restart", restart_pending }], problems: [{ key, kind, message }], handover: { pending, folder } }`. Secret values are `null` with `last4`. It lives in a new `routes/configuration.py` and is added to `openapi.yaml`.

### D11. `omrg config` commands

`transports/cli/config.py` adds `init` (template built from the `Settings` model and `config/defaults.yaml`, every line commented, `--force` keeps `omrg.jsonc.<date>.bak`) and `show` (stderr, keys masked). Both are thin and call `config/`.

### D12. Restart dialog through the power menu

After a save whose key is restart-only, the page opens a dialog. "Restart now" posts the power menu restart. When `GET /v1/server/power` says the app runs in a terminal, the dialog shows the command instead. The only restart-only field the page edits is the web port, but the dialog takes any key, so the Configuration section reuses it.

## Risks / Trade-offs

- [The CLI now reads the keychain, and macOS may ask the user to allow access for the Python binary] → Import `keyring` only when a `keychain://` reference exists; document the prompt; `file://` or `env://` avoids it.
- [A hand edit and a page save race within the same second] → The revision is a content hash, not a time stamp, so any byte change is caught. The write re-reads the file inside the lock.
- [The JSONC editor mis-edits an unusual file (duplicate keys, deep nesting)] → Refuse with 409 when the target key appears twice; property tests over generated files; the original stays untouched on any error because the write is atomic.
- [Invalid file values are ignored, not fatal, so a typo in `embed_provider` falls back to the default embedder] → The problem list and `omrg config show` name it; the embedding stamp guard (ADR-051) refuses a collection built with another model.
- [Rollback to an older build loses page saves that moved out of the database] → The older build still reads the 9 keys it knew from `omrg.jsonc`, now as locked values. Release notes say so.
- [Settings source order changes for users who set a value in both `omrg.jsonc` and `.env`] → `.env` already won for the 9 shared keys; for the new keys there was no file value before.

## Migration Plan

1. Merge `add-web-power-menu`.
2. Ship this change. On the first `omrg web` start, the handover moves database rows into `omrg.jsonc` (D8).
3. Users of `~/.omrg/.env` can run `omrg config init`, copy values across, and delete the `.env`. Nothing forces this.
4. Rollback: install the previous version. Settings that the old version reads from the file still apply.
