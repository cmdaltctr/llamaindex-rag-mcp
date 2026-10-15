# workspace-settings delta

## Purpose

A Settings area that holds the workspace-wide controls and information that belong to no other view: appearance, provider connections, MCP access, the live server log, runtime capabilities and workspace details.

## ADDED Requirements

### Requirement: Settings is split into sections

The Settings view SHALL offer the sections Appearance, Connections, MCP, Server log, Runtime and Workspace, switched with chip buttons, with one section shown at a time.

#### Scenario: Switch section

- **WHEN** the user selects the Server log chip
- **THEN** only the Server log section MUST show and the Server log chip MUST be marked selected

### Requirement: Connections show provider configuration without secrets

The Connections section SHALL list the Ollama, llama.cpp and OpenRouter providers from `GET /v1/connections`, each with its endpoint URLs, configured model names, whether a key is set, and the roles that use it (embeddings, answers, metadata extraction, claim verification), resolved by the same rules the server uses at startup. The response and the page SHALL NOT contain any key value. The response SHALL include `config_dir`, the server's working directory whose `.env` the settings read. The section SHALL state that the values come from `<config_dir>/.env` and that a change needs a server restart, and SHALL offer no edit control.

#### Scenario: Roles follow the configuration

- **WHEN** `EMBED_PROVIDER` is `local`, `LOCAL_BACKEND` is `llamacpp` and `ANSWER__PROVIDER` is `ollama`
- **THEN** llama.cpp MUST list the embeddings role and Ollama MUST list the answers role

#### Scenario: Key is never exposed

- **WHEN** `OPENROUTER_API_KEY` is set
- **THEN** the OpenRouter entry MUST show that a key is set, and the key value MUST NOT appear in the response or the page

### Requirement: A connection test runs only on request

Each provider entry SHALL offer a Test action that calls `POST /v1/connections/{provider}/test`, which sends one model-list request with a 5-second timeout and returns whether the provider was reachable and a reason from a fixed set (`refused`, `timeout`, `unauthorised`, `http-<status>`, `not-configured`). The server SHALL NOT return response bodies or exception text, and SHALL NOT contact any provider unless a test is requested.

#### Scenario: Local provider down

- **WHEN** the user tests Ollama and nothing listens on its URL
- **THEN** the entry MUST show not reachable with the reason refused, stated in text with a badge

#### Scenario: No background cloud call

- **WHEN** the user opens Connections and presses no Test action
- **THEN** the server MUST NOT send any request to OpenRouter

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

The MCP section SHALL show a copyable stdio client configuration that starts `omrg` with `uv run --directory <project>`, where `<project>` is `config_dir` from `GET /v1/connections`, so the client's process reads the same `.env`. It SHALL also show, through the endpoints of the `add-mcp-http-transport` change only: an on/off switch for MCP over HTTP, the HTTP client configuration with the server's `/mcp` URL, token create, rotate and revoke with a new token shown once, and the saved web port that applies on the next launch.

#### Scenario: Copy stdio configuration

- **WHEN** the user copies the stdio configuration
- **THEN** the clipboard MUST hold a client configuration that runs `uv run --directory <project> omrg` with `config_dir` as `<project>`

#### Scenario: Switch reflects the server

- **WHEN** the server reports MCP over HTTP as off and the user turns the switch on
- **THEN** the section MUST show the state the server returns after the change, not an assumed state

#### Scenario: Token shown once

- **WHEN** the user creates the MCP token and then leaves and reopens the MCP section
- **THEN** the token MUST show with a copy action after creation and MUST NOT show after reopening
