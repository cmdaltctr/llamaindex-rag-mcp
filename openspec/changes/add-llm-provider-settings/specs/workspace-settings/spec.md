# Spec Delta

## MODIFIED Requirements

### Requirement: Settings is split into sections

The Settings view SHALL offer the sections Appearance, Providers, Chat, MCP, Server log, Runtime and Workspace, switched with chip buttons, with one section shown at a time. Each section SHALL have the address `#/settings/<section>` (`appearance`, `providers`, `chat`, `mcp`, `log`, `runtime`, `workspace`). Selecting a chip SHALL rewrite the address. `#/settings` SHALL show Appearance.

#### Scenario: Switch section

- **WHEN** the user selects the Server log chip
- **THEN** only the Server log section MUST show, the Server log chip MUST be marked selected, and the address MUST read `#/settings/log`

#### Scenario: Open a section from a link

- **WHEN** the app opens at `#/settings/chat`
- **THEN** only the Chat section MUST show and the Chat chip MUST be marked selected

### Requirement: Connections show provider configuration without secrets

The Providers section SHALL show one card for each entry of `GET /v1/connections`. Each card SHALL show the provider name, a Local or Cloud badge with text, the roles that use it, each editable field with its source, the read-only values (embedding address and models) marked as read-only, and the install command when the provider is not installed. A field from `env` SHALL show "Set from environment (read-only here)" with the variable name. A key field SHALL show at most "Key set" and the last four characters. A Cloud card, and a card whose address is not on this machine, SHALL state that text leaves this machine. The section SHALL state that saved values apply at once to this web server only.

#### Scenario: Roles follow the configuration

- **WHEN** `EMBED_PROVIDER` is `local`, `LOCAL_BACKEND` is `llamacpp` and the Chat provider is `ollama`
- **THEN** llama.cpp MUST list the embeddings role and Ollama MUST list the answers role

#### Scenario: Key is never exposed

- **WHEN** `OPENROUTER_API_KEY` is set in `.env`
- **THEN** the OpenRouter card MUST show "Set from environment (read-only here)", and no five consecutive characters of the key MUST appear in the response or the page

#### Scenario: Save an address

- **WHEN** the Ollama address is not locked and the user types a new address and presses Save
- **THEN** the card MUST show the address and the source the server returns after the save

#### Scenario: Replace a key

- **WHEN** the user types a new OpenRouter key and presses Save key
- **THEN** the key input MUST be emptied, the card MUST show "Key set" with the last four characters and the source keychain, and the page MUST NOT show the key again

#### Scenario: Optional key

- **WHEN** the `openai_compatible` entry marks its key field as optional and no key is set
- **THEN** the card MUST show the key field as optional, MUST NOT show an error, and the Chat section MUST allow choosing `openai_compatible`

#### Scenario: Provider not installed

- **WHEN** the `anthropic` entry reports that its package is not installed
- **THEN** the card MUST show the install command `uv sync --extra anthropic`, and the Chat section MUST mark `anthropic` as not ready with the reason in text

#### Scenario: No keychain

- **WHEN** the server reports that no keychain is available
- **THEN** the key field MUST show one plain line that says so and names the environment variable to set, and MUST offer no key input

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

## ADDED Requirements

### Requirement: The Chat section chooses the Chat model

The Chat section SHALL show the Chat provider and model from `GET /v1/settings/chat` with their source. When the choice is not locked, it SHALL offer a provider select of the registered providers, each provider that is not ready marked with its reason in text, a free-text model name field, a List models action that fills the field from the provider's list, a Test action for the typed choice, Save and Clear.

#### Scenario: Pick a model from the list

- **WHEN** the user selects Ollama, presses List models and picks `qwen3:4b`
- **THEN** the model name field MUST hold `qwen3:4b` and nothing MUST be saved until the user presses Save

#### Scenario: Type a model name

- **WHEN** the user selects OpenRouter, types `openai/gpt-4o-mini` and presses Save
- **THEN** the section MUST show the choice and the source saved that the server returns

#### Scenario: Locked choice

- **WHEN** `.env` sets `ANSWER__PROVIDER`
- **THEN** the section MUST show the choice as locked, name the variable to remove, and offer no Save action

#### Scenario: Test result

- **WHEN** the user presses Test and the server reports ok false with the reason timeout
- **THEN** the section MUST show the failure as a badge with text and one plain sentence, and MUST NOT show provider text

### Requirement: The Chat section says where the choice applies

The Chat section SHALL state that the choice also answers MCP clients of this web server that cannot supply their own model, that metadata extraction keeps its own model, and that `omrg` over stdio and the CLI read `.env` only. When the selected provider is cloud, the section SHALL state that questions and retrieved passages leave this machine.

#### Scenario: Cloud choice warns

- **WHEN** the user selects OpenRouter in the Chat section
- **THEN** the section MUST state that questions and retrieved passages are sent to openrouter.ai

#### Scenario: Local choice

- **WHEN** the user selects Ollama with an address on this machine
- **THEN** the section MUST NOT show the cloud statement
