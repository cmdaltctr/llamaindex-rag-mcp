# workspace-settings Specification

## Purpose
A Settings area that holds the workspace-wide controls and information that belong to no other view: appearance, provider connections, MCP access, the live server log, runtime capabilities and workspace details.

## Requirements

### Requirement: Settings is split into sections

The Settings view SHALL offer the sections Appearance, Providers, Chat, MCP, Server log, Runtime, Workspace, Document reading and Configuration, in that order, switched with chip buttons, with one section shown at a time. Each section SHALL have the address `#/settings/<section>` (`appearance`, `providers`, `chat`, `mcp`, `log`, `runtime`, `workspace`, `document-reading`, `configuration`). Selecting a chip SHALL rewrite the address. `#/settings` SHALL show Appearance.

#### Scenario: Switch section

- **WHEN** the user selects the Server log chip
- **THEN** only the Server log section MUST show, the Server log chip MUST be marked selected, and the address MUST read `#/settings/log`

#### Scenario: Open a section from a link

- **WHEN** the app opens at `#/settings/chat`
- **THEN** only the Chat section MUST show and the Chat chip MUST be marked selected

#### Scenario: Open Document reading from a link

- **WHEN** the app opens at `#/settings/document-reading`
- **THEN** only the Document reading section MUST show, its chip MUST be marked selected, and its chip MUST come directly before the Configuration chip

### Requirement: Connections show provider configuration without secrets

The Providers section SHALL show one card for each entry of `GET /v1/connections`. Each card SHALL show the provider name, a Local or Cloud badge with text, the roles that use it, each editable field as a setting row, the read-only values (embedding address and models) as read-only rows, and the install command when the provider is not installed. A field from `env` SHALL show "Set in the environment. Change it there." with the variable name. A field from `dotenv` SHALL show "Set in .env. Change it there." with the variable name and the `.env` path. A field from `config-file` SHALL show "from omrs.jsonc" and SHALL stay editable. A key from `key-file` SHALL show "from key file" with the file path. A key from `keychain` SHALL show "in system keychain". The field source SHALL be one of `env`, `dotenv`, `config-file`, `keychain`, `key-file`, `default` and `none`. A key field SHALL show at most "Key set" and the last four characters. A Cloud card, and a card whose address is not on this machine, SHALL state that text leaves this machine. The section SHALL name the `omrs.jsonc` path and SHALL state that saves are written there.

#### Scenario: Roles follow the configuration

- **WHEN** `EMBED_PROVIDER` is `local`, `LOCAL_BACKEND` is `llamacpp` and the Chat provider is `ollama`
- **THEN** llama.cpp MUST list the embeddings role and Ollama MUST list the answers role

#### Scenario: Key is never exposed

- **WHEN** `OPENROUTER_API_KEY` is set in `.env`
- **THEN** the OpenRouter card MUST show "Set in .env. Change it there.", and no five consecutive characters of the key MUST appear in the response or the page

#### Scenario: Address from the config file

- **WHEN** the Ollama entry reports the source `config-file`
- **THEN** the card MUST show the address with "from omrs.jsonc" and MUST offer Edit

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

### Requirement: A connection test runs only on request

Each provider card SHALL offer a Test action that calls `POST /v1/connections/{provider}/test`. When a field holds an unsaved typed value, the request SHALL carry it and the server SHALL test it without saving it. The server SHALL send one model-list or key-check request for each address with a 5-second timeout, and return whether the provider was reachable and a reason from a fixed set (`refused`, `timeout`, `unauthorised`, `http-<status>`, `not-configured`). The server SHALL NOT return response bodies or exception text, SHALL NOT log a typed key, and SHALL NOT contact any provider unless a test or a model list is requested.

#### Scenario: Local provider down

- **WHEN** the user tests Ollama and nothing listens on its URL
- **THEN** the entry MUST show not reachable with the reason refused, stated in text with a badge

#### Scenario: No background cloud call

- **WHEN** the user opens Providers or Chat and presses no Test or List models action
- **THEN** the server MUST NOT send any request to OpenRouter

