## MODIFIED Requirements

### Requirement: Connections show provider configuration without secrets

The Providers section SHALL show one card for each entry of `GET /v1/connections`. Each card SHALL show the provider name, a Local or Cloud badge with text, the roles that use it, each editable field as a setting row, the read-only values (embedding address and models) as read-only rows, and the install command when the provider is not installed. A field from `env` SHALL show "Set in the environment. Change it there." with the variable name. A field from `dotenv` SHALL show "Set in .env. Change it there." with the variable name and the `.env` path. A field from `config-file` SHALL show "Saved in settings (omrs.jsonc)" and SHALL stay editable. A key from `key-file` SHALL show "from key file" with the file path. A key from `keychain` SHALL show "in system keychain". The field source SHALL be one of `env`, `dotenv`, `config-file`, `keychain`, `key-file`, `default` and `none`. A key field SHALL show at most "Key set" and the last four characters. A Cloud card, and a card whose address is not on this machine, SHALL state that text leaves this machine. The section SHALL name the `omrs.jsonc` path and SHALL state that saves are written there.

#### Scenario: Roles follow the configuration

- **WHEN** `EMBED_PROVIDER` is `local`, `LOCAL_BACKEND` is `llamacpp` and the Chat provider is `ollama`
- **THEN** llama.cpp MUST list the embeddings role and Ollama MUST list the answers role

#### Scenario: Key is never exposed

- **WHEN** `OPENROUTER_API_KEY` is set in `.env`
- **THEN** the OpenRouter card MUST show "Set in .env. Change it there.", and no five consecutive characters of the key MUST appear in the response or the page

#### Scenario: Address from the config file

- **WHEN** the Ollama entry reports the source `config-file`
- **THEN** the card MUST show the address with "Saved in settings (omrs.jsonc)" and MUST offer Edit

#### Scenario: Key from a key file

- **WHEN** the OpenRouter key field reports the source `key-file` for `secrets/openrouter.key`
- **THEN** the card MUST show "Key set · ending <last four> · from key file secrets/openrouter.key" and MUST offer Replace and no Remove

#### Scenario: Save an address

- **WHEN** the Ollama address is not locked and the user presses Edit, changes the address and presses Save
- **THEN** the card MUST show the address and the source `config-file` that the server returns after the save

#### Scenario: Replace a key

- **WHEN** the user presses Replace, types a new OpenRouter key and presses Save key
- **THEN** the input MUST close, the card MUST show "Key set · ending <last four> · in system keychain", and the page MUST NOT show the key again

#### Scenario: Optional key

- **WHEN** the `openai_compatible` entry marks its key field as optional and no key is set
- **THEN** the card MUST show the key field as optional, MUST NOT show an error, and the Chat section MUST allow choosing `openai_compatible`

#### Scenario: Provider not installed

- **WHEN** the `anthropic` entry reports that its package is not installed
- **THEN** the card MUST show the install command `uv sync --extra anthropic`, and the Chat section MUST mark `anthropic` as not ready with the reason in text

#### Scenario: No keychain

- **WHEN** the server reports that no keychain is available and no key is set
- **THEN** the key field MUST show one plain line that says so and names `secrets/<provider>.key` and the environment variable, and MUST offer no key input

### Requirement: The Ollama card edits the context window

The Ollama card SHALL show "Context window (tokens)" as a setting row with its value and source. Edit SHALL open a number field filled with the current value, with the minimum 2,048 and the maximum 262,144. A locked field SHALL be read-only and SHALL state its lock. A saved value SHALL be written to `omrs.jsonc` and SHALL apply at once. The card SHALL state that the window does not apply to embedding models.

#### Scenario: Show default

- **WHEN** the user opens Settings > Providers with no value set
- **THEN** the Ollama card MUST show 16384 and the source "default"

#### Scenario: Save a value

- **WHEN** the user presses Edit, types 32768 and presses Save
- **THEN** the card MUST show 32768 and the source "Saved in settings (omrs.jsonc)"

#### Scenario: Out of range

- **WHEN** the user types 1000
- **THEN** the card MUST show the friendly error "Enter 2,048 to 262,144." and MUST NOT save

#### Scenario: Locked by environment

- **WHEN** the field reports source `env` or `dotenv`
- **THEN** the card MUST show where it is set and MUST NOT offer Edit

