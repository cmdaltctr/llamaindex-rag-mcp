# Proposal

## Why

omrg keeps settings in three places: `.env`, a partial `omrg.jsonc` and the `workspace_settings` table of the workspace database. A value can come from any of them, a value in `omrg.jsonc` locks its card, and a card save goes to the database. During demo preparation on 2026-10-19 this made it hard to see which value was in force and why a llama.cpp save failed. OMMS keeps every setting in one `omms.jsonc` that its own page also writes, and that model is easier to reason about.

## What Changes

- `~/.config/omrg/omrg.jsonc` accepts every setting that `.env` accepts, about 35, plus the web settings (port, upload limit, MCP over HTTP). A file key is the environment name in lower case, and `__` nests: `RETRIEVAL__TOP_K` becomes `retrieval.top_k`.
- **BREAKING** The Settings page writes `omrg.jsonc`, as OMMS writes `omms.jsonc`. Only allowed keys are written. Comments are kept. A save is refused when the file changed on disk after the page loaded it.
- **BREAKING** A value in `omrg.jsonc` no longer locks its card. Only the process environment and `.env` lock a field. `.env` stays as a development and CI override.
- **BREAKING** The `workspace_settings` table stops holding settings. On the first start of `omrg web`, saved rows move into `omrg.jsonc` once. The database keeps profiles, pipelines, chats, runs and MCP tokens.
- API keys stay out of `omrg.jsonc`. A key field holds a reference: `env://NAME`, `file://~/.config/omrg/secrets/<name>.key` or `keychain://<provider>`. A key typed on a card goes to the system keychain, and the page writes the `keychain://` reference. `secrets/<provider>.key` still applies without a reference, as in OMMS.
- Every Settings field shows its value and where it came from (`omrg.jsonc`, `.env`, environment, key file, keychain, default). A field with a value never shows an empty input. A set key shows one row with the last four characters, Replace and Remove.
- `omrg web` picks up hand edits of `omrg.jsonc` with no restart for settings that apply at once (provider addresses, keys, Chat choice, context windows, upload limit, MCP over HTTP, llama.cpp server values).
- The web port and the engine settings (embedding, vector store, chunking, ingestion, retrieval, metadata, OCR) apply at the next launch. A page save of the port opens a dialog that offers a restart through the power menu. A hand edit of such a setting shows "Restart to apply" with the same dialog.
- A new Settings › Configuration section lists every setting read-only, with value, source and problems found in the file (unknown key, invalid value, broken file).
- Settings shows the server's reason when a save is refused, for example "The program must be a file named llama-server", in place of "The local server could not complete that request."
- New CLI commands: `omrg config init` writes a commented starter `omrg.jsonc`, and `omrg config show` prints each setting with its value and source.
- The login item reads `omrg.jsonc`. `~/.omrg/.env` becomes optional.
- A new ADR-087 replaces the ADR-083 rules "the app never writes the config folder", "saved values live in the workspace database" and "the config file locks its field".

## Capabilities

### New Capabilities

- `settings-file`: the user config folder and `omrg.jsonc` as the single store of settings: location, key names, source order, secret references, page writes, revision check, live reload, restart-only settings, handover from the database, and the `omrg config` commands.

### Modified Capabilities

- `llm-provider-settings`: provider values and keys take their sources from `omrg.jsonc` and its references. The config file no longer locks. A page key save writes a `keychain://` reference. The CLI and the stdio server see page saves. The read-only folder rule and the old `omrg.jsonc` requirement move to `settings-file`.
- `workspace-settings`: provider, Chat, Ollama and llama.cpp cards show value and source rows, keep no empty inputs for set values, and report sources without `saved`. New requirements for the Configuration section, refused-save reasons and the restart dialog.
- `local-web-workspace`: the web port and the upload limit are stored in `omrg.jsonc`. The "workspace settings live in the workspace database" requirement is removed.
- `mcp-http-transport`: the on/off state is stored in `omrg.jsonc`.
- `llamacpp-server`: server settings use the new sources and do not lock from the config file.
- `config-composition-root`: the precedence order gains `omrg.jsonc` below `.env`.
- `web-login-item`: the login item reads `omrg.jsonc`, and `~/.omrg/.env` is optional.

## Impact

- **Code:** `src/omrg/config/` (full-key reader, JSONC editor, source tracking), `compose_providers.py` (keychain reference resolution, lock rule), `compose_connections.py` (key field without `saved_at`), `transports/api/` (`mcp_http.py`, `provider_state.py`, `app.py`, `lifespan.py::_upload_limit`, routes `chat_settings.py`, `connections.py`, `mcp.py`, `llamacpp_server.py`), `integrations/workspace_sqlite/settings.py` (handover, then no reads), `transports/cli/` (`web.py`, `web_login_item.py`, new `config` group), `web/src/settings/` (row component, Configuration section, restart dialog), `web/src/lib/errors.ts`.
- **API:** field sources drop `saved` and add `dotenv`. Key fields drop `saved_at`. Save routes take and return a `revision`, and answer 409 when the file changed. New `GET /v1/settings/configuration`.
- **Dependencies:** none added. `keyring` stays.
- **Order:** depends on `add-web-power-menu` for the restart dialog. Implement that change first.
- **Docs:** `docs/guides/configuration.md`, `.env.example`, CLI reference, ADR-083 addendum, new ADR-087.
- **Data:** existing `workspace_settings` rows move into `omrg.jsonc` once. Keychain entries stay where they are.
