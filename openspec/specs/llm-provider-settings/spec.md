# llm-provider-settings Specification

## Purpose
Lets the user set language model (LLM) provider addresses, API keys and the Chat model from the web workspace. Covers where each value comes from, how keys stay secret, how a saved value takes effect at once, and how the server tests a provider and lists its models.

## Requirements

### Requirement: Provider cards follow the LLM provider registry

`GET /v1/connections` SHALL return one entry for each provider in the LLM provider registry, in registration order. Each entry SHALL carry the provider's display name, whether it is local or cloud, whether its optional package is installed with the install command when it is not, its editable fields, its read-only values, and the roles that use it. Adding a provider SHALL need only a new provider module and one registry line.

#### Scenario: Registered providers only

- **WHEN** the registry holds `ollama`, `llamacpp`, `openrouter`, `openai_compatible` and `anthropic`
- **THEN** the response MUST hold exactly five entries, for those five providers, in that order

#### Scenario: Optional package missing

- **WHEN** the package that the `anthropic` provider needs is not installed
- **THEN** the `anthropic` entry MUST report it as not installed and MUST give the install command `uv sync --extra anthropic`

#### Scenario: OpenAI-like package is in the base install

- **WHEN** the base install has no extra and the response holds the `llamacpp`, `openrouter` and `openai_compatible` entries
- **THEN** each of the three entries MUST report the provider as installed, because the LlamaIndex OpenAI-like packages are base dependencies

#### Scenario: Cloud provider marked

- **WHEN** the response holds the `openrouter`, `openai_compatible` or `anthropic` entry
- **THEN** the entry MUST mark the provider as cloud

#### Scenario: A new provider needs no other change

- **WHEN** a test registers a fake provider module with a descriptor and one registry line
- **THEN** the response MUST hold an entry for it, and no route, summary function or web file MUST need a change

### Requirement: The registry lists the OpenAI-compatible and Anthropic Chat providers

The LLM provider registry SHALL hold two Chat providers in addition to `ollama`, `llamacpp` and `openrouter`, each as one provider module, one `register()` line and one connection descriptor. `openai_compatible` (display name "OpenAI-compatible") SHALL serve the answers role only. It SHALL have an editable address field (`OPENAI_COMPATIBLE_BASE_URL`, default `https://api.openai.com/v1`) and an optional secret field (`OPENAI_COMPATIBLE_API_KEY`). `anthropic` (display name "Anthropic") SHALL serve the answers role only. It SHALL have one required secret field (`ANTHROPIC_API_KEY`) and the fixed address `https://api.anthropic.com`. Neither provider SHALL appear in the embeddings or metadata roles.

#### Scenario: OpenAI-compatible entry

- **WHEN** the response holds the `openai_compatible` entry
- **THEN** the entry MUST list the roles as answers only, an editable address with the default `https://api.openai.com/v1`, and a secret field that is marked optional

#### Scenario: Anthropic entry

- **WHEN** the response holds the `anthropic` entry
- **THEN** the entry MUST list the roles as answers only, one secret field that is marked required, and no editable address

#### Scenario: Remote or loopback address

- **WHEN** the user saves the `openai_compatible` address `http://localhost:1234/v1` and later saves `https://api.together.xyz/v1`
- **THEN** the server MUST accept both, the second entry MUST be treated as not on this machine, and the card MUST state that text leaves this machine

### Requirement: An optional key does not block Chat

A secret field marked optional SHALL NOT make Chat not ready when it is empty. The `openai_compatible` key SHALL be optional because servers such as LM Studio and vLLM need none. The server SHALL send a bearer credential to that provider only when a key is set, and SHALL send it only to the address saved or typed for that provider.

#### Scenario: Chat ready without a key

- **WHEN** the Chat provider is `openai_compatible`, the address is `http://localhost:1234/v1` and no key is set
- **THEN** `GET /v1/settings/chat` MUST report ready true

#### Scenario: Key sent only to its own address

- **WHEN** an `openai_compatible` key is set and the user tests the provider
- **THEN** the request MUST go only to the `openai_compatible` address, and no request to another provider MUST carry that key

### Requirement: A required key blocks Chat

A secret field that is not marked optional SHALL make Chat not ready while it is empty. For `anthropic`, `GET /v1/settings/chat` SHALL report ready false with the reason `not-configured` while no Anthropic key is set. The server SHALL send no request to Anthropic while the key is missing.

#### Scenario: Anthropic without a key

- **WHEN** the Chat provider is `anthropic` and no Anthropic key is set
- **THEN** `GET /v1/settings/chat` MUST report ready false with the reason `not-configured`