#### Scenario: Test a typed key before saving

- **WHEN** the user types an OpenRouter key, presses Test and the provider rejects the key
- **THEN** the card MUST show not reachable with the reason unauthorised, and the saved key state MUST NOT change

### Requirement: The server log streams redacted lines

The Server log section SHALL show the server's recent log records in a monospace, terminal-style panel, loaded from `GET /v1/logs` and followed live through `GET /v1/logs/stream`, with a level filter, pause, copy, and auto-scroll while the panel is scrolled to the bottom. Both endpoints SHALL require the browser session. Records SHALL be redacted before they are buffered, the buffer SHALL hold at most the last 1,000 records in memory, and the stream SHALL end when the server stops admitting requests.

#### Scenario: Live line

- **WHEN** the server logs a warning while the section is open
- **THEN** the warning MUST appear in the panel without a reload

#### Scenario: Secret removed

- **WHEN** a log message contains the configured OpenRouter key
- **THEN** the buffered record, the response and the panel MUST NOT contain the key

#### Scenario: Bearer credential refused

- **WHEN** a request to either log endpoint carries a bearer credential instead of the browser session
- **THEN** the server MUST refuse it

### Requirement: The MCP section shows how to connect a client

The MCP section SHALL show a copyable stdio client configuration that starts `omrs` with `uv run --directory <project>`, where `<project>` is `config_dir` from `GET /v1/connections`, so the client's process reads the same `.env`. It SHALL also show, through the endpoints of the `add-mcp-http-transport` change only: an on/off switch for MCP over HTTP, the HTTP client configuration with the server's `/mcp` URL, token create, rotate and revoke with a new token shown once, and the saved web port that applies on the next launch.

#### Scenario: Copy stdio configuration

- **WHEN** the user copies the stdio configuration
- **THEN** the clipboard MUST hold a client configuration that runs `uv run --directory <project> omrs` with `config_dir` as `<project>`

#### Scenario: Switch reflects the server

- **WHEN** the server reports MCP over HTTP as off and the user turns the switch on
- **THEN** the section MUST show the state the server returns after the change, not an assumed state

#### Scenario: Token shown once

- **WHEN** the user creates the MCP token and then leaves and reopens the MCP section
- **THEN** the token MUST show with a copy action after creation and MUST NOT show after reopening

### Requirement: The Chat section chooses the Chat model

The Chat section SHALL show the Chat provider and model from `GET /v1/settings/chat` as setting rows with their source. When the choice is not locked, Edit SHALL open a provider select of the registered providers, each provider that is not ready marked with its reason in text, a model name field filled with the current model, a List models action that fills the field from the provider's list, a Test action for the typed choice, Save, Cancel and Clear. Save SHALL write `answer.provider` and `answer.model` to `omrs.jsonc`.

#### Scenario: Pick a model from the list

- **WHEN** the user presses Edit, selects Ollama, presses List models and picks `qwen3:4b`
- **THEN** the model name field MUST hold `qwen3:4b` and nothing MUST be saved until the user presses Save

#### Scenario: Type a model name

- **WHEN** the user selects OpenRouter, types `openai/gpt-4o-mini` and presses Save
- **THEN** the section MUST show the choice with the source `config-file` that the server returns

#### Scenario: Locked choice

- **WHEN** `.env` sets `ANSWER__PROVIDER`
- **THEN** the section MUST show the choice as locked, name the variable and `.env`, and offer no Edit action

#### Scenario: Test result

- **WHEN** the user presses Test and the server reports ok false with the reason timeout
- **THEN** the section MUST show the failure as a badge with text and one plain sentence, and MUST NOT show provider text

### Requirement: The Chat section says where the choice applies

The Chat section SHALL state that the choice also answers MCP clients of this web server that cannot supply their own model, that metadata extraction keeps its own model, that the claim check judge has its own choice in the block below, and that `omrs` over stdio and the CLI read the same `omrs.jsonc` at their next launch. When the selected provider is cloud, the section SHALL state that questions and retrieved passages leave this machine.

