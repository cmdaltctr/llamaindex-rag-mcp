# ADR-087: Settings Live in omrg.jsonc

- **Date:** 2026-10-19
- **Status:** Accepted
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-083](083-llm-provider-settings-in-the-web-workspace.md) (rules 12 and 13 and part of rule 2 are replaced, see its addendum), [ADR-078](078-upload-limit-as-a-workspace-setting-and-run-artefact-route.md) (the upload limit), [ADR-080](080-profiles-own-pipelines.md) (the web server owns the workspace), [ADR-085](085-web-login-item.md) (the login item), [ADR-086](086-web-power-menu.md) (the restart dialog), [ADR-037](037-architecture-v2-conformance.md) (settings are injected and frozen)
- **Change:** `openspec/changes/move-settings-to-config-file/` (design D1 to D12)
- **Amended by:** [ADR-095](095-page-writes-every-scalar-setting.md) (the keys the page may write; replaces decision 5's "only the keys it edits" and point 1 of the document-reading addendum)

## Context

Settings lived in three places: `.env`, a partial `omrg.jsonc` and the `workspace_settings` table of the workspace database. A value could come from any of them. A value in `omrg.jsonc` locked its card. A card save went to the database. During demo preparation on 2026-10-19 the user could not see which value was in force, and could not see why a llama.cpp save failed.

OMMS keeps every setting in one `omms.jsonc` that its own page also writes. That model is easier to reason about, and the user chose it for omrg.

## Decision

1. **The page writes `omrg.jsonc`, and the database holds no settings** (D1). The file is the store. The Settings page is a second editor of it. A database value that overrides the file was rejected: it hides a hand edit behind an older page save.
2. **One naming rule** (D2). A file key is the environment name in lower case, and `__` nests one level. `RETRIEVAL__TOP_K` is `retrieval.top_k`. `web_port` and `mcp_http_enabled` have no environment name. `web_max_upload_mib` keeps `WEB_MAX_UPLOAD_MIB` as a launch twin. `omrg config init` builds its template from the `Settings` model, so the docs need no mapping table and the template cannot drift.
3. **Source order** (D3). From highest: an explicit option, the process environment (`env`), `.env` (`dotenv`), `omrg.jsonc` (`config-file`), the YAML defaults and profile bundle, the code default (`default`). Only `env` and `dotenv` lock a field. A value in `omrg.jsonc` does not lock. A `UserConfigSource` in `config/settings_file.py` supplies the file values and records the source of each field. `.env` keys are told apart from process keys by their names, never their values.
4. **A small in-house JSONC editor** (D4). `config/jsonc_edit.py` replaces one value span, inserts one member or removes one member, and leaves every other byte alone. Comments and key order stay. No new dependency.
5. **Safe writes** (D5). The page may write only the keys it edits. Each read returns a revision (SHA-256 of the file). A save with an old revision gets 409 and writes nothing. A broken file is never written. The write goes to a temporary file, then `os.replace`. A new file has mode 0600 and a new folder 0700. Only `omrg web` writes the file (gotcha 17).
6. **Keys stay out of the file** (D6). A key field holds `env://NAME`, `file://~/.config/omrg/secrets/<name>.key` or `keychain://<provider>`. A key typed on a card goes to the system keychain, and the page writes the `keychain://` reference. `secrets/<provider>.key` still applies without a reference. The composition root resolves `keychain://`, so the web server, the CLI and the stdio server see the same key. `keyring` is imported only when a `keychain://` reference exists. `config/` stays a leaf.
7. **Live reload by file stamp** (D7). Before a request that reads settings, `ProviderState` compares the `(mtime_ns, size, inode)` of the file with the last read, and re-reads on a change. Provider addresses and keys, the Chat choice, context windows, llama.cpp server values, the upload limit and MCP on/off apply at once. The web port and the engine settings apply at the next launch, because `EffectiveSettings` stays frozen (ADR-037). A hand edit of such a key shows "Restart to apply".
8. **One handover from the database** (D8). On the first start of `omrg web`, each saved row moves into `omrg.jsonc` where the file lacks the key. A saved key becomes a `keychain://` reference. The copied rows are deleted. The table stays, so an older build still opens the database. If the write fails, the rows stay and the next start retries. The CLI and the stdio server never touch the rows.
9. **The page shows the source and the reason** (D9, D10, D12). One `SettingRow` component shows the value, its source and Edit. `GET /v1/settings/configuration` lists every setting read-only with value, source, `applies` and problems. A refused save shows the server's reason. A save of a restart-only key opens a dialog that offers a restart through the power menu.
10. **`omrg config init` and `omrg config show`** (D11). `init` writes a starter file with every setting commented out. `show` prints each setting, its source and the problems, with keys masked.
11. **The login item reads `omrg.jsonc`** (ADR-085 follow-up). `~/.omrg/.env` becomes optional and overrides the file. The `omrg web install` plan names the file path and suggests `omrg config init`.

## Consequences

### Positive

- One file holds every setting. A text editor and the page edit the same file, and each sees the other's change.
- The page shows where each value comes from. A set value never shows an empty input.
- The CLI and the stdio server see page saves, because they read the same file and resolve the same references.
- Hand edits apply with no restart for most settings.
- The database holds profiles, pipelines, chats, runs and MCP tokens, and no settings.

### Negative

- The page can now change a file the user owns. The revision check and the atomic write limit the risk.
- The CLI can now read the keychain, and macOS may ask the user to allow access for the Python binary. A `file://` or `env://` reference avoids the prompt.
- A rollback to an older build loses page saves that moved out of the database. The older build still reads the nine keys it knew, now as locked values.
- A user who set a value in both `omrg.jsonc` and `.env` for a new key sees no change, because `.env` wins. For the nine shared keys `.env` already won.
- An invalid value in the file is ignored, not fatal. A typo in `embed_provider` falls back to the default embedder. The problem list and `omrg config show` name it, and the embedding stamp guard (ADR-051) refuses a collection built with another model.

### Neutral

- `.env` stays for CI, tests and worktrees.
- Engine settings are read-only on the page. A later change can add edit rows with the same writer and row component.
- No new dependency. `keyring` stays in the `web` extra.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Database values override the file, with a Reset button** | Two stores again. A hand edit is hidden by an older page save. The user rejected it on 2026-10-19. |
| **The file locks its field (status quo)** | The page cannot edit what the file sets, so the cards are read-only for the values the user cares about. |
| **`json5` or `commentjson`** | They parse JSONC but write plain JSON, which drops comments. |
| **Rewrite the whole file from a dict** | It drops comments. OMMS avoids this with `jsonc-parser` `modify`, which has no Python port. |
| **A watcher thread for live reload** | It adds a thread and platform differences. A stat per request costs microseconds. |
| **Apply engine settings without a restart** | `EffectiveSettings` is frozen per launch (ADR-037). |
| **A cross-process file lock** | Only `omrg web` writes the file (gotcha 17). |
| **Drop the `workspace_settings` table at handover** | A schema migration would destroy data and block an older build. |
| **Remove `.env` support** | CI, tests and worktrees depend on it. |
| **Do nothing** | Three stores stay, and the user cannot tell which value is in force. |

## References

- `openspec/changes/move-settings-to-config-file/` (proposal, design D1 to D12, specs, tasks)
- `src/omrg/config/` (`user_config.py`, `settings_file.py`, `jsonc_edit.py`, `settings_file_write.py`)
- `src/omrg/compose_providers.py` (locking and keychain references)
- `src/omrg/transports/cli/config.py` and `src/omrg/transports/cli/config_template.py` (`omrg config`)
- `src/omrg/transports/api/settings_handover.py` and `src/omrg/transports/api/routes/configuration.py`
- `docs/guides/configuration.md`, `docs/guides/cli-reference.md`, `.env.example`

## Addendum (2026-10-20): Profile Levers and Key Precedence

On 2026-10-20 the live app moved to `omrg.jsonc`. All 34 keys in `~/.omrg/.env` moved to the file. The OpenRouter key moved to `~/.config/omrg/secrets/openrouter.key`, with a `file://` reference. Then `~/.omrg/.env` was removed. The move and a code check found two facts that decision 3 does not state.

1. **A collection's profile replaces the profile levers of `omrg.jsonc`.** Decision 3 gives the order of the server settings. Each collection operation then resolves its profile (`_bundle_to_effective` in `core/profiles/resolver.py`). For the five levers `retrieval.top_k`, `retrieval.rerank_enabled`, `retrieval.hybrid_enabled`, `chunking.strategy_fallback` and `metadata.taxonomy_mode`, the resolver reads the process environment, then the profile bundle, then a fixed fallback. It never reads the server value. `.env` is loaded into the process environment at startup, so it counts as environment.
   - A lever in `.env` or the environment overrides every profile, with no warning.
   - A lever in `omrg.jsonc` changes no search and no ingest. `omrg config show` and the Settings page still show it with source `config-file`, so it looks in force. A check with `retrieval.top_k: 5` in the file gave a server value of 5, but 10 for `documents` and 20 for `codebase`.
   - `ingestion.ingest_extensions` and the three `answer.verify_*` fields are different. The resolver uses the server value when the bundle does not set the field, so a file value applies there.
   - **Rule:** keep the five levers out of `omrg.jsonc` and `.env`. Change a lever in the profile, or with an environment variable for one command. The live migration followed this rule.
2. **A shell key outranks the key file.** An `OPENROUTER_API_KEY` exported in a shell (for example in `~/.zshrc`) is `env`. It wins over the `file://` reference in each process that starts from that shell. The login item does not read `~/.zshrc`. The CLI and the web app can then use different keys. Remove the export to make every process use the key file.

## Addendum (2026-10-20): Document Reading Keys Become Page-Editable

Change: `openspec/changes/archive/2026-10-20-document-reading-settings/` (design D1 to D11). Neutral consequence 2 said that a later change can add edit rows for engine settings. This change adds rows for nine keys in Settings > Document reading: `pdf_reader`, `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`.

1. **The page writes the nine keys through the same writer.** `ALLOWED_KEYS` grows from 16 to 25 keys. A dedicated route pair, `GET` and `PUT /v1/settings/document-reading`, accepts only these nine keys. A generic write route for every setting was rejected, because each setting has its own restart and identity effects.
2. **Each key applies at the next launch only.** Decision 7 still holds: `EffectiveSettings` stays frozen (ADR-037). A save leaves the value in force unchanged and marks the row "Restart to apply". The page then offers the restart dialog (ADR-086). Each key is part of the index identity, so the next ingest after the restart can read existing files again.
3. **Write-time checks, with startup behaviour unchanged.** A page write checks the strict JSON type, the five reader names (`auto`, `liteparse`, `pdf_inspector`, `pypdfium2`, `pypdf`), the engine folder-name rule (at most 64 characters) and the `document` or `page` unit. It refuses blank text, because the writer reads blank as "remove the key". `null` removes the key. The route also refuses a PDF reader that is not installed, and allows an engine that is valid but not provisioned. Startup reading does not change: an unknown `pdf_reader` from any source still warns and falls back to `auto`, and an uninstalled reader still resolves to `pypdf`.
4. **Locks follow decision 3.** A key from the environment or `.env` is read-only, and a write that names it gets 409.
5. **"No fallback engine" is deferred.** The page cannot set `ocr_engine_fallback` to empty, because the writer removes a blank key. A later change can add an explicit value with its own rule in `integrations/ocr_worker/routes.py`. Until then, `OCR_ENGINE_FALLBACK=` in `.env` turns the fallback route off.
