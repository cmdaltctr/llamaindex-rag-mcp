# Spec Delta

## Purpose

Lets the user set language model (LLM) provider addresses, API keys and the Chat model from the web workspace. Covers where each value comes from, how keys stay secret, how a saved value takes effect at once, and how the server tests a provider and lists its models.

## ADDED Requirements

### Requirement: Provider cards follow the LLM provider registry

`GET /v1/connections` SHALL return one entry for each provider in the LLM provider registry, in registration order. Each entry SHALL carry the provider's display name, whether it is local or cloud, whether its optional package is installed with the install command when it is not, its editable fields, its read-only values, and the roles that use it. Adding a provider SHALL need only a new provider module and one registry line.

#### Scenario: Registered providers only

- **WHEN** the registry holds `ollama`, `llamacpp` and `openrouter`
- **THEN** the response MUST hold exactly three entries, for those three providers

#### Scenario: Optional package missing

- **WHEN** the package that the `llamacpp` provider needs is not installed
- **THEN** the `llamacpp` entry MUST report it as not installed and MUST give the install command `uv sync --extra llamacpp`

#### Scenario: Cloud provider marked

- **WHEN** the response holds the `openrouter` entry
- **THEN** the entry MUST mark the provider as cloud

### Requirement: Each provider value has one source

Each editable address and the Chat choice SHALL come from the first of: the process environment or `.env` (source `env`), the value saved in the workspace (`saved`), the default (`default`). An API key SHALL come from the environment or `.env` (`env`), then the system keychain (`keychain`), else none (`none`). A value from `env` SHALL lock its field: a write SHALL return 409 naming the variable to remove, and SHALL change nothing.

#### Scenario: Environment wins and locks

- **WHEN** `.env` sets `LLAMACPP_CHAT_URL` and the user saves another llama.cpp chat address
- **THEN** the server MUST return 409, the address in use MUST stay the `.env` value, and the field MUST report the source `env`

#### Scenario: Saved value used

- **WHEN** neither the environment nor `.env` sets `OLLAMA_BASE_URL` and the user saves `http://gpu-box.local:11434`
- **THEN** the Ollama entry MUST report that address with the source `saved`

#### Scenario: Cleared value falls back

- **WHEN** the user clears the saved Ollama address
- **THEN** the Ollama entry MUST report the default address with the source `default`

#### Scenario: Key from the environment

- **WHEN** `OPENROUTER_API_KEY` is set in the environment
- **THEN** the OpenRouter key field MUST report the source `env` and locked, and a save or delete of the key MUST return 409

### Requirement: API keys live only in the system keychain

`PUT` and `DELETE /v1/connections/{provider}/key` (browser session, `credentials` scope) SHALL save a key to or remove it from the system keychain under the service `omrg` with the provider name as user name. The server SHALL use only a recommended backend (macOS Keychain, Windows Credential Locker, Secret Service). It SHALL NOT write a key to `.env`, the workspace database or any file.

#### Scenario: Key saved in the keychain

- **WHEN** a keychain is available and the user saves an OpenRouter key
- **THEN** the keychain MUST hold the key under the service `omrg` and the user name `openrouter`, the workspace database MUST hold only the save time, and no file in the workspace or the working directory MUST contain the key

#### Scenario: Key removed

- **WHEN** the user deletes the saved OpenRouter key and the environment sets none
- **THEN** the keychain MUST no longer hold the key and the entry MUST report the source `none`

#### Scenario: Bearer credential refused

- **WHEN** a request to save or delete a key carries a bearer credential instead of the browser session
- **THEN** the server MUST refuse it and MUST change nothing

### Requirement: No keychain means no saved key

When no usable keychain backend is available, the server SHALL refuse to save a key with 409 and SHALL NOT store it anywhere else. Each secret field SHALL report that no keychain is available and name the environment variable to set instead. The fail and null backends, any backend from the `keyrings.alt` package, and any backend with priority below 1 SHALL count as not available.

#### Scenario: Container without a keychain