### Requirement: Every setting is shown as a value and source row

Each editable setting on the Settings page SHALL show one row with its label, the value in force and its source in plain words ("Saved in settings (omrs.jsonc)", "Set in .env", "Set in the environment", "default"). Edit SHALL open an input filled with the value in force, with Save and Cancel. The page SHALL NOT show an empty input for a field that has a value.

#### Scenario: Value from the file

- **WHEN** `omrs.jsonc` sets `llamacpp_server_binary` to `/opt/homebrew/bin/llama-server`
- **THEN** the row MUST show that path and "Saved in settings (omrs.jsonc)", and no input MUST be visible until the user presses Edit

#### Scenario: Edit opens filled

- **WHEN** the user presses Edit on that row
- **THEN** the input MUST hold `/opt/homebrew/bin/llama-server`

#### Scenario: Default value shown

- **WHEN** no source sets the Ollama address
- **THEN** the row MUST show `http://localhost:11434` and "default"

### Requirement: The Configuration section lists every setting

Settings SHALL have a Configuration section that lists every setting, grouped by block, with its value in force, its source, and "Restart to apply" when its file value differs from the value the server started with. Keys SHALL show at most the last four characters. The section SHALL show the `omrs.jsonc` path with a copy action, and the problems found in the file. It SHALL take its data from `GET /v1/settings/configuration` (read scope). Each setting SHALL be a mini card. A setting the server reports as editable SHALL offer Edit, which opens a control for its kind: an on/off switch for a boolean, a number field with its range for a number, a choice list for a setting with fixed choices, and a text field for text. Save SHALL call `PUT /v1/settings/configuration` with the revision the section read. A setting the server reports as read-only SHALL show its reason and no Edit. A setting set in the environment or `.env` SHALL be read-only and SHALL show "Remove <ENV_NAME> from the environment or .env to edit it here." An optional setting saved in the file SHALL offer Clear, which removes the key so the default applies. A chunking setting SHALL state that it is part of the index identity, so the next ingest after a restart can read existing files again.

#### Scenario: Engine setting edited by hand

- **WHEN** the user changes `retrieval.top_k` in `omrs.jsonc` while the server runs
- **THEN** the section MUST show the launch value, the source `config-file` and "Restart to apply", and MUST offer the restart dialog

#### Scenario: Problems listed

- **WHEN** `omrs.jsonc` holds an unknown key and an invalid value
- **THEN** the section MUST list both by key with one plain line each and MUST NOT show the invalid value

#### Scenario: Database rows not moved

- **WHEN** the server could not move saved settings into `omrs.jsonc`
- **THEN** the section MUST show "Saved settings could not be moved to omrs.jsonc" with the folder path

#### Scenario: Edit a restart-only number

- **WHEN** `retrieval.top_k` comes from the default and the user edits it to 20 and saves
- **THEN** the page MUST send `{"revision": <read revision>, "changes": {"retrieval.top_k": 20}}`, the row MUST show 20 with "Saved in settings (omrs.jsonc)" and "Restart to apply", and the restart dialog MUST be offered

#### Scenario: Turn a boolean off

- **WHEN** the user switches `answer.enabled` off and saves
- **THEN** `omrs.jsonc` MUST hold `answer.enabled` false and the row MUST show "Off"

#### Scenario: Choose from fixed choices

- **WHEN** the user edits `metadata.extraction_mode`
- **THEN** the control MUST be a choice list of the accepted modes, and no free text MUST be possible

#### Scenario: Out of range number refused before the request

- **WHEN** the server reports `answer.max_rounds` with the range 1 to 8 and the user types 12
- **THEN** the page MUST show the range rule and MUST NOT send a request

#### Scenario: Read-only identity setting

- **WHEN** the section shows `embed_model`
- **THEN** the row MUST show its value and its reason ("The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest.") and MUST NOT offer Edit

#### Scenario: Clear an optional setting

- **WHEN** `omrs.jsonc` holds `metadata.ollama_classify_timeout_override` 30 and the user presses Clear
- **THEN** the key MUST be removed from the file and the row MUST show the default and the source "default"

#### Scenario: File changed under the page

- **WHEN** someone edits `omrs.jsonc` by hand after the section loaded and the user then saves a setting
- **THEN** the page MUST show "omrs.jsonc changed on disk. Reload to see the new values." and MUST NOT write
