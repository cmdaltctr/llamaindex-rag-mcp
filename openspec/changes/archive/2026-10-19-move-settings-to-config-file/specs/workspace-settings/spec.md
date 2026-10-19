# Spec Delta

## MODIFIED Requirements

### Requirement: Connections show provider configuration without secrets

The Providers section SHALL show one card for each entry of `GET /v1/connections`. Each card SHALL show the provider name, a Local or Cloud badge with text, the roles that use it, each editable field as a setting row, the read-only values (embedding address and models) as read-only rows, and the install command when the provider is not installed. A field from `env` SHALL show "Set in the environment. Change it there." with the variable name. A field from `dotenv` SHALL show "Set in .env. Change it there." with the variable name and the `.env` path. A field from `config-file` SHALL show "from omrg.jsonc" and SHALL stay editable. A key from `key-file` SHALL show "from key file" with the file path. A key from `keychain` SHALL show "in system keychain". The field source SHALL be one of `env`, `dotenv`, `config-file`, `keychain`, `key-file`, `default` and `none`. A key field SHALL show at most "Key set" and the last four characters. A Cloud card, and a card whose address is not on this machine, SHALL state that text leaves this machine. The section SHALL name the `omrg.jsonc` path and SHALL state that saves are written there.

#### Scenario: Roles follow the configuration

- **WHEN** `EMBED_PROVIDER` is `local`, `LOCAL_BACKEND` is `llamacpp` and the Chat provider is `ollama`
- **THEN** llama.cpp MUST list the embeddings role and Ollama MUST list the answers role

#### Scenario: Key is never exposed

- **WHEN** `OPENROUTER_API_KEY` is set in `.env`
- **THEN** the OpenRouter card MUST show "Set in .env. Change it there.", and no five consecutive characters of the key MUST appear in the response or the page

#### Scenario: Address from the config file

- **WHEN** the Ollama entry reports the source `config-file`
- **THEN** the card MUST show the address with "from omrg.jsonc" and MUST offer Edit

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

### Requirement: The Chat section chooses the Chat model

The Chat section SHALL show the Chat provider and model from `GET /v1/settings/chat` as setting rows with their source. When the choice is not locked, Edit SHALL open a provider select of the registered providers, each provider that is not ready marked with its reason in text, a model name field filled with the current model, a List models action that fills the field from the provider's list, a Test action for the typed choice, Save, Cancel and Clear. Save SHALL write `answer.provider` and `answer.model` to `omrg.jsonc`.

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

### Requirement: The Ollama card edits the context window

The Ollama card SHALL show "Context window (tokens)" as a setting row with its value and source. Edit SHALL open a number field filled with the current value, with the minimum 2,048 and the maximum 262,144. A locked field SHALL be read-only and SHALL state its lock. A saved value SHALL be written to `omrg.jsonc` and SHALL apply at once. The card SHALL state that the window does not apply to embedding models.

#### Scenario: Show default

- **WHEN** the user opens Settings > Providers with no value set
- **THEN** the Ollama card MUST show 16384 and the source "default"

#### Scenario: Save a value

- **WHEN** the user presses Edit, types 32768 and presses Save
- **THEN** the card MUST show 32768 and the source "from omrg.jsonc"

#### Scenario: Out of range

- **WHEN** the user types 1000
- **THEN** the card MUST show the friendly error "Enter 2,048 to 262,144." and MUST NOT save

#### Scenario: Locked by environment

- **WHEN** the field reports source `env` or `dotenv`
- **THEN** the card MUST show where it is set and MUST NOT offer Edit

### Requirement: The llama.cpp card shows a Local server panel

