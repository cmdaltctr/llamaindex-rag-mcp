# settings-file Specification

## Purpose
Keep every omrs setting in one user file, `omrs.jsonc`, that people edit by hand and the Settings page also writes, with API keys held only as references to the environment, a key file or the system keychain.

## Requirements

### Requirement: The user config folder location

The web server, the CLI and the stdio MCP server SHALL read the user config folder: `$OMRS_CONFIG_DIR` when set, else `$XDG_CONFIG_HOME/omrs` when set, else `~/.config/omrs`. The folder MAY hold `omrs.jsonc` and `secrets/<name>.key`. A missing folder or file SHALL give no values and no warning. The folder `~/.config/omrg` and the variable `OMRG_CONFIG_DIR` SHALL NOT be read.

#### Scenario: Folder from OMRS_CONFIG_DIR

- **WHEN** `OMRS_CONFIG_DIR` names a folder that holds `omrs.jsonc` and `XDG_CONFIG_HOME` is also set
- **THEN** every process MUST read `omrs.jsonc` from the `OMRS_CONFIG_DIR` folder

#### Scenario: Folder from OMRG_CONFIG_DIR

- **WHEN** `OMRG_CONFIG_DIR` names a folder that holds `omrg.jsonc` and `OMRS_CONFIG_DIR` is not set
- **THEN** no process MUST read that folder

#### Scenario: Folder from XDG_CONFIG_HOME

- **WHEN** `OMRS_CONFIG_DIR` is not set and `XDG_CONFIG_HOME` names a folder
- **THEN** every process MUST read the `omrs` subfolder of it

#### Scenario: Default folder

- **WHEN** neither variable is set
- **THEN** every process MUST read `~/.config/omrs`

#### Scenario: Missing folder

- **WHEN** the folder does not exist and `omrs web` starts
- **THEN** the server MUST start with defaults and MUST log no warning

#### Scenario: The old folder is not a fallback

- **GIVEN** `~/.config/omrg/omrg.jsonc` exists and `~/.config/omrs` does not
- **WHEN** a process resolves the config folder
- **THEN** the process MUST NOT read `~/.config/omrg`

### Requirement: omrs.jsonc accepts every setting

`omrs.jsonc` SHALL accept JSON with comments and trailing commas. It SHALL accept every setting that the environment accepts. The file key SHALL be the environment name in lower case, and `__` SHALL nest one level, so `RETRIEVAL__TOP_K` is `retrieval.top_k` and `EMBED_PROVIDER` is `embed_provider`. It SHALL also accept `web_port`, `web_max_upload_mib` and `mcp_http_enabled`.

#### Scenario: Nested setting

- **WHEN** `omrs.jsonc` holds `{ "retrieval": { "top_k": 7 } }` and no environment value sets `RETRIEVAL__TOP_K`
- **THEN** a search MUST use 7 results and `omrs config show` MUST report `retrieval.top_k` as 7 from `omrs.jsonc`

#### Scenario: Flat setting

- **WHEN** `omrs.jsonc` holds `"embed_provider": "local"` and `"local_backend": "ollama"`
- **THEN** the engine MUST embed through Ollama

#### Scenario: Comments and trailing commas

- **WHEN** `omrs.jsonc` holds comments and a trailing comma and is otherwise valid
- **THEN** every process MUST read its values

### Requirement: Settings follow one source order

Each setting SHALL come from the first of these sources, highest first: an explicit per-operation option or launch option, the process environment (`env`), the `.env` file (`dotenv`), `omrs.jsonc` (`config-file`), the YAML defaults and profile bundle, then the code default (`default`). A value from `env` or `dotenv` SHALL lock its field in the Settings page. A value from `config-file` SHALL NOT lock its field.

#### Scenario: .env wins over the file

- **WHEN** `.env` sets `LLAMACPP_CHAT_URL` and `omrs.jsonc` sets `llamacpp_chat_url` to another address
- **THEN** the `.env` address MUST be used and the field MUST report the source `dotenv`

#### Scenario: Process environment named apart from .env

- **WHEN** the shell exports `OLLAMA_BASE_URL` and `.env` does not set it
- **THEN** the field MUST report the source `env`

#### Scenario: File value stays editable

- **WHEN** `omrs.jsonc` sets `ollama_base_url` and neither the environment nor `.env` sets it
- **THEN** the field MUST report the source `config-file` and a page save MUST succeed

### Requirement: Problems in omrs.jsonc do not stop the server

A file that cannot be parsed SHALL give no values. A value that fails its rule SHALL be ignored, and the next source SHALL apply. Each problem SHALL be logged once and listed in `GET /v1/settings/configuration` by key, never by value. The server SHALL start.

