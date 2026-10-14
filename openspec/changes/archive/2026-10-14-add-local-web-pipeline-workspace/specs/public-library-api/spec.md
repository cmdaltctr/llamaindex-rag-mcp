# Public library API delta

## MODIFIED Requirements

### Requirement: The package exposes a public API

The package SHALL export, from its top-level `__init__`, `Engine`,
`EffectiveSettings`, `PipelineDefinition`, `PipelineResult`,
`PipelineEvent`, `PipelineValidationError`, and `__version__`. A library
consumer SHALL ingest, retrieve, answer, validate graphs, and execute graphs
through explicit Engine methods without importing private modules or creating
an implicit module-level engine. Everything not exported SHALL be treated as
internal and free to change without a major version.

#### Scenario: Core operations are importable from the top level

- **WHEN** a consumer imports the package
- **THEN** the engine type, effective-settings type and declared graph
  result/event/error types SHALL be importable by name from the top level
- **AND** ingest, search and answer SHALL remain documented Engine methods,
  with ingestion and answering async
- **AND** graph validation and asynchronous graph execution SHALL be
  documented Engine methods
- **AND** none SHALL require importing a module whose name begins with an
  underscore or that lives under an internal subpackage

#### Scenario: The exported surface is declared

- **WHEN** the top-level module is inspected
- **THEN** `__all__` SHALL enumerate the public surface
- **AND** a name absent from `__all__` SHALL be documented as internal

#### Scenario: Importing the package has no side effects

- **WHEN** the package is imported
- **THEN** no settings SHALL be resolved
- **AND** no provider, vector store, model or network client SHALL be
  constructed
- **AND** no process-global state SHALL be mutated

#### Scenario: Optional dependencies do not break import

- **WHEN** the package is imported in an environment lacking any optional
  extra
- **THEN** the import SHALL succeed
- **AND** the failure SHALL occur only when the corresponding capability is
  used, with an actionable message naming the extra

#### Scenario: Invalid graph is validated through the public API

- **WHEN** a consumer calls `Engine.validate_pipeline()` or submits invalid
  input to `Engine.run_pipeline()`
- **THEN** invalid graph input SHALL produce `PipelineValidationError` with
  actionable node/port diagnostics before side effects

#### Scenario: Valid graph is executed through the public API

- **WHEN** a consumer awaits `Engine.run_pipeline()` with a valid definition
- **THEN** the graph SHALL determine execution
- **AND** the consumer SHALL receive a `PipelineResult` and optional
  `PipelineEvent` notifications without importing HTTP or notebook code

#### Scenario: Runtime node failure has a stable result

- **WHEN** an admitted graph node fails
- **THEN** graph execution SHALL report its failure, completed effects, and
  skipped dependants in the public result contract
- **AND** existing ingest/search/answer return shapes SHALL remain unchanged