The llama.cpp card SHALL show a "Local server" panel with: the state as text and a badge (`stopped`, `starting`, `running` or `failed`); the fixed reason when the state is `failed`; setting rows for program path, model, context window and idle sleep, each with its value and source; and the buttons Start, Stop and Restart. The panel SHALL say: "omrg starts and stops only this server. It never touches a server you started yourself." The panel SHALL show "Restart to apply" when the values in force differ from the values of the running server. The panel SHALL NOT show output of the server. Start SHALL be disabled while the state is `starting` or `running`. Stop SHALL be disabled while the state is `stopped`. A locked field SHALL be read-only and SHALL state its lock. The panel SHALL state that the embedding server is not managed. When Start fails because a value is not set, the panel SHALL name the missing value.

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
- **THEN** it MUST show "omrg starts and stops only this server. It never touches a server you started yourself."

#### Scenario: Program and model need a credentials session

- **WHEN** the session lacks the `credentials` scope
- **THEN** the program path and model rows MUST be read-only and MUST state that the scope is needed

#### Scenario: Locked field

- **WHEN** `LLAMACPP_SERVER_MODEL` is in the environment
- **THEN** the model row MUST say where it is set and MUST NOT offer Edit

#### Scenario: Not configured

- **WHEN** no program path is set and the user presses Start
- **THEN** the panel MUST show the state `failed` and the line "Set the program path first."

## ADDED Requirements

### Requirement: Every setting is shown as a value and source row

Each editable setting on the Settings page SHALL show one row with its label, the value in force and its source in plain words ("from omrg.jsonc", "Set in .env", "Set in the environment", "default"). Edit SHALL open an input filled with the value in force, with Save and Cancel. The page SHALL NOT show an empty input for a field that has a value.

#### Scenario: Value from the file

- **WHEN** `omrg.jsonc` sets `llamacpp_server_binary` to `/opt/homebrew/bin/llama-server`
- **THEN** the row MUST show that path and "from omrg.jsonc", and no input MUST be visible until the user presses Edit

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

- **WHEN** a save returns 409 because `omrg.jsonc` changed
- **THEN** the page MUST show "omrg.jsonc changed on disk. Reload to see the new values." with a Reload action

### Requirement: A restart-only change offers a restart

After the user saves a setting that applies only after a restart, the page SHALL open a dialog that names the setting and offers "Restart now" and "Later". "Restart now" SHALL use the power menu restart. When the app runs in a terminal, the dialog SHALL show the command to restart instead of "Restart now". "Later" SHALL leave the row marked "Restart to apply".

#### Scenario: Port saved

- **WHEN** the app runs as the login item and the user saves port 9100
- **THEN** a dialog MUST say that port 9100 applies after a restart and MUST offer "Restart now" and "Later"

#### Scenario: Restart now

- **WHEN** the user presses "Restart now"
- **THEN** the page MUST send the power menu restart request and MUST tell the user to sign in again with `omrg web open`

#### Scenario: Foreground server

- **WHEN** the app runs in a terminal and the user saves port 9100
- **THEN** the dialog MUST show the restart command and MUST NOT offer "Restart now"

### Requirement: The Configuration section lists every setting

Settings SHALL have a Configuration section that lists every setting read-only, grouped by block, with its value in force, its source, and "Restart to apply" when its file value differs from the value the server started with. Keys SHALL show at most the last four characters. The section SHALL show the `omrg.jsonc` path with a copy action, and the problems found in the file. It SHALL take its data from `GET /v1/settings/configuration` (read scope).

#### Scenario: Engine setting edited by hand

- **WHEN** the user changes `retrieval.top_k` in `omrg.jsonc` while the server runs
- **THEN** the section MUST show the launch value, the source `config-file` and "Restart to apply", and MUST offer the restart dialog

#### Scenario: Problems listed

- **WHEN** `omrg.jsonc` holds an unknown key and an invalid value
- **THEN** the section MUST list both by key with one plain line each and MUST NOT show the invalid value

#### Scenario: Database rows not moved

- **WHEN** the server could not move saved settings into `omrg.jsonc`
- **THEN** the section MUST show "Saved settings could not be moved to omrg.jsonc" with the folder path