#### Scenario: Broken file

- **WHEN** `omrs.jsonc` is not valid JSONC and `omrs web` starts
- **THEN** the server MUST start with no values from the file, MUST log one warning and MUST list the problem "omrs.jsonc could not be read"

#### Scenario: Invalid value

- **WHEN** `omrs.jsonc` sets `retrieval.top_k` to `"many"`
- **THEN** the default MUST apply and the problem list MUST name `retrieval.top_k` and its rule

#### Scenario: Invalid address

- **WHEN** `omrs.jsonc` sets `ollama_base_url` to `file:///etc/passwd`
- **THEN** the value MUST be ignored and the warning MUST name the field and not the value

### Requirement: Unknown and old key names are reported

A key that names no setting SHALL be ignored and listed as unknown. A key that matches a retired flat environment name SHALL be ignored and listed with the nested key that replaced it.

#### Scenario: Typo

- **WHEN** `omrs.jsonc` holds `"retreival": { "top_k": 5 }`
- **THEN** the problem list MUST name `retreival` as unknown and the default top-k MUST apply

#### Scenario: Old flat name

- **WHEN** `omrs.jsonc` holds `"top_k": 5`
- **THEN** the problem list MUST name `top_k` and the replacement `retrieval.top_k`

### Requirement: Key fields hold references only

A secret field in `omrs.jsonc` SHALL hold one of: `env://NAME`, `file://<path inside secrets/>` (a leading `~` expands to the home folder), or `keychain://<provider>`. A literal key SHALL be ignored and logged once by field name. A `file://` path that resolves outside `secrets/`, after links, SHALL be refused.

#### Scenario: env reference

- **WHEN** `openrouter_api_key` is `env://MY_ROUTER_KEY` and that variable holds a key
- **THEN** the OpenRouter key MUST be used and the field MUST report the source `config-file`

#### Scenario: OMMS-style file reference

- **WHEN** `openrouter_api_key` is `file://~/.config/omrs/secrets/openrouter.key` and the file holds a key
- **THEN** the key MUST be used and the field MUST report the source `key-file` with that path

#### Scenario: Literal key

- **WHEN** `openrouter_api_key` holds `sk-or-123456`
- **THEN** no key MUST come from the file, and the log and problem list MUST name the field and MUST NOT contain the value

#### Scenario: Path outside secrets

- **WHEN** a reference is `file:///etc/passwd` or uses `..` to leave `secrets/`
- **THEN** the file MUST NOT be read and the problem list MUST name the field

### Requirement: A key file applies without a reference

When `omrs.jsonc` holds no reference for a provider key and no environment value sets it, the key in `secrets/<provider>.key` SHALL apply. Key files SHALL keep the existing safety rules: at most 4 KiB, a regular file, a warning when looser than mode 0600.

#### Scenario: Implicit key file

- **WHEN** `secrets/openrouter.key` holds a key and nothing else sets the OpenRouter key
- **THEN** the key MUST be used and the field MUST report the source `key-file` with the file path

#### Scenario: Reference wins over the implicit file

- **WHEN** `secrets/openrouter.key` exists and `omrs.jsonc` sets `openrouter_api_key` to `keychain://openrouter`
- **THEN** the keychain key MUST be used

### Requirement: Every process resolves keychain references

A `keychain://<provider>` reference SHALL read the system keychain entry with service `omrs` and the provider as user name, in the web server, the CLI and the stdio MCP server. When no usable keychain exists or the entry is missing, the field SHALL have no key and SHALL say why.

#### Scenario: CLI uses a key saved on the page

- **WHEN** a key was saved on the Settings page and the user runs a CLI command that needs that provider
- **THEN** the CLI MUST use the keychain key

#### Scenario: Entry missing

- **WHEN** `omrs.jsonc` holds `keychain://openrouter` and the keychain has no such entry
- **THEN** the field MUST report "Missing from the system keychain" and the provider MUST have no key

### Requirement: The Settings page writes omrs.jsonc

A save from the Settings page SHALL write the value into `omrs.jsonc` and SHALL NOT write the workspace database. Only keys that the page edits SHALL be writable. When the folder or file is missing, the server SHALL create the folder with mode 0700 and the file with mode 0600 and a header comment. A write SHALL go to a temporary file that replaces the original, and SHALL keep the original mode.

#### Scenario: First save creates the file

- **WHEN** no `omrs.jsonc` exists and the user saves an Ollama address
- **THEN** the file MUST exist with mode 0600, MUST hold `ollama_base_url`, and the field MUST report the source `config-file`

#### Scenario: Key outside the allowed list

