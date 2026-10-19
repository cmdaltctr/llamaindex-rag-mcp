# Spec Delta

## MODIFIED Requirements

### Requirement: Server settings and sources

The server SHALL have the settings `llamacpp_server_binary` (env `LLAMACPP_SERVER_BINARY`), `llamacpp_server_model` (env `LLAMACPP_SERVER_MODEL`) and `llamacpp_context_window` (env `LLAMACPP_CONTEXT_WINDOW`, default 16,384, range 2,048 to 262,144) and `llamacpp_idle_sleep_seconds` (env `LLAMACPP_IDLE_SLEEP_SECONDS`, default 300, range 0 to 86,400, 0 turns sleep off). Each SHALL be settable in `omrg.jsonc` under the same key name and in the llama.cpp card. A card save SHALL write `omrg.jsonc`. The source order of the provider settings SHALL apply: the environment and `.env` (both lock), then `omrg.jsonc` (does not lock), then the default. A changed value SHALL apply at the next start of the owned server. The port SHALL come from `llamacpp_chat_url`.

#### Scenario: Config file sets all three

- **WHEN** `omrg.jsonc` holds the three keys
- **THEN** `GET /v1/llamacpp/server` MUST report each with source `config-file` and `locked` false

#### Scenario: Saved from the GUI

- **WHEN** no environment value exists and the user saves the three values
- **THEN** `omrg.jsonc` MUST hold them and the sources MUST be `config-file`

#### Scenario: Environment wins

- **WHEN** `LLAMACPP_CONTEXT_WINDOW=8192` is in the environment and the user saves another value
- **THEN** the server MUST return 409 and name the variable

#### Scenario: Context window range

- **WHEN** the user saves 1,000
- **THEN** the server MUST return 400 with the range and save nothing

#### Scenario: Program rule refused

- **WHEN** the user saves `~/.llama-app/llama` as the program
- **THEN** the server MUST return 400 with the program rule message, which starts "The program must be the absolute path of an executable file named llama-server", MUST NOT change the file, and the card MUST show that message in place of a generic error
