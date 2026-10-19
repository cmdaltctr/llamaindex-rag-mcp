# Spec Delta

## MODIFIED Requirements

### Requirement: Each provider value has one source

Each editable address and the Chat choice SHALL come from the first of these sources, highest first: the process environment (`env`), the `.env` file (`dotenv`), `omrg.jsonc` (`config-file`), the default (`default`). An API key SHALL come from the first of: the environment (`env`), `.env` (`dotenv`), a reference in `omrg.jsonc` (`config-file` for `env://`, `key-file` for `file://`, `keychain` for `keychain://`), the key file `secrets/<provider>.key` (`key-file`), else none (`none`). A value from `env` or `dotenv` SHALL lock its field: a write SHALL return 409 naming the variable and where it is set, and SHALL change nothing. A value from any other source SHALL NOT lock its field. The source `saved` SHALL NOT exist.

#### Scenario: Environment wins and locks

- **WHEN** `.env` sets `LLAMACPP_CHAT_URL` and the user saves another llama.cpp chat address
- **THEN** the server MUST return 409, the address in use MUST stay the `.env` value, and the field MUST report the source `dotenv`

#### Scenario: Saved value used

- **WHEN** neither the environment nor `.env` sets `OLLAMA_BASE_URL` and the user saves `http://gpu-box.local:11434`
- **THEN** `omrg.jsonc` MUST hold that address and the Ollama entry MUST report it with the source `config-file`

#### Scenario: Cleared value falls back

- **WHEN** the user clears the Ollama address
- **THEN** `omrg.jsonc` MUST no longer hold `ollama_base_url` and the Ollama entry MUST report the default address with the source `default`

#### Scenario: Key from the environment

- **WHEN** `OPENROUTER_API_KEY` is set in the environment
- **THEN** the OpenRouter key field MUST report the source `env` and locked, and a save or delete of the key MUST return 409

### Requirement: API keys live only in the system keychain

`PUT` and `DELETE /v1/connections/{provider}/key` (browser session, `credentials` scope) SHALL save a key to or remove it from the system keychain under the service `omrg` with the provider name as user name. A save SHALL also write `keychain://<provider>` as the provider's key reference in `omrg.jsonc`. A delete SHALL remove the keychain entry and that reference. The server SHALL use only a recommended backend (macOS Keychain, Windows Credential Locker, Secret Service). It SHALL NOT write a key to `.env`, the workspace database or any file.

#### Scenario: Key saved in the keychain

- **WHEN** a keychain is available and the user saves an OpenRouter key
- **THEN** the keychain MUST hold the key under the service `omrg` and the user name `openrouter`, `omrg.jsonc` MUST hold `keychain://openrouter`, and no file in the workspace, the config folder or the working directory MUST contain the key

#### Scenario: Key replaces a file reference

- **WHEN** `omrg.jsonc` holds a `file://` reference for OpenRouter and the user saves a key on the page
- **THEN** the reference MUST become `keychain://openrouter` and the key file MUST be unchanged

#### Scenario: Key removed

- **WHEN** the user deletes the OpenRouter key saved in the keychain and nothing else sets one
- **THEN** the keychain MUST no longer hold the key, `omrg.jsonc` MUST hold no OpenRouter key reference, and the entry MUST report the source `none`

#### Scenario: Bearer credential refused

- **WHEN** a request to save or delete a key carries a bearer credential instead of the browser session
- **THEN** the server MUST refuse it and MUST change nothing

### Requirement: No keychain means no saved key

When no usable keychain backend is available, the server SHALL refuse to save a key with 409 and SHALL NOT store it anywhere else. Each secret field SHALL report that no keychain is available and name both the key file path and the environment variable to use instead. The fail and null backends, any backend from the `keyrings.alt` package, and any backend with priority below 1 SHALL count as not available.

#### Scenario: Container without a keychain

- **WHEN** the server runs where no recommended keychain backend exists and the user saves an OpenRouter key
- **THEN** the server MUST return 409, MUST write the key nowhere, and the field MUST report no keychain and name `secrets/openrouter.key` and `OPENROUTER_API_KEY`

#### Scenario: Plaintext backend refused

- **WHEN** `PYTHON_KEYRING_BACKEND` selects the `keyrings.alt` plaintext file backend
- **THEN** the server MUST treat the keychain as not available and MUST NOT write a key through that backend

#### Scenario: Fail backend

- **WHEN** `keyring` reports the fail or null backend
- **THEN** the server MUST treat the keychain as not available

#### Scenario: Saved key missing