#### Scenario: Cloud choice warns

- **WHEN** the user selects OpenRouter in the Chat section
- **THEN** the section MUST state that questions and retrieved passages are sent to openrouter.ai

#### Scenario: Local choice

- **WHEN** the user selects Ollama with an address on this machine
- **THEN** the section MUST NOT show the cloud statement

### Requirement: The Ollama card edits the context window

The Ollama card SHALL show "Context window (tokens)" as a setting row with its value and source. Edit SHALL open a number field filled with the current value, with the minimum 2,048 and the maximum 262,144. A locked field SHALL be read-only and SHALL state its lock. A saved value SHALL be written to `omrs.jsonc` and SHALL apply at once. The card SHALL state that the window does not apply to embedding models.

#### Scenario: Show default

- **WHEN** the user opens Settings > Providers with no value set
- **THEN** the Ollama card MUST show 16384 and the source "default"

#### Scenario: Save a value

- **WHEN** the user presses Edit, types 32768 and presses Save
- **THEN** the card MUST show 32768 and the source "from omrs.jsonc"

#### Scenario: Out of range

- **WHEN** the user types 1000
- **THEN** the card MUST show the friendly error "Enter 2,048 to 262,144." and MUST NOT save

#### Scenario: Locked by environment

- **WHEN** the field reports source `env` or `dotenv`
- **THEN** the card MUST show where it is set and MUST NOT offer Edit

### Requirement: The llama.cpp card shows a Local server panel

The llama.cpp card SHALL show a "Local server" panel with: the state as text and a badge (`stopped`, `starting`, `running` or `failed`); the fixed reason when the state is `failed`; setting rows for program path, model, context window and idle sleep, each with its value and source; and the buttons Start, Stop and Restart. The panel SHALL say: "omrs starts and stops only this server. It never touches a server you started yourself." The panel SHALL show "Restart to apply" when the values in force differ from the values of the running server. The panel SHALL NOT show output of the server. Start SHALL be disabled while the state is `starting` or `running`. Stop SHALL be disabled while the state is `stopped`. A locked field SHALL be read-only and SHALL state its lock. The panel SHALL state that the embedding server is not managed. When Start fails because a value is not set, the panel SHALL name the missing value.

#### Scenario: Stopped

- **WHEN** no server is running
- **THEN** the panel MUST show the state `stopped`, Start enabled and Stop disabled

#### Scenario: Failed with a reason

- **WHEN** a start ends with reason `port-in-use`
- **THEN** the panel MUST show the state `failed` and a friendly line for the reason, and MUST NOT show any process output

#### Scenario: Restart to apply

- **WHEN** the server is running and the user saves a new model
- **THEN** the server MUST keep running and the panel MUST show "Restart to apply"

#### Scenario: Ownership text

- **WHEN** the user opens the panel
- **THEN** it MUST show "omrs starts and stops only this server. It never touches a server you started yourself."

#### Scenario: Program and model need a credentials session

- **WHEN** the session lacks the `credentials` scope
- **THEN** the program path and model rows MUST be read-only and MUST state that the scope is needed

#### Scenario: Locked field

- **WHEN** `LLAMACPP_SERVER_MODEL` is in the environment
- **THEN** the model row MUST say where it is set and MUST NOT offer Edit

#### Scenario: Not configured

- **WHEN** no program path is set and the user presses Start
- **THEN** the panel MUST show the state `failed` and the line "Set the program path first."

### Requirement: Every setting is shown as a value and source row

Each editable setting on the Settings page SHALL show one row with its label, the value in force and its source in plain words ("from omrs.jsonc", "Set in .env", "Set in the environment", "default"). Edit SHALL open an input filled with the value in force, with Save and Cancel. The page SHALL NOT show an empty input for a field that has a value.

#### Scenario: Value from the file

- **WHEN** `omrs.jsonc` sets `llamacpp_server_binary` to `/opt/homebrew/bin/llama-server`
- **THEN** the row MUST show that path and "from omrs.jsonc", and no input MUST be visible until the user presses Edit

