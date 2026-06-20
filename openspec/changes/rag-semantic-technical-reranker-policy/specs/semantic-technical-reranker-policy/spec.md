## ADDED Requirements

### Requirement: Effective rerank policy resolution

The system SHALL resolve effective rerank behaviour from explicit caller intent and configured semantic/technical policy.

#### Scenario: Explicit rerank true overrides policy
- **GIVEN** `RERANK_ENABLED=false`
- **AND** `RERANK_ENABLED_FOR_SEMANTIC=false`
- **WHEN** search is called with `rerank=True`
- **THEN** the system SHALL apply reranking
- **AND** diagnostics SHALL indicate reranking was explicitly requested

#### Scenario: Explicit rerank false overrides policy
- **GIVEN** `RERANK_ENABLED=true`
- **WHEN** search is called with `rerank=False`
- **THEN** the system SHALL NOT apply reranking
- **AND** diagnostics SHALL indicate reranking was explicitly disabled

#### Scenario: Omitted rerank follows global default
- **GIVEN** `RERANK_ENABLED=true`
- **WHEN** search is called without an explicit rerank value
- **THEN** the system SHALL apply reranking
- **AND** diagnostics SHALL indicate reranking came from the global default

#### Scenario: Omitted rerank uses default off
- **GIVEN** `RERANK_ENABLED=false`
- **AND** `RERANK_ENABLED_FOR_SEMANTIC=false`
- **WHEN** search is called without an explicit rerank value
- **THEN** the system SHALL NOT apply reranking
- **AND** diagnostics SHALL indicate reranking was disabled by default

### Requirement: Semantic workload override

The system SHALL support a semantic-workload override that can enable reranking when global reranking is disabled and the workload is below the configured technical threshold.

#### Scenario: Semantic query enables policy reranking
- **GIVEN** `RERANK_ENABLED=false`
- **AND** `RERANK_ENABLED_FOR_SEMANTIC=true`
- **AND** `HARD_TECHNICAL_THRESHOLD=0.3`
- **WHEN** search is called without explicit rerank for a query classified as semantic
- **THEN** the system SHALL apply reranking
- **AND** diagnostics SHALL indicate reranking was enabled by semantic policy

#### Scenario: Technical query disables policy reranking
- **GIVEN** `RERANK_ENABLED=false`
- **AND** `RERANK_ENABLED_FOR_SEMANTIC=true`
- **WHEN** search is called without explicit rerank for a query classified as identifier-heavy
- **THEN** the system SHALL NOT apply reranking
- **AND** diagnostics SHALL indicate reranking was disabled by technical policy

#### Scenario: Technical workload fraction disables policy reranking
- **GIVEN** `RERANK_ENABLED=false`
- **AND** `RERANK_ENABLED_FOR_SEMANTIC=true`
- **AND** `HARD_TECHNICAL_THRESHOLD=0.3`
- **AND** workload metadata reports an identifier-heavy fraction of `0.3` or greater
- **WHEN** search is called without explicit rerank
- **THEN** the system SHALL NOT apply reranking
- **AND** diagnostics SHALL indicate the configured technical threshold was met

### Requirement: Public search surfaces follow config defaults

The direct retrieval API, MCP server search tool, and CLI search command SHALL follow `config.py` for omitted rerank behaviour.

#### Scenario: MCP omitted rerank follows policy resolver
- **GIVEN** `RERANK_ENABLED=false`
- **WHEN** `search_documents` is called without a rerank argument
- **THEN** the MCP search path SHALL use the effective rerank policy resolver
- **AND** it SHALL NOT hardcode reranking on

#### Scenario: CLI omitted rerank follows policy resolver
- **GIVEN** `RERANK_ENABLED=false`
- **WHEN** `cli search` is called without a rerank flag
- **THEN** the CLI search path SHALL use the effective rerank policy resolver
- **AND** it SHALL NOT hardcode reranking on