#### Scenario: Anthropic package missing

- **WHEN** the Chat provider is `anthropic` and the `anthropic` extra is not installed
- **THEN** `GET /v1/settings/chat` MUST report ready false with the reason `not-installed`

### Requirement: Provider tests send the right credentials

The connection test and the model list SHALL use the descriptor of the provider. For `openai_compatible` they SHALL send `GET {base_url}/models` and SHALL add an `Authorization: Bearer` header only when a key is set. For `anthropic` they SHALL send `GET https://api.anthropic.com/v1/models` with the headers `x-api-key` and `anthropic-version: 2023-06-01`, and SHALL send no request when no key is set; the result SHALL then report the reason `not-configured`.

#### Scenario: OpenAI-compatible test with a key

- **WHEN** an `openai_compatible` key is set and the user tests the provider
- **THEN** the request MUST be `GET {base_url}/models` with the bearer header

#### Scenario: OpenAI-compatible test without a key

- **WHEN** no `openai_compatible` key is set and the user tests the provider
- **THEN** the request MUST be `GET {base_url}/models` with no `Authorization` header

#### Scenario: Anthropic test headers

- **WHEN** an Anthropic key is set and the user tests the provider
- **THEN** the request MUST be `GET /v1/models` on `https://api.anthropic.com` with the headers `x-api-key` and `anthropic-version: 2023-06-01`

#### Scenario: Anthropic test without a key

- **WHEN** no Anthropic key is set and the user tests the provider
- **THEN** the server MUST send no request and the result MUST report not reachable with the reason `not-configured`

### Requirement: Secret rules apply to every secret field

The rules for keychain storage, the environment lock, redaction, the last four characters and live application SHALL apply to every secret field of every registered provider, driven by the descriptors. A new provider SHALL NOT need a change to the redaction set, the editable-field set, the locking code or the readiness check beyond its own descriptor. This SHALL include `OPENAI_COMPATIBLE_API_KEY` and `ANTHROPIC_API_KEY`.

#### Scenario: Anthropic key in the keychain

- **WHEN** a keychain is available and the user saves an Anthropic key
- **THEN** the keychain MUST hold it under the service `omrg` and the user name `anthropic`, and no file or database row MUST contain it

#### Scenario: Anthropic key redacted

- **WHEN** the user saves an Anthropic key whose text starts with `sk-ant-` and a later log message contains it
- **THEN** the buffered record, `GET /v1/logs` and the log stream MUST show the message with the key removed

#### Scenario: OpenAI-compatible key from the environment

- **WHEN** `OPENAI_COMPATIBLE_API_KEY` is set in the environment
- **THEN** the key field MUST report the source `env` and locked, and a save or delete of the key MUST return 409

#### Scenario: OpenAI-compatible key applies at once

- **WHEN** the Chat provider is `openai_compatible` and the user saves a new key
- **THEN** the next answer MUST send the new key to the saved address, and an answer that started before the save MUST finish with the old key

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

### Requirement: The Ollama address is locked while Ollama makes embeddings

When any embedding use of the server names Ollama, the Ollama address SHALL be locked with a reason that says embeddings use it. A write to it SHALL return 409 and change nothing. The running embedder keeps the address it was built with, so a change would split the two roles and could change a collection's vectors.

#### Scenario: Ollama makes embeddings

- **WHEN** the embeddings role resolves to Ollama and the user saves a new Ollama address
- **THEN** the server MUST return 409 naming the embeddings role, and the address in use MUST NOT change

### Requirement: The Chat status says whether Chat is ready

`GET /v1/settings/chat` SHALL return the Chat provider, the model name, their source, whether the choice is locked, and whether Chat is ready. When Chat is not ready, it SHALL give a reason from a fixed set: `disabled`, `unknown-provider`, `not-installed`, `not-configured` (a required value, such as a key that the provider needs, is missing). The server SHALL NOT contact a provider for this route.

#### Scenario: Not ready without a key

- **WHEN** the Chat provider is `openrouter` and no OpenRouter key is set
- **THEN** `GET /v1/settings/chat` MUST report ready false with the reason `not-configured`

#### Scenario: Registry providers other than the first three

- **WHEN** the Chat provider is `anthropic` or `openai_compatible`
- **THEN** `GET /v1/settings/chat` MUST decide readiness from the descriptor of that provider, with no branch on the provider name

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

### Requirement: A literal key in omrg.jsonc is ignored