#### Scenario: Edit opens filled

- **WHEN** the user presses Edit on that row
- **THEN** the input MUST hold `/opt/homebrew/bin/llama-server`

#### Scenario: Default value shown

- **WHEN** no source sets the Ollama address
- **THEN** the row MUST show `http://localhost:11434` and "default"

### Requirement: A set key shows a summary row

A key field with a key SHALL show one row "Key set · ending <last four> · <source>" and no input. It SHALL offer Replace, which opens an empty key input, unless the key comes from `env` or `dotenv`. It SHALL offer Remove only when the key is in the system keychain.

#### Scenario: Key in the keychain

- **WHEN** the OpenRouter key comes from `keychain://openrouter`
- **THEN** the row MUST read "Key set · ending <last four> · in system keychain" and MUST offer Replace and Remove

#### Scenario: Key in .env

- **WHEN** the OpenRouter key comes from `.env`
- **THEN** the row MUST read "Key set · ending <last four> · Set in .env. Change it there." and MUST offer no button

#### Scenario: No key

- **WHEN** no source sets the OpenRouter key and a keychain is available
- **THEN** the field MUST show a key input with the placeholder "Paste key (saved to the system keychain)" and the hint "Or put it in secrets/openrouter.key"

### Requirement: A refused save shows its reason

When the server refuses a Settings save with 400 or 409 and a message, the page SHALL show that message as one line with one action. Server messages for these answers SHALL name the rule or the source and SHALL NOT contain the refused value or any key.

#### Scenario: Program rule

- **WHEN** the user saves `~/.llama-app/llama` as the llama.cpp program
- **THEN** the card MUST show the program rule message and MUST NOT show "The local server could not complete that request."

#### Scenario: File changed on disk

- **WHEN** a save returns 409 because `omrs.jsonc` changed
- **THEN** the page MUST show "omrs.jsonc changed on disk. Reload to see the new values." with a Reload action

### Requirement: A restart-only change offers a restart

After the user saves a setting that applies only after a restart, the page SHALL open a dialog that names the setting and offers "Restart now" and "Later". "Restart now" SHALL use the power menu restart. When the app runs in a terminal, the dialog SHALL show the command to restart instead of "Restart now". "Later" SHALL leave the row marked "Restart to apply".

#### Scenario: Port saved

- **WHEN** the app runs as the login item and the user saves port 9100
- **THEN** a dialog MUST say that port 9100 applies after a restart and MUST offer "Restart now" and "Later"

#### Scenario: Restart now

- **WHEN** the user presses "Restart now"
- **THEN** the page MUST send the power menu restart request and MUST say that the page signs in again by itself, and MUST name `omrs web open` for a restart that moves the app to a new port

#### Scenario: Foreground server

- **WHEN** the app runs in a terminal and the user saves port 9100
- **THEN** the dialog MUST show the restart command and MUST NOT offer "Restart now"

### Requirement: The Configuration section lists every setting

Settings SHALL have a Configuration section that lists every setting read-only, grouped by block, with its value in force, its source, and "Restart to apply" when its file value differs from the value the server started with. Keys SHALL show at most the last four characters. The section SHALL show the `omrs.jsonc` path with a copy action, and the problems found in the file. It SHALL take its data from `GET /v1/settings/configuration` (read scope).

#### Scenario: Engine setting edited by hand

- **WHEN** the user changes `retrieval.top_k` in `omrs.jsonc` while the server runs
- **THEN** the section MUST show the launch value, the source `config-file` and "Restart to apply", and MUST offer the restart dialog

#### Scenario: Problems listed

- **WHEN** `omrs.jsonc` holds an unknown key and an invalid value
- **THEN** the section MUST list both by key with one plain line each and MUST NOT show the invalid value

#### Scenario: Database rows not moved

- **WHEN** the server could not move saved settings into `omrs.jsonc`
- **THEN** the section MUST show "Saved settings could not be moved to omrs.jsonc" with the folder path