- **WHEN** `omrg.jsonc` holds `keychain://openrouter` but the keychain holds no `omrg` entry for it
- **THEN** the field MUST report that the key is missing from the keychain, and the provider MUST be treated as having no key

### Requirement: Saved values apply at once in the web server

A saved or hand-edited address, key or Chat choice SHALL apply in the `omrg web` process with no restart: to the answer model, the claim-verification judge and metadata extraction, including for MCP clients served over HTTP. Calls that already started SHALL finish with the old client; later calls SHALL use the new one. Embedding identity SHALL NOT change. `omrg` over stdio and the CLI SHALL read the same `omrg.jsonc` at launch, so they SHALL see page saves from their next launch.

#### Scenario: Answer uses the new address at once

- **WHEN** Chat uses Ollama and the user saves a new Ollama address
- **THEN** the next answer MUST send its model request to the new address with no restart

#### Scenario: Metadata extraction uses the new key at once

- **WHEN** metadata extraction uses OpenRouter and the user saves a new OpenRouter key
- **THEN** the next ingest MUST send the new key, and an ingest that started before the save MUST finish with the old key

#### Scenario: Stdio server unchanged

- **WHEN** a stdio server is running and the user saves a new Ollama address in the web workspace
- **THEN** the running stdio server MUST keep the address it read at launch

#### Scenario: Stdio server sees a page save at its next launch

- **WHEN** the user saves an OpenRouter key in the web workspace and then starts `omrg` over stdio with no key in the environment or `.env`
- **THEN** the stdio server MUST use the key through the `keychain://openrouter` reference

## ADDED Requirements

### Requirement: Key references and key files do not lock the key field

A key from a key file, implicit or referenced, or from an `env://` reference SHALL NOT lock its field. A key saved on the page SHALL replace the reference with `keychain://<provider>`. `PUT` and `DELETE /v1/connections/{provider}/key` SHALL NOT return 409 only because a key file or a reference exists. The page SHALL NOT delete or change a key file.

#### Scenario: Page key overrides the key file

- **WHEN** `secrets/openrouter.key` holds a key and the user saves a different key on the page
- **THEN** the OpenRouter key field MUST report the source `keychain` and the saved key MUST be used

#### Scenario: Removing the page key falls back

- **WHEN** the user removes the OpenRouter key saved on the page and `secrets/openrouter.key` exists
- **THEN** the OpenRouter key field MUST report the source `key-file`

#### Scenario: Config file reference does not lock

- **WHEN** `omrg.jsonc` holds `env://MY_ROUTER_KEY` for OpenRouter and the user saves a key on the page
- **THEN** the server MUST save it, and the reference MUST become `keychain://openrouter`

### Requirement: The CLI and the stdio server share the page's settings

The `config/` package SHALL read the user config folder, and the composition root SHALL resolve its key references, so the CLI, the stdio MCP server and the web server SHALL use the same values from it, including values saved on the Settings page.

#### Scenario: Stdio uses the config folder

- **WHEN** `omrg.jsonc` sets `ollama_base_url` and the user starts `omrg` over stdio
- **THEN** the stdio server MUST use that address

#### Scenario: CLI uses a key file

- **WHEN** `secrets/openrouter.key` exists and the user runs a CLI command that needs the OpenRouter key
- **THEN** the CLI MUST use that key

#### Scenario: Page save reaches the CLI

- **WHEN** the user saves an address in the web workspace and then starts the CLI
- **THEN** the CLI MUST use the saved address

## REMOVED Requirements

### Requirement: The key file does not lock the key field

**Reason**: Its scenario "Config file locks" no longer holds: a value in `omrg.jsonc` does not lock (ADR-087).
**Migration**: Replaced by "Key references and key files do not lock the key field".

### Requirement: The CLI and the stdio server read the user config folder

**Reason**: Its scenario "Saved web value stays web-only" no longer holds: page saves go to `omrg.jsonc`, which every process reads.
**Migration**: Replaced by "The CLI and the stdio server share the page's settings".

### Requirement: The user config folder is read-only

**Reason**: The Settings page now writes `omrg.jsonc`, as OMMS writes `omms.jsonc` (ADR-087).
**Migration**: The folder location rules move to `settings-file` ("The user config folder location"). Write rules are in `settings-file` ("The Settings page writes omrg.jsonc").

### Requirement: omrg.jsonc holds non-secret values and key references

**Reason**: `omrg.jsonc` now holds every setting, and a value in it no longer locks its field.
**Migration**: See `settings-file`: "omrg.jsonc accepts every setting", "Key fields hold references only" and "Problems in omrg.jsonc do not stop the server".
