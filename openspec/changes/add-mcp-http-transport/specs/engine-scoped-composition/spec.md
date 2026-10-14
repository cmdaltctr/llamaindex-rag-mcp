# engine-scoped-composition delta

## MODIFIED Requirements

### Requirement: The server startup path is one caller of the engine

`ensure_runtime_setup()` SHALL remain available as the startup path for the CLI and the watcher and SHALL be implemented in terms of the engine: it constructs the default engine from the environment and installs it as the process default for those transports. The MCP server SHALL NOT call it; the MCP lifespan constructs or receives its Engine directly.

#### Scenario: Existing transports are unchanged

- **WHEN** the MCP server, CLI or watcher starts
- **THEN** it SHALL obtain a working engine
- **AND** its tools and commands SHALL return the same results as before this change

#### Scenario: Optional answering is lazy

- **GIVEN** an Engine whose retrieval dependencies are available but whose
  answer provider or optional extra is absent
- **WHEN** the Engine is constructed and `search()` is used
- **THEN** construction and search MUST succeed
- **AND** the actionable failure MUST occur only if `answer()` is used

#### Scenario: The process default is a convenience, not a requirement

- **WHEN** a caller constructs and uses an engine directly
- **THEN** it SHALL work without the process default having been installed
- **AND** a full ingest/search path SHALL remain correct when the LlamaIndex
  global embedder is a throwing sentinel

#### Scenario: Startup remains fail-fast

- **WHEN** startup encounters an invalid provider, store or strategy name
- **THEN** it SHALL fail with the existing actionable error
- **AND** SHALL NOT start with a partially composed runtime