A secret field in `omrg.jsonc` that holds a value which is not an `env://` or `file://` reference SHALL be ignored. The server SHALL log one warning that names the field and SHALL NOT log the value. The server SHALL NOT use the value.

#### Scenario: Literal key ignored

- **WHEN** `omrg.jsonc` sets the OpenRouter key to a literal string
- **THEN** the OpenRouter key field MUST NOT report the source `config-file`, the key MUST NOT be used, and the log MUST name the field and MUST NOT hold any part of the string

### Requirement: A file reference stays inside secrets

A `file://` reference SHALL resolve, after symlinks are followed, to a path inside the `secrets/` folder of the user config folder. A reference that resolves elsewhere SHALL be refused: the field SHALL give no value from the config file and the server SHALL log one warning that names the field.

#### Scenario: Reference inside secrets

- **WHEN** `omrg.jsonc` sets a key to `file://` followed by the absolute path of `secrets/router.key`
- **THEN** the server MUST read the key from that file

#### Scenario: Reference outside secrets

- **WHEN** the reference is `file:///etc/passwd` or uses `..` to leave `secrets/`
- **THEN** the server MUST NOT read the file and MUST log one warning that names the field

#### Scenario: Symlink leaves the folder

- **WHEN** the referenced file is a symlink to a path outside `secrets/`
- **THEN** the server MUST NOT read the file

### Requirement: Key files follow safety rules

`secrets/<provider>.key` SHALL hold one key for the provider whose registry name is the file name. The server SHALL read at most 4 KiB and SHALL strip surrounding whitespace. The server SHALL refuse a symlink that resolves outside the user config folder and SHALL refuse a path that is not a regular file. When a key file has a mode looser than 0600, or the `secrets/` folder has a mode looser than 0700, the server SHALL still read the key and SHALL log one warning with the path and the mode, and SHALL NOT log the content. The permission check SHALL be skipped on Windows. A key file SHALL apply to secret fields only.

#### Scenario: Key file read

- **WHEN** `secrets/openrouter.key` holds a key with a trailing newline and no other source sets the OpenRouter key
- **THEN** the OpenRouter key field MUST report set with the source `key-file`, and the key MUST be used without the newline

#### Scenario: File too large

- **WHEN** a key file holds more than 4 KiB
- **THEN** the server MUST NOT use it and MUST log one warning that names the path

#### Scenario: Symlink out of the folder

- **WHEN** `secrets/openrouter.key` is a symlink to a file outside the user config folder
- **THEN** the server MUST refuse it and MUST log one warning

#### Scenario: Not a regular file

- **WHEN** `secrets/openrouter.key` is a folder or a device
- **THEN** the server MUST refuse it

#### Scenario: Loose permissions

- **WHEN** a key file has mode 0644 on macOS or Linux
- **THEN** the server MUST use the key, and MUST log one warning that holds the path and the mode and no part of the key

#### Scenario: Unknown file name

- **WHEN** `secrets/` holds a file whose name is not a registered provider
- **THEN** the server MUST ignore it

### Requirement: Keys from the user config folder are redacted

A key that comes from the user config folder (a key file, or an `env://` or `file://` reference) SHALL join the redaction set exactly like a key from the environment. From the moment the server reads it, the server log, log panel, log stream and error text of answer results SHALL NOT contain it. A response SHALL hold at most the last four characters of it, and only when it has 16 or more characters.

#### Scenario: Key file key in a log line

- **WHEN** the server reads a key from `secrets/openrouter.key` and a later log message contains it
- **THEN** the buffered record, `GET /v1/logs` and the log stream MUST show the message with the key removed

#### Scenario: Only the last four characters

- **WHEN** a 64-character key comes from a key file and the user reads `GET /v1/connections`
- **THEN** no response body MUST contain any five consecutive characters of the key

### Requirement: Tests never read the real config folder

The test suite SHALL set `OMRG_CONFIG_DIR` to a temporary folder before any settings are resolved, so no test reads or depends on the real user config folder.

#### Scenario: Suite isolates the folder

- **WHEN** a test resolves settings while `~/.config/omrg/omrg.jsonc` exists on the machine
- **THEN** the test MUST NOT see any value from it

### Requirement: The connections summary names the config folder

`GET /v1/connections` SHALL return a top-level `user_config_dir` that names the user config folder with `~` for the home folder. The field `source` SHALL take one of `env`, `config-file`, `saved`, `keychain`, `key-file`, `default` and `none`. The response SHALL NOT contain a key from the folder beyond the last four characters.

#### Scenario: Folder named

