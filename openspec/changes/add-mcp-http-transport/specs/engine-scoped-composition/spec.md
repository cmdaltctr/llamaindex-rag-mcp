# engine-scoped-composition delta

## ADDED Requirements

### Requirement: The engine answers with a client completion or resolved rows

`Engine.answer` SHALL accept an optional client completion (a completion function, a source label of `client_mrtr` or `client_legacy`, and a round cap) and optional pre-resolved retrieval rows. A client completion SHALL replace only the answer model: claim verification SHALL stay with the engine's own verifier. The result SHALL report the client completion's source label, and synthesis SHALL run no more rounds than its cap. When rows are given, the engine SHALL NOT retrieve again. Without either argument, the result SHALL equal the result before this change.

#### Scenario: Client model, server verifier

- **WHEN** `answer` runs with a client completion and claim verification enabled
- **THEN** the answer MUST come from the client completion, verification MUST use the engine's verifier, and the completion source MUST be the client's label

#### Scenario: Round cap

- **WHEN** the answer block allows 8 rounds and the client completion's cap is 4
- **THEN** synthesis MUST run at most 4 rounds

#### Scenario: Resolved rows

- **WHEN** `answer` runs with rows
- **THEN** the engine MUST NOT run a retrieval

#### Scenario: Default unchanged

- **WHEN** `answer` runs with neither argument
- **THEN** the result MUST equal the result before this change for the same input and models

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
