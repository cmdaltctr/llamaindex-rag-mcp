# Spec Delta

## Purpose

Keep every omrg setting in one user file, `omrg.jsonc`, that people edit by hand and the Settings page also writes, with API keys held only as references to the environment, a key file or the system keychain.

## ADDED Requirements

### Requirement: The user config folder location

The web server, the CLI and the stdio MCP server SHALL read the user config folder: `$OMRG_CONFIG_DIR` when set, else `$XDG_CONFIG_HOME/omrg` when set, else `~/.config/omrg`. The folder MAY hold `omrg.jsonc` and `secrets/<name>.key`. A missing folder or file SHALL give no values and no warning.

#### Scenario: Folder from OMRG_CONFIG_DIR

- **WHEN** `OMRG_CONFIG_DIR` names a folder that holds `omrg.jsonc` and `XDG_CONFIG_HOME` is also set
- **THEN** every process MUST read `omrg.jsonc` from the `OMRG_CONFIG_DIR` folder

#### Scenario: Folder from XDG_CONFIG_HOME

- **WHEN** `OMRG_CONFIG_DIR` is not set and `XDG_CONFIG_HOME` names a folder
- **THEN** every process MUST read the `omrg` subfolder of it

#### Scenario: Default folder

- **WHEN** neither variable is set
- **THEN** every process MUST read `~/.config/omrg`

#### Scenario: Missing folder

- **WHEN** the folder does not exist and `omrg web` starts
- **THEN** the server MUST start with defaults and MUST log no warning

### Requirement: omrg.jsonc accepts every setting

`omrg.jsonc` SHALL accept JSON with comments and trailing commas. It SHALL accept every setting that the environment accepts. The file key SHALL be the environment name in lower case, and `__` SHALL nest one level, so `RETRIEVAL__TOP_K` is `retrieval.top_k` and `EMBED_PROVIDER` is `embed_provider`. It SHALL also accept `web_port`, `web_max_upload_mib` and `mcp_http_enabled`.

#### Scenario: Nested setting

- **WHEN** `omrg.jsonc` holds `{ "retrieval": { "top_k": 7 } }` and no environment value sets `RETRIEVAL__TOP_K`
- **THEN** a search MUST use 7 results and `omrg config show` MUST report `retrieval.top_k` as 7 from `omrg.jsonc`

#### Scenario: Flat setting

- **WHEN** `omrg.jsonc` holds `"embed_provider": "local"` and `"local_backend": "ollama"`
- **THEN** the engine MUST embed through Ollama

#### Scenario: Comments and trailing commas

- **WHEN** `omrg.jsonc` holds comments and a trailing comma and is otherwise valid
- **THEN** every process MUST read its values

### Requirement: Settings follow one source order

Each setting SHALL come from the first of these sources, highest first: an explicit per-operation option or launch option, the process environment (`env`), the `.env` file (`dotenv`), `omrg.jsonc` (`config-file`), the YAML defaults and profile bundle, then the code default (`default`). A value from `env` or `dotenv` SHALL lock its field in the Settings page. A value from `config-file` SHALL NOT lock its field.

#### Scenario: .env wins over the file

- **WHEN** `.env` sets `LLAMACPP_CHAT_URL` and `omrg.jsonc` sets `llamacpp_chat_url` to another address
- **THEN** the `.env` address MUST be used and the field MUST report the source `dotenv`

#### Scenario: Process environment named apart from .env

- **WHEN** the shell exports `OLLAMA_BASE_URL` and `.env` does not set it
- **THEN** the field MUST report the source `env`

#### Scenario: File value stays editable

- **WHEN** `omrg.jsonc` sets `ollama_base_url` and neither the environment nor `.env` sets it
- **THEN** the field MUST report the source `config-file` and a page save MUST succeed

### Requirement: Problems in omrg.jsonc do not stop the server

A file that cannot be parsed SHALL give no values. A value that fails its rule SHALL be ignored, and the next source SHALL apply. Each problem SHALL be logged once and listed in `GET /v1/settings/configuration` by key, never by value. The server SHALL start.

#### Scenario: Broken file

- **WHEN** `omrg.jsonc` is not valid JSONC and `omrg web` starts
- **THEN** the server MUST start with no values from the file, MUST log one warning and MUST list the problem "omrg.jsonc could not be read"

#### Scenario: Invalid value

- **WHEN** `omrg.jsonc` sets `retrieval.top_k` to `"many"`
- **THEN** the default MUST apply and the problem list MUST name `retrieval.top_k` and its rule

#### Scenario: Invalid address

- **WHEN** `omrg.jsonc` sets `ollama_base_url` to `file:///etc/passwd`
- **THEN** the value MUST be ignored and the warning MUST name the field and not the value

### Requirement: Unknown and old key names are reported

A key that names no setting SHALL be ignored and listed as unknown. A key that matches a retired flat environment name SHALL be ignored and listed with the nested key that replaced it.

#### Scenario: Typo