- **WHEN** the server runs where no recommended keychain backend exists and the user saves an OpenRouter key
- **THEN** the server MUST return 409, MUST write the key nowhere, and the field MUST report no keychain and name `OPENROUTER_API_KEY`

#### Scenario: Plaintext backend refused

- **WHEN** `PYTHON_KEYRING_BACKEND` selects the `keyrings.alt` plaintext file backend
- **THEN** the server MUST treat the keychain as not available and MUST NOT write a key through that backend

#### Scenario: Fail backend

- **WHEN** `keyring` reports the fail or null backend
- **THEN** the server MUST treat the keychain as not available

#### Scenario: Saved key missing

- **WHEN** the database records a key save but the keychain holds no `omrg` entry for the provider at start
- **THEN** the field MUST report that the saved key is missing from the keychain, and the provider MUST be treated as having no key

### Requirement: A key is never returned and never logged

No response SHALL contain more of a key than its last four characters. A key field SHALL report whether a key is set, its source, when it was saved, and the last four characters only when the key has 16 or more characters. From the moment the server accepts a key, the server log, the log panel, the log stream and the error text of answer results SHALL NOT contain it. A replaced key SHALL stay redacted until the server stops.

#### Scenario: Only the last four characters

- **WHEN** the user saves a 64-character OpenRouter key and reads `GET /v1/connections`
- **THEN** the key field MUST hold the last four characters of the key, and no response body MUST contain any five consecutive characters of the key

#### Scenario: Short key shows no characters

- **WHEN** the key in use has fewer than 16 characters
- **THEN** the key field MUST report that a key is set and MUST hold no characters of it

#### Scenario: New key in a log line

- **WHEN** the user saves an OpenRouter key and a later log message contains that key
- **THEN** the buffered record, `GET /v1/logs` and the log stream MUST show the message with the key removed

#### Scenario: Replaced key still redacted

- **WHEN** the user replaces a saved key and a later log message contains the old key
- **THEN** the record MUST show the message with the old key removed

### Requirement: Provider addresses are validated

A provider address SHALL be an absolute `http` or `https` URL with a host, at most 2,048 characters, with no user name, password, query or fragment. The server SHALL check this before it saves an address or sends a request to it. Loopback and local network hosts SHALL be allowed. A rejected address SHALL get 400 with a message that names the rule and does not repeat the value.

#### Scenario: Wrong scheme

- **WHEN** the user saves the Ollama address `file:///etc/passwd`
- **THEN** the server MUST return 400, MUST save nothing and MUST send no request

#### Scenario: Credentials in the address

- **WHEN** the user tests the llama.cpp chat address `http://user:pass@localhost:8081/v1`
- **THEN** the server MUST return 400 and MUST send no request

#### Scenario: Local network host allowed

- **WHEN** the user saves the Ollama address `http://192.168.1.20:11434`
- **THEN** the server MUST save it

### Requirement: Saved values apply at once in the web server

A saved address, key or Chat choice SHALL apply in the `omrg web` process with no restart: to the answer model, the claim-verification judge and metadata extraction, including for MCP clients served over HTTP. Calls that already started SHALL finish with the old client; later calls SHALL use the new one. Embedding identity SHALL NOT change. `omrg` over stdio, the CLI and experiment contexts SHALL read `.env` only.

#### Scenario: Answer uses the new address at once

- **WHEN** Chat uses Ollama and the user saves a new Ollama address
- **THEN** the next answer MUST send its model request to the new address with no restart

#### Scenario: Metadata extraction uses the new key at once

- **WHEN** metadata extraction uses OpenRouter and the user saves a new OpenRouter key
- **THEN** the next ingest MUST send the new key, and an ingest that started before the save MUST finish with the old key

#### Scenario: Stdio server unchanged

- **WHEN** the user saves an OpenRouter key in the web workspace and starts `omrg` over stdio with no key in `.env`
- **THEN** the stdio server MUST report no OpenRouter key

### Requirement: The Ollama address is locked while Ollama makes embeddings

When any embedding use of the server names Ollama, the Ollama address SHALL be locked with a reason that says embeddings use it. A write to it SHALL return 409 and change nothing. The running embedder keeps the address it was built with, so a change would split the two roles and could change a collection's vectors.