### Requirement: Document reading shows the reading settings and their state

The Document reading section SHALL show one row for each of `pdf_reader`, `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`. Each row SHALL show the value in force since launch, its source and the default. When the saved file value differs from the value in force, the row SHALL show the saved value and "Restart to apply". A key set in the environment or `.env` SHALL be read-only and SHALL show "Remove <ENV_NAME> from the environment or .env to edit it here." The section SHALL state that the settings apply after a restart, and that they are part of the index identity, so the next ingest after a restart can read existing files again. The PDF reader choice SHALL mark each reader that is not installed and SHALL NOT let the user choose it. The engine choices SHALL list the engines the server reports and SHALL mark each engine that is not provisioned, with the reason. When `OCR_WORKER_COMMAND` is set, the section SHALL say that it replaces the primary engine.

#### Scenario: Value saved but not yet in force

- **WHEN** the server launched with `pdf_reader` `auto` and `omrs.jsonc` now holds `"pdf_reader": "liteparse"`
- **THEN** the PDF reader row MUST show `auto` in force, `liteparse` saved and "Restart to apply"

#### Scenario: Key locked by the environment

- **WHEN** `OCR_ROUTING_UNIT=page` is set in `.env`
- **THEN** the routing unit row MUST offer no Edit and MUST show "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here."

#### Scenario: Reader not installed

- **WHEN** the server reports `pypdfium2` as not installed
- **THEN** the PDF reader choice MUST show `pypdfium2` as not available with the reason and MUST NOT allow it to be selected

#### Scenario: Worker command overrides the primary engine

- **WHEN** `OCR_WORKER_COMMAND` is set
- **THEN** the primary engine row MUST say that `OCR_WORKER_COMMAND` replaces the primary engine

### Requirement: Document reading saves to omrs.jsonc for the next launch

A save in the Document reading section SHALL write the changed keys into `omrs.jsonc` with the file revision the page last read. A save SHALL NOT change the value in force. After a save that leaves a key waiting for a restart, the page SHALL offer the restart dialog and SHALL repeat the index identity note. "Use default" on a row SHALL remove the key from the file. A refused save SHALL show the server message and SHALL leave the row unchanged.

#### Scenario: Save a fraction

- **WHEN** the user sets the OCR page fraction to 0.2 and presses Save
- **THEN** `omrs.jsonc` MUST hold `"ocr_fallback_page_fraction": 0.2`, the row MUST show "Restart to apply", and the restart dialog MUST open

#### Scenario: Return to the default

- **WHEN** the file holds `"ocr_engine_fallback": "my-engine"` and the user presses "Use default" on that row
- **THEN** `omrs.jsonc` MUST no longer hold `ocr_engine_fallback`

#### Scenario: File edited while the page is open

- **WHEN** the user edits `omrs.jsonc` in an editor and then saves a row in Document reading
- **THEN** the page MUST show "omrs.jsonc changed on disk. Reload to see the new values." and MUST offer Reload

### Requirement: Document reading routes

`GET /v1/settings/document-reading` SHALL need the read scope. It SHALL return the file `revision`, one entry for each of the nine keys in a fixed order (with the value in force, the saved value, the source, whether it is locked, the lock reason, whether a restart is pending, and the default), every PDF reader with its availability, the reader in use, and the OCR workers folder, whether `OCR_WORKER_COMMAND` is set, and each known engine with its availability. `PUT /v1/settings/document-reading` SHALL need a browser session with the manage scope. It SHALL take `values` (one to nine of the nine keys, each a value or `null`) and a required `revision`. It SHALL write all values or none. On success it SHALL return the same body as `GET`. It SHALL answer 400 for a key outside the nine, for a value that breaks its rule, for a blank text value and for a PDF reader that is not installed. It SHALL answer 409 for a locked key, for a stale revision and for a file that cannot be parsed. No error message SHALL hold a submitted value.

#### Scenario: Read the section