- **WHEN** `omrg.jsonc` holds `"retreival": { "top_k": 5 }`
- **THEN** the problem list MUST name `retreival` as unknown and the default top-k MUST apply

#### Scenario: Old flat name

- **WHEN** `omrg.jsonc` holds `"top_k": 5`
- **THEN** the problem list MUST name `top_k` and the replacement `retrieval.top_k`

### Requirement: Key fields hold references only

A secret field in `omrg.jsonc` SHALL hold one of: `env://NAME`, `file://<path inside secrets/>` (a leading `~` expands to the home folder), or `keychain://<provider>`. A literal key SHALL be ignored and logged once by field name. A `file://` path that resolves outside `secrets/`, after links, SHALL be refused.

#### Scenario: env reference

- **WHEN** `openrouter_api_key` is `env://MY_ROUTER_KEY` and that variable holds a key
- **THEN** the OpenRouter key MUST be used and the field MUST report the source `config-file`

#### Scenario: OMMS-style file reference

- **WHEN** `openrouter_api_key` is `file://~/.config/omrg/secrets/openrouter.key` and the file holds a key
- **THEN** the key MUST be used and the field MUST report the source `key-file` with that path

#### Scenario: Literal key

- **WHEN** `openrouter_api_key` holds `sk-or-123456`
- **THEN** no key MUST come from the file, and the log and problem list MUST name the field and MUST NOT contain the value

#### Scenario: Path outside secrets

- **WHEN** a reference is `file:///etc/passwd` or uses `..` to leave `secrets/`
- **THEN** the file MUST NOT be read and the problem list MUST name the field

### Requirement: A key file applies without a reference

When `omrg.jsonc` holds no reference for a provider key and no environment value sets it, the key in `secrets/<provider>.key` SHALL apply. Key files SHALL keep the existing safety rules: at most 4 KiB, a regular file, a warning when looser than mode 0600.

#### Scenario: Implicit key file

- **WHEN** `secrets/openrouter.key` holds a key and nothing else sets the OpenRouter key
- **THEN** the key MUST be used and the field MUST report the source `key-file` with the file path

#### Scenario: Reference wins over the implicit file

- **WHEN** `secrets/openrouter.key` exists and `omrg.jsonc` sets `openrouter_api_key` to `keychain://openrouter`
- **THEN** the keychain key MUST be used

### Requirement: Every process resolves keychain references

A `keychain://<provider>` reference SHALL read the system keychain entry with service `omrg` and the provider as user name, in the web server, the CLI and the stdio MCP server. When no usable keychain exists or the entry is missing, the field SHALL have no key and SHALL say why.

#### Scenario: CLI uses a key saved on the page

- **WHEN** a key was saved on the Settings page and the user runs a CLI command that needs that provider
- **THEN** the CLI MUST use the keychain key

#### Scenario: Entry missing

- **WHEN** `omrg.jsonc` holds `keychain://openrouter` and the keychain has no such entry
- **THEN** the field MUST report "Missing from the system keychain" and the provider MUST have no key

### Requirement: The Settings page writes omrg.jsonc

A save from the Settings page SHALL write the value into `omrg.jsonc` and SHALL NOT write the workspace database. Only keys that the page edits SHALL be writable. When the folder or file is missing, the server SHALL create the folder with mode 0700 and the file with mode 0600 and a header comment. A write SHALL go to a temporary file that replaces the original, and SHALL keep the original mode.

#### Scenario: First save creates the file

- **WHEN** no `omrg.jsonc` exists and the user saves an Ollama address
- **THEN** the file MUST exist with mode 0600, MUST hold `ollama_base_url`, and the field MUST report the source `config-file`

#### Scenario: Key outside the allowed list

- **WHEN** a request asks the server to write `embed_provider`
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Broken file is not overwritten

- **WHEN** `omrg.jsonc` is not valid JSONC and the user saves a field on the page
- **THEN** the server MUST answer 409 with "omrg.jsonc could not be read. Fix it, then save again." and MUST NOT change the file

#### Scenario: Interrupted write

- **WHEN** the server stops during a save
- **THEN** `omrg.jsonc` MUST hold either the old or the new content, never a partial file

### Requirement: A page save keeps the rest of the file

A write SHALL change only the saved key. Comments, key order, formatting of other members and keys the page does not edit SHALL stay as they were. Clearing a value SHALL remove its member.

#### Scenario: Comments kept

- **WHEN** `omrg.jsonc` holds comments and `retrieval.top_k`, and the user saves the Chat model
- **THEN** the comments and `retrieval.top_k` MUST be unchanged and `answer.model` MUST hold the new model

#### Scenario: Clear a value

- **WHEN** the user returns the Ollama context window to the default
- **THEN** `ollama_context_window` MUST no longer be in the file and the field MUST report the source `default`

### Requirement: A page save never overwrites a hand edit

