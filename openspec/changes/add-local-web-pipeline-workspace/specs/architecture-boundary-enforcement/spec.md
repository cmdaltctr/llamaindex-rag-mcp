# Architecture boundary enforcement delta

## MODIFIED Requirements

### Requirement: Full-package import boundary coverage

The import-linter contract set SHALL cover every package under
`src/omrg/`. The business-layer contract SHALL include
`core.ingestion`, `core.retrieval`, `core.metadata`, `core.chunking`,
`core.vectordb`, `core.profiles`, `core.codebase`, `core.documents`,
`core.community`, `core.answer`, `core.pipelines`, `core.workspace`,
and `daemon`, forbidding concrete provider and transport dependencies under
the existing sanctioned exceptions. New packages SHALL not be omitted from
coverage.

#### Scenario: Every package is a contract source

- **WHEN** the contract set in `pyproject.toml` is compared against the
  packages present under `src/omrg/`
- **THEN** every package MUST appear as a source module in at least one
  applicable contract
- **AND** new graph/workspace packages MUST not depend on FastAPI, notebook
  runtimes, or transport modules

#### Scenario: Transport import from core fails

- **WHEN** any module under `core/` or `daemon/` imports from
  `omrg.transports`
- **THEN** `uv run lint-imports` MUST fail

### Requirement: Use-case subsystems live under core

The codebase-understanding subsystem SHALL live at `core/codebase/` and the
document-graph subsystem SHALL live at `core/documents/`. Domain algorithms
and graph execution SHALL remain under `core/`. Top-level modules SHALL
serve public API or composition responsibilities rather than implementing
domain algorithms. Domain subsystems SHALL share injected contracts and
settings without direct ingestion/retrieval cross-imports.

#### Scenario: Ingestion no longer reaches upward

- **WHEN** `core/ingestion/pipeline.py` needs file-type detection
- **THEN** it MUST use its injected detection seam or the sanctioned
  integration
- **AND** it MUST NOT import a top-level business implementation

#### Scenario: Top-level business modules are gone

- **WHEN** `src/omrg/` is listed after the change
- **THEN** public API and composition modules such as `__init__.py`,
  `engine.py`, `compose.py`, and composition helpers MAY exist
- **AND** ingestion, retrieval, graph scheduling, and workspace business
  algorithms MUST remain in their owning `core/` packages

#### Scenario: Subsystems share only settings

- **WHEN** domain subsystem imports are inspected
- **THEN** codebase/document graph packages MUST not import ingestion or
  retrieval implementations
- **AND** ingestion and retrieval MUST not import one another
- **AND** cross-domain orchestration MUST use injected contracts

## ADDED Requirements

### Requirement: Graph scheduling is independent of domain implementations
The generic graph runner SHALL receive operation adapters and resources through injection. It SHALL not import ingestion, retrieval, answering, provider, transport, or process-launch implementations. Domain adapters SHALL remain in their owning packages and use existing registries.

#### Scenario: New operation is registered
- **WHEN** a new compatible operation adapter is added and registered
- **THEN** the runner SHALL execute it without a name-specific branch or concrete implementation import

#### Scenario: Runner reaches into a domain implementation
- **WHEN** the runner imports a domain or transport implementation directly
- **THEN** executable boundary tests SHALL fail naming the offending edge

### Requirement: Application persistence and external tools remain injected leaves
Workspace services SHALL receive persistence and process-control interfaces from composition. Their adapters SHALL exchange pure data and avoid importing core business logic. Core graph execution SHALL not import SQLite, web frameworks, uv, or marimo implementations.

#### Scenario: Web runtime is unavailable
- **WHEN** graph validation/execution is imported without web or notebook dependencies
- **THEN** the import SHALL succeed without constructing an application or tool process

#### Scenario: External process wrapper imports business logic
- **WHEN** a process or persistence integration adds a core business import
- **THEN** executable boundary tests SHALL reject that dependency