- **WHEN** a session with the read scope sends `GET /v1/settings/document-reading`
- **THEN** the answer MUST be 200 and MUST hold nine `settings` entries, `pdf_readers` starting with `auto`, and `ocr.engines`

#### Scenario: Key outside the nine

- **WHEN** a `PUT` sets `embed_provider`
- **THEN** the server MUST answer 400 "embed_provider is not a document reading setting." and MUST NOT change the file

#### Scenario: Locked key

- **WHEN** `PDF_READER` is set in the environment and a `PUT` sets `pdf_reader`
- **THEN** the server MUST answer 409 "Remove PDF_READER from the environment or .env to edit it here." and MUST NOT change the file

#### Scenario: Value out of range

- **WHEN** a `PUT` sets `ocr_maths_page_fraction` to 1.5
- **THEN** the server MUST answer 400 with a message that names `ocr_maths_page_fraction` and the range and does not hold 1.5, and MUST NOT change the file

#### Scenario: One bad value stops the whole save

- **WHEN** a `PUT` sets `ocr_routing_unit` to `page` and `ocr_engine_primary` to `../x`
- **THEN** the server MUST answer 400 and the file MUST hold neither value

#### Scenario: Uninstalled reader

- **WHEN** `pypdfium2` is not installed and a `PUT` sets `pdf_reader` to `pypdfium2`
- **THEN** the server MUST answer 400 "pdf_reader: This PDF reader is not installed. Install its package, then save again." and MUST NOT change the file

#### Scenario: Unprovisioned engine is allowed

- **WHEN** a `PUT` sets `ocr_engine_primary` to a valid name that has no folder under the engines folder
- **THEN** the server MUST answer 200, the file MUST hold the name, and the engine entry MUST report `available` false with the reason

### Requirement: The Chat section sets the claim check judge

The Chat section SHALL show a "Claim check judge" block under the Chat choice. The block SHALL show the judge provider and the judge model from `GET /v1/settings/judge` as setting rows with their source. An alias SHALL show with the provider it resolves to, for example "cloud (OpenRouter)". An empty model SHALL show "Not set" and the sentence "Claim checks are skipped until you set a judge model." When the choice is not locked, the block SHALL offer Edit, and SHALL offer Remove when the source is `config-file`. Edit SHALL open the same provider select, model name field, List models and Test actions as the Chat choice, filled with the current values, with Save and Cancel. Save SHALL be disabled while the model name is empty. When the choice is locked, the block SHALL name the variable and where it is set, and SHALL offer no Edit or Remove. The block SHALL state that the judge runs only for collections whose profile turns on "Check claims", and that a profile that sets its own judge overrides this choice. When the selected judge provider is cloud, the block SHALL state that claims and cited passages are sent off this machine.

#### Scenario: Default judge shown

- **WHEN** no source sets the judge
- **THEN** the block MUST show "cloud (OpenRouter)" with "default", the model "Not set" with "default", the skipped-checks sentence, and Edit, and MUST NOT offer Remove

#### Scenario: Edit opens filled

- **WHEN** `omrs.jsonc` sets the judge to `openrouter` and `openai/gpt-5-mini` and the user presses Edit
- **THEN** the provider select MUST show OpenRouter and the model field MUST hold `openai/gpt-5-mini`

#### Scenario: Pick a judge model from the list

- **WHEN** the user presses Edit, selects Ollama, presses List models and picks `qwen3:4b`
- **THEN** the model name field MUST hold `qwen3:4b` and nothing MUST be saved until the user presses Save

#### Scenario: Remove the judge

- **WHEN** the judge comes from `omrs.jsonc` and the user presses Remove
- **THEN** the page MUST send the clear request and MUST show the default judge with the source "default"

#### Scenario: Locked judge

- **WHEN** `.env` sets `ANSWER__VERIFY_PROVIDER`
- **THEN** the block MUST show the judge as locked, name the variable and `.env`, and offer no Edit or Remove

#### Scenario: Narrow screen

- **WHEN** the Chat section shows at 390 px wide
- **THEN** the judge rows and the form MUST fit with no horizontal page scroll