- **WHEN** a request asks the server to write `embed_provider`
- **THEN** the server MUST answer 400 and MUST NOT change the file

#### Scenario: Broken file is not overwritten

- **WHEN** `omrs.jsonc` is not valid JSONC and the user saves a field on the page
- **THEN** the server MUST answer 409 with "omrs.jsonc could not be read. Fix it, then save again." and MUST NOT change the file

#### Scenario: Interrupted write

- **WHEN** the server stops during a save
- **THEN** `omrs.jsonc` MUST hold either the old or the new content, never a partial file

### Requirement: A page save keeps the rest of the file

A write SHALL change only the saved key. Comments, key order, formatting of other members and keys the page does not edit SHALL stay as they were. Clearing a value SHALL remove its member.

#### Scenario: Comments kept

- **WHEN** `omrs.jsonc` holds comments and `retrieval.top_k`, and the user saves the Chat model
- **THEN** the comments and `retrieval.top_k` MUST be unchanged and `answer.model` MUST hold the new model

#### Scenario: Clear a value

- **WHEN** the user returns the Ollama context window to the default
- **THEN** `ollama_context_window` MUST no longer be in the file and the field MUST report the source `default`

### Requirement: A page save never overwrites a hand edit

Each settings read SHALL return a revision of `omrs.jsonc`. A save SHALL carry that revision. When the file changed after that revision, the server SHALL answer 409 with "omrs.jsonc changed on disk. Reload to see the new values." and SHALL NOT write.

#### Scenario: File edited while the page is open

- **WHEN** the user opens Settings, edits `omrs.jsonc` in an editor, then saves a field on the page
- **THEN** the server MUST answer 409, the editor's change MUST stay in the file, and the page MUST show the 409 message

### Requirement: The page never writes a key into a file

The server SHALL write only references into `omrs.jsonc`. It SHALL NOT write, create or delete `.env`, any file in `secrets/`, or a literal key anywhere.

#### Scenario: Key saved on the page

- **WHEN** the user saves an OpenRouter key on the page
- **THEN** `omrs.jsonc` MUST hold `"openrouter_api_key": "keychain://openrouter"` and no file under the config folder or the workspace MUST contain the key

### Requirement: Hand edits apply without a restart

`omrs web` SHALL notice a change to `omrs.jsonc` before it serves the next request that reads settings. Settings that apply at once SHALL use the new value from that request on: provider addresses, provider keys, the Chat provider and model, the claim check judge provider and model (`answer.verify_provider`, `answer.verify_model`), context windows, llama.cpp server values, `web_max_upload_mib` and `mcp_http_enabled`. The CLI and the stdio MCP server SHALL read the file at launch.

#### Scenario: Edit the Chat model by hand

- **WHEN** `omrs web` runs and the user changes `answer.model` in `omrs.jsonc`
- **THEN** the next answer MUST use the new model with no restart, and Settings MUST show it from `omrs.jsonc`

#### Scenario: Edit the judge model by hand

- **WHEN** `omrs web` runs and the user changes `answer.verify_model` in `omrs.jsonc`
- **THEN** the next answer with claim checks on MUST use the new judge model with no restart, and the Configuration section MUST NOT show "Restart to apply" for it

#### Scenario: Edit the upload limit by hand

- **WHEN** the user sets `web_max_upload_mib` to 200 in the file while the server runs
- **THEN** the next upload MUST be checked against 200 MiB

### Requirement: Some settings apply only after a restart

`web_port` and the engine settings (embedding, vector store, chunking, ingestion, retrieval, metadata, OCR, and the `answer` members other than `provider`, `model`, `verify_provider` and `verify_model`) SHALL apply at the next launch of the process. `omrs web` SHALL keep the values it started with and SHALL report each such key whose file value differs from it.

#### Scenario: Edit top-k by hand

- **WHEN** `omrs web` runs and the user changes `retrieval.top_k` in `omrs.jsonc`
- **THEN** searches MUST keep the launch value, and `GET /v1/settings/configuration` MUST list `retrieval.top_k` as "Restart to apply"

#### Scenario: Edit verify_claims by hand

- **WHEN** `omrs web` runs and the user changes `answer.verify_claims` in `omrs.jsonc`
- **THEN** `GET /v1/settings/configuration` MUST list `answer.verify_claims` as "Restart to apply"

#### Scenario: Embedding model changed by hand

- **WHEN** the user changes `embed_model` and restarts, and a collection holds vectors from the old model
- **THEN** a search of that collection MUST fail with the existing embedding-stamp message and MUST NOT mix vectors

### Requirement: Saved settings move out of the workspace database