- **WHEN** the user reads `GET /v1/connections` with the default folder
- **THEN** `user_config_dir` MUST read `~/.config/omrg`

#### Scenario: Source values

- **WHEN** an address comes from `omrg.jsonc` and a key from a key file
- **THEN** the address `source` MUST be `config-file` and the key `source` MUST be `key-file`

### Requirement: Ollama context window is a setting

The server SHALL have a setting `ollama_context_window`, an integer number of tokens. The default SHALL be 16,384. The allowed range SHALL be 2,048 to 262,144. The value SHALL come from the first source that holds one, highest first: environment `OLLAMA_CONTEXT_WINDOW` and `.env`, key `ollama_context_window` in `omrg.jsonc`, a value saved in the web workspace, the default. A value from the environment, `.env` or `omrg.jsonc` SHALL lock the field. A value outside the range SHALL be rejected with a message that names the rule and not the value. The setting SHALL NOT apply to embedding models.

#### Scenario: Default

- **WHEN** no source sets the Ollama context window
- **THEN** the effective value MUST be 16,384 and the source MUST be `default`

#### Scenario: Range

- **WHEN** the user saves 1,024 or 300,000
- **THEN** the server MUST return 400, MUST save nothing and MUST NOT repeat the value in the message

#### Scenario: Range edges

- **WHEN** the user saves 2,048 and then 262,144
- **THEN** the server MUST accept both

#### Scenario: Environment locks the field

- **WHEN** `OLLAMA_CONTEXT_WINDOW=8192` is in the environment and the user saves another value
- **THEN** the server MUST return 409 and name the variable, and the effective value MUST stay 8,192

#### Scenario: Config file locks the field

- **WHEN** `omrg.jsonc` holds `ollama_context_window` and the user saves another value
- **THEN** the server MUST return 409, and the source MUST be `config-file`

#### Scenario: Saved value used

- **WHEN** no environment or file value exists and the user saves 32,768
- **THEN** the effective value MUST be 32,768 and the source MUST be `saved`

#### Scenario: Invalid file value

- **WHEN** `omrg.jsonc` holds `ollama_context_window` of 100
- **THEN** the server MUST ignore the value, MUST log one warning that names the field and not the value, and MUST use the next source

### Requirement: The Ollama context window is sent on every Ollama call

The Chat answer model for Ollama SHALL pass the effective context window as `context_window` to the LlamaIndex Ollama client. The server SHALL NOT call `/api/show` to read the model maximum. Metadata extraction through Ollama SHALL send the effective context window as `options.num_ctx` on `POST /api/generate`. A saved value SHALL apply live: the next call SHALL use the new value, and a call already started SHALL finish with the old value.

#### Scenario: No model-maximum lookup

- **WHEN** Chat builds an Ollama answer model
- **THEN** the client MUST receive `context_window` equal to the effective value and the server MUST send no request to `/api/show`

#### Scenario: Large model maximum ignored

- **WHEN** the model reports a maximum of 262,144 tokens and the effective value is 16,384
- **THEN** the request to Ollama MUST carry `num_ctx` of 16,384

#### Scenario: Metadata extraction

- **WHEN** metadata extraction uses Ollama with an effective value of 8,192
- **THEN** the `POST /api/generate` body MUST hold `options.num_ctx` of 8,192

#### Scenario: Live apply

- **WHEN** the user saves 32,768 while Chat is open
- **THEN** the next answer MUST send `num_ctx` of 32,768 with no restart

#### Scenario: Embeddings unchanged

- **WHEN** the user saves a new Ollama context window
- **THEN** the embedding requests and the embedding identity of every collection MUST stay unchanged

### Requirement: Integer fields are a descriptor kind

A provider descriptor SHALL be able to declare an integer field with a minimum, a maximum and a default. The summary, the save route, the test route and the OpenAPI contract SHALL handle the field with no provider-name branch. `GET /v1/connections` SHALL return an integer field with `kind` `int`, the `value`, `min`, `max`, `source`, `locked` and `lock_reason`.

#### Scenario: Summary shape

- **WHEN** the user reads `GET /v1/connections`
- **THEN** the Ollama entry MUST hold a field `context_window` with `kind` `int`, `min` 2048, `max` 262144 and `value` 16384

#### Scenario: Non-integer refused

- **WHEN** the user saves `"abc"` or `16384.5` as the context window
- **THEN** the server MUST return 400

#### Scenario: Fake provider with an integer field

- **WHEN** a test registers a fake provider with an integer field
- **THEN** the card, the save route and the lock rules MUST work with no change outside the descriptor

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