#### Scenario: Ollama makes embeddings

- **WHEN** the embeddings role resolves to Ollama and the user saves a new Ollama address
- **THEN** the server MUST return 409 naming the embeddings role, and the address in use MUST NOT change

### Requirement: The Chat status says whether Chat is ready

`GET /v1/settings/chat` SHALL return the Chat provider, the model name, their source, whether the choice is locked, and whether Chat is ready. When Chat is not ready, it SHALL give a reason from a fixed set: `disabled`, `unknown-provider`, `not-installed`, `not-configured`. The server SHALL NOT contact a provider for this route.

#### Scenario: Not ready without a key

- **WHEN** the Chat provider is `openrouter` and no OpenRouter key is set
- **THEN** `GET /v1/settings/chat` MUST report ready false with the reason `not-configured`

#### Scenario: Answering turned off

- **WHEN** `ANSWER__ENABLED` is false
- **THEN** `GET /v1/settings/chat` MUST report ready false with the reason `disabled`

#### Scenario: No provider request

- **WHEN** the Chat section or the Chat view reads `GET /v1/settings/chat`
- **THEN** the server MUST NOT send any request to a provider

### Requirement: The Chat choice sets the web server's answer model

`PUT /v1/settings/chat` (browser session, `manage` scope) SHALL save a registered provider and a model name of 1 to 200 characters with no control characters, or clear both. The saved choice SHALL be the answer model of the web server from the next answer. The route SHALL return 409 and change nothing when `ANSWER__PROVIDER` or `ANSWER__MODEL` comes from the environment or `.env`.

#### Scenario: Choose a cloud model

- **WHEN** the user saves the provider `openrouter` and the model `openai/gpt-4o-mini` and an OpenRouter key is set
- **THEN** `GET /v1/settings/chat` MUST report that choice with the source `saved` and ready true, and the next answer MUST use that model

#### Scenario: Unknown provider refused

- **WHEN** the user saves the provider `gemini`, which the registry does not hold
- **THEN** the server MUST return 400 and MUST save nothing

#### Scenario: Locked by the environment

- **WHEN** `.env` sets `ANSWER__MODEL` and the user saves another model
- **THEN** the server MUST return 409 naming `ANSWER__MODEL`, and the answer model MUST NOT change

### Requirement: A Chat model test runs only on request

`POST /v1/settings/chat/test` (browser session, `manage` scope) SHALL build the model for the given provider and model name, or for the saved choice when the body names none, and send one short prompt with a 30-second limit. It SHALL return whether a non-empty reply came back, the time taken, and a reason from a fixed set (`refused`, `timeout`, `unauthorised`, `http-<status>`, `not-installed`, `not-configured`, `empty-reply`, `failed`). It SHALL NOT return reply or exception text.

#### Scenario: Model answers

- **WHEN** the user tests Ollama with the model `qwen3:4b` and Ollama replies
- **THEN** the result MUST report ok true with the time taken, and the saved Chat choice MUST NOT change, because a test never saves

#### Scenario: Unknown model name

- **WHEN** the provider answers the test prompt with HTTP status 404
- **THEN** the result MUST report ok false with the reason `http-404` and no provider text

### Requirement: The model list is fetched only on request

`POST /v1/connections/{provider}/models` (browser session, `manage` scope) SHALL send one model-list request to the provider, using typed values from the body when given and otherwise the values in use, with a 5-second limit. It SHALL return only model names: at most 1,000, sorted, each 1 to 200 characters with no control characters, and a flag when it cut the list. A failure SHALL return the reasons of the connection test. The server SHALL NOT save a typed value.

#### Scenario: Ollama lists its models

- **WHEN** the user asks for the Ollama models and Ollama holds `qwen3:4b` and `llama3.2:latest`
- **THEN** the result MUST list exactly those two names

#### Scenario: Provider down

- **WHEN** the user asks for the llama.cpp models and nothing listens at the chat address
- **THEN** the result MUST report not reachable with the reason `refused`
