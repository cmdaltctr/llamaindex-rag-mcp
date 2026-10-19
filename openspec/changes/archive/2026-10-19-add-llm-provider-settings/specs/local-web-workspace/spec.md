# Spec Delta

## MODIFIED Requirements

### Requirement: Workspace settings live in the workspace database

Settings that the web workspace changes at run time SHALL be stored in a `workspace_settings` key-value table of the workspace database, added by a schema migration. Only these keys SHALL exist, each validated on read: `mcp_http_enabled`, `web_port`, `upload_limit_mib`, `chat.provider`, `chat.model`, one `provider.<name>.<field>` key for each editable address or integer field of a registered LLM provider (including `provider.ollama.context_window`), `llamacpp.server_binary`, `llamacpp.server_model`, `llamacpp.context_window`, and one `provider.<name>.key_saved_at` flag for each provider whose key is in the keychain. A value that fails validation SHALL be treated as unset. API keys SHALL NOT be stored there. Other engine settings SHALL NOT be stored there.

#### Scenario: Invalid stored value

- **WHEN** `web_port` holds a value outside 1024 to 65535
- **THEN** the launch MUST ignore it and use the next source in the port order

#### Scenario: Damaged provider address

- **WHEN** `provider.ollama.base_url` holds a value that is not a valid provider address
- **THEN** the server MUST treat it as unset and use the next source

#### Scenario: No secret in the database

- **WHEN** the user saves an OpenRouter key
- **THEN** no row of the workspace database MUST contain the key

#### Scenario: Damaged context window

- **WHEN** `provider.ollama.context_window` holds 100 or a non-integer
- **THEN** the server MUST treat it as unset and use the next source

#### Scenario: Damaged server program

- **WHEN** `llamacpp.server_binary` holds a path that fails the program rules
- **THEN** the server MUST treat it as unset and MUST NOT start a process with it
