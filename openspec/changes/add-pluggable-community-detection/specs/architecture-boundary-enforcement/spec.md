## MODIFIED Requirements

### Requirement: Full-package import boundary coverage

The import-linter contract set SHALL cover every package under
`src/rag_mcp/`, not a subset. The business-layer contract SHALL name
`core.ingestion`, `core.retrieval`, `core.metadata`, `core.chunking`,
`core.vectordb`, `core.profiles`, `core.codebase`, `core.documents`,
`core.community`, and `daemon` as source modules, forbidding imports of
`core.providers` and `transports` from all of them.

#### Scenario: Every package is a contract source

- **WHEN** the contract set in `pyproject.toml` is compared against the
  packages present under `src/rag_mcp/`
- **THEN** every package MUST appear as a source module in at least one
  contract

#### Scenario: Transport import from core fails

- **WHEN** any module under `core/` or `daemon/` imports from
  `rag_mcp.transports`
- **THEN** `uv run lint-imports` MUST fail

## ADDED Requirements

### Requirement: Community integration direction is acyclic
The shared community strategy package SHALL not import from codebase or document graph subsystems. Optional external community adapters SHALL remain integration leaves and SHALL not import from `core/`.

#### Scenario: Both graph subsystems use shared partitioning
- **WHEN** codebase and document graphs select a community strategy
- **THEN** both SHALL depend on the shared community strategy contract
- **AND** neither graph subsystem SHALL import the other

#### Scenario: Leiden adapter is inspected
- **WHEN** the optional Leiden adapter is inspected
- **THEN** it SHALL not import from `rag_mcp.core`, `rag_mcp.transports`, or `rag_mcp.daemon`