When `omrs web` opens a workspace whose database still holds settings rows, it SHALL copy each valid row into `omrs.jsonc` where the file does not set that key, SHALL add `keychain://<provider>` for each provider whose saved key is in the keychain, and SHALL then delete the copied rows. When the file cannot be written, the rows SHALL stay, SHALL NOT be used, and Settings SHALL say so.

#### Scenario: Saved port moves

- **WHEN** the database holds `web_port` 9100 and `omrs.jsonc` does not set `web_port`
- **THEN** after the start `omrs.jsonc` MUST hold `"web_port": 9100` and the database MUST hold no settings rows

#### Scenario: File value wins

- **WHEN** the database holds an Ollama address and `omrs.jsonc` already sets `ollama_base_url`
- **THEN** the file value MUST stay and the row MUST be deleted

#### Scenario: Folder not writable

- **WHEN** the config folder cannot be written
- **THEN** the server MUST start, the rows MUST stay, and Settings MUST show "Saved settings could not be moved to omrs.jsonc" with the folder path

#### Scenario: Other processes do not move rows

- **WHEN** the CLI or the stdio MCP server starts
- **THEN** it MUST NOT read or delete settings rows

### Requirement: omrs config init writes a starter file

`omrs config init` SHALL write `omrs.jsonc` in the user config folder with every setting as a commented line that shows its default and its environment name, and SHALL create the folder with mode 0700 and the file with mode 0600. It SHALL refuse with exit code 1 when the file exists, unless `--force` is given, which SHALL keep a dated copy of the old file.

#### Scenario: New file

- **WHEN** no `omrs.jsonc` exists and the user runs `omrs config init`
- **THEN** the file MUST exist, MUST parse, and MUST set no value

#### Scenario: Existing file

- **WHEN** `omrs.jsonc` exists and the user runs `omrs config init`
- **THEN** the command MUST exit with code 1, MUST name the file, and MUST NOT change it

### Requirement: omrs config show prints each setting and its source

`omrs config show` SHALL print each setting with its value and its source, and SHALL list the problems found in `omrs.jsonc`. A key SHALL show at most "set", the last four characters and the source. Output SHALL go to stderr.

#### Scenario: Key masked

- **WHEN** the OpenRouter key comes from `secrets/openrouter.key`
- **THEN** the line MUST show the last four characters and `key-file`, and no five consecutive characters of the key MUST appear in the output

### Requirement: The page may write the document-reading keys

The keys the Settings page may write SHALL include `pdf_reader`, `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`. A page write of one of these keys SHALL check the value before it writes: `pdf_reader` SHALL be one of `auto`, `liteparse`, `pdf_inspector`, `pypdfium2` and `pypdf`; an engine name SHALL start with a letter or digit, SHALL hold only letters, digits, dots, hyphens and underscores, and SHALL be at most 64 characters; a boolean key SHALL take only `true` or `false`; a fraction key SHALL take only a number from 0.0 to 1.0; `ocr_routing_unit` SHALL be `document` or `page`; and a blank text value SHALL be refused. `null` SHALL remove the key. These write checks SHALL NOT change how a value is read at startup: a `pdf_reader` value outside the five names, from any source, SHALL still log a warning and fall back to `auto`.

#### Scenario: Valid reader written

- **WHEN** the page writes `pdf_reader` `liteparse`
- **THEN** `omrs.jsonc` MUST hold `"pdf_reader": "liteparse"` and every other byte of the file MUST stay as it was

#### Scenario: Unknown reader refused on write

- **WHEN** the page writes `pdf_reader` `pdfminer`
- **THEN** the write MUST be refused with "pdf_reader: The value must be one of: auto, liteparse, pdf_inspector, pypdfium2, pypdf." and the file MUST NOT change

#### Scenario: Unknown reader in the file at startup

- **WHEN** a person writes `"pdf_reader": "pdfminer"` into `omrs.jsonc` by hand and the server starts
- **THEN** the server MUST log a warning and MUST use `auto`, as before this change

#### Scenario: Engine name with a path

- **WHEN** the page writes `ocr_engine_fallback` `../other`
- **THEN** the write MUST be refused with the engine name rule and the file MUST NOT change

#### Scenario: Blank engine name refused

- **WHEN** the page writes `ocr_engine_fallback` as an empty string
- **THEN** the write MUST be refused with "ocr_engine_fallback: The value must not be blank. Send null to use the default." and the file MUST NOT change

#### Scenario: Text where a boolean is expected

- **WHEN** the page writes `ocr_fallback_enabled` as the text `"true"`
- **THEN** the write MUST be refused with "ocr_fallback_enabled: The value must be true or false." and the file MUST NOT change