Each settings read SHALL return a revision of `omrg.jsonc`. A save SHALL carry that revision. When the file changed after that revision, the server SHALL answer 409 with "omrg.jsonc changed on disk. Reload to see the new values." and SHALL NOT write.

#### Scenario: File edited while the page is open

- **WHEN** the user opens Settings, edits `omrg.jsonc` in an editor, then saves a field on the page
- **THEN** the server MUST answer 409, the editor's change MUST stay in the file, and the page MUST show the 409 message

### Requirement: The page never writes a key into a file

The server SHALL write only references into `omrg.jsonc`. It SHALL NOT write, create or delete `.env`, any file in `secrets/`, or a literal key anywhere.

#### Scenario: Key saved on the page

- **WHEN** the user saves an OpenRouter key on the page
- **THEN** `omrg.jsonc` MUST hold `"openrouter_api_key": "keychain://openrouter"` and no file under the config folder or the workspace MUST contain the key

### Requirement: Hand edits apply without a restart

`omrg web` SHALL notice a change to `omrg.jsonc` before it serves the next request that reads settings. Settings that apply at once SHALL use the new value from that request on: provider addresses, provider keys, the Chat provider and model, context windows, llama.cpp server values, `web_max_upload_mib` and `mcp_http_enabled`. The CLI and the stdio MCP server SHALL read the file at launch.

#### Scenario: Edit the Chat model by hand

- **WHEN** `omrg web` runs and the user changes `answer.model` in `omrg.jsonc`
- **THEN** the next answer MUST use the new model with no restart, and Settings MUST show it from `omrg.jsonc`

#### Scenario: Edit the upload limit by hand

- **WHEN** the user sets `web_max_upload_mib` to 200 in the file while the server runs
- **THEN** the next upload MUST be checked against 200 MiB

### Requirement: Some settings apply only after a restart

`web_port` and the engine settings (embedding, vector store, chunking, ingestion, retrieval, metadata, OCR and the other `answer` members) SHALL apply at the next launch of the process. `omrg web` SHALL keep the values it started with and SHALL report each such key whose file value differs from it.

#### Scenario: Edit top-k by hand

- **WHEN** `omrg web` runs and the user changes `retrieval.top_k` in `omrg.jsonc`
- **THEN** searches MUST keep the launch value, and `GET /v1/settings/configuration` MUST list `retrieval.top_k` as "Restart to apply"

#### Scenario: Embedding model changed by hand

- **WHEN** the user changes `embed_model` and restarts, and a collection holds vectors from the old model
- **THEN** a search of that collection MUST fail with the existing embedding-stamp message and MUST NOT mix vectors

### Requirement: Saved settings move out of the workspace database

When `omrg web` opens a workspace whose database still holds settings rows, it SHALL copy each valid row into `omrg.jsonc` where the file does not set that key, SHALL add `keychain://<provider>` for each provider whose saved key is in the keychain, and SHALL then delete the copied rows. When the file cannot be written, the rows SHALL stay, SHALL NOT be used, and Settings SHALL say so.

#### Scenario: Saved port moves

- **WHEN** the database holds `web_port` 9100 and `omrg.jsonc` does not set `web_port`
- **THEN** after the start `omrg.jsonc` MUST hold `"web_port": 9100` and the database MUST hold no settings rows

#### Scenario: File value wins

- **WHEN** the database holds an Ollama address and `omrg.jsonc` already sets `ollama_base_url`
- **THEN** the file value MUST stay and the row MUST be deleted

#### Scenario: Folder not writable

- **WHEN** the config folder cannot be written
- **THEN** the server MUST start, the rows MUST stay, and Settings MUST show "Saved settings could not be moved to omrg.jsonc" with the folder path

#### Scenario: Other processes do not move rows

- **WHEN** the CLI or the stdio MCP server starts
- **THEN** it MUST NOT read or delete settings rows

### Requirement: omrg config init writes a starter file

`omrg config init` SHALL write `omrg.jsonc` in the user config folder with every setting as a commented line that shows its default and its environment name, and SHALL create the folder with mode 0700 and the file with mode 0600. It SHALL refuse with exit code 1 when the file exists, unless `--force` is given, which SHALL keep a dated copy of the old file.

#### Scenario: New file

- **WHEN** no `omrg.jsonc` exists and the user runs `omrg config init`
- **THEN** the file MUST exist, MUST parse, and MUST set no value

#### Scenario: Existing file

- **WHEN** `omrg.jsonc` exists and the user runs `omrg config init`
- **THEN** the command MUST exit with code 1, MUST name the file, and MUST NOT change it

### Requirement: omrg config show prints each setting and its source

`omrg config show` SHALL print each setting with its value and its source, and SHALL list the problems found in `omrg.jsonc`. A key SHALL show at most "set", the last four characters and the source. Output SHALL go to stderr.

#### Scenario: Key masked

- **WHEN** the OpenRouter key comes from `secrets/openrouter.key`
- **THEN** the line MUST show the last four characters and `key-file`, and no five consecutive characters of the key MUST appear in the output
