# Modular core extraction delta

## MODIFIED Requirements

### Requirement: Ingestion and chunking subpackage extraction

The system SHALL provide ingestion orchestration from a `core/ingestion/`
subpackage exposing `ingest_path_async()` as the standard public entry point,
and SHALL provide the existing chunking strategies from `core/chunking/`.
Asynchronous graph ingestion SHALL use reusable internal source preparation,
reading, normalisation, enrichment, splitting, embedding, and protected
replacement stages from those same packages. Chunking dispatch SHALL resolve
strategies through `core/chunking/registry.py` without module-level imports of
concrete strategies. Both structured and unstructured document branches SHALL
invoke the selected registered document strategy, rather than private
implementation helpers. Reading, metadata attachment, reader declarations, and
degradation reporting SHALL retain their existing owners and semantics. Graph
execution SHALL NOT introduce a separate ingestion algorithm or a synchronous
mutation entry point.

#### Scenario: Content-type dispatch preserved

- **WHEN** a file with a known content type (e.g. `.py`, `.md`, `.yaml`) is
  ingested through the standard operation or a graph
- **THEN** the shared chunker MUST preserve its content-type precedence

#### Scenario: Strategy resolved through the registry

- **WHEN** the chunker resolves the strategy for a file
- **THEN** it MUST call `registry.get(<strategy name>)`
- **AND** `core/ingestion/chunker.py` MUST have no module-level import of
  `core.chunking.code`, `core.chunking.markdown`, `core.chunking.sentence`, or
  `core.chunking.config_file`
- **AND** the chunker MUST NOT call sentence splitting or post-processing
  helpers directly

#### Scenario: Only existing strategies extracted

- **WHEN** this change extends chunking for graph adapters
- **THEN** it MUST reuse the existing registered strategies
- **AND** it MUST NOT add a net-new chunking algorithm merely for the canvas

#### Scenario: Async ingestion entry point preserved

- **WHEN** an existing caller invokes ingestion
- **THEN** `ingest_path_async` MUST remain available with its injected
  `EffectiveSettings` parameter and existing behaviour
- **AND** new graph ingestion MUST be asynchronous and receive frozen settings

#### Scenario: Protected replacement is reused

- **WHEN** a graph writes an indexed source
- **THEN** the graph MUST use the same source/embedding validation and
  replacement operation as standard ingestion
- **AND** write, verification, and stale cleanup MUST stay together

#### Scenario: Registered replacement reaches production dispatch

- **WHEN** the sentence registry resolves a sentinel replacement
- **THEN** structured and unstructured standard/graph document dispatch MUST invoke it
- **AND** the regression MUST fail if either branch returns to a private splitter

#### Scenario: Reader-produced Markdown remains intact

- **WHEN** a non-Markdown source is read as declared Markdown
- **THEN** the selected strategy MUST receive that declaration
- **AND** headings, model-token settings, and post-processing MUST be applied exactly once

#### Scenario: Metadata degradation survives dispatch

- **WHEN** unstructured metadata extraction reports degradation
- **THEN** returned chunk results MUST retain that marker through the registered strategy call

### Requirement: Retrieval subpackage grouping

The system SHALL keep dense retrieval, sparse retrieval, fusion, reranking,
the `search()` orchestration facade, and threshold policy under
`core/retrieval/`. Candidate sizing, filtering, policy, fallback, and context
operations needed by graphs SHALL have shared implementations in that
subpackage. Standard and graph adapters SHALL resolve strategy implementations
through the existing registries, without name-specific dispatch branches or
module-level imports of concrete strategies.

#### Scenario: End-to-end search dispatch

- **WHEN** `search()` is called through the subpackage
- **THEN** it MUST preserve its existing dense + sparse + RRF + rerank policy
  orchestration and result semantics

#### Scenario: Stages resolved through the registry

- **WHEN** standard or graph retrieval dispatch needs a registered
  implementation
- **THEN** it MUST resolve it through the relevant `registry.get(...)`
- **AND** dispatch modules MUST have no module-level imports of concrete
  implementation modules

#### Scenario: Threshold policy relocated intact

- **WHEN** threshold policy is used in a standard search or graph
- **THEN** the calibrated ÷30 rerank transform MUST remain numerically
  identical
- **AND** no new calibration or default change MUST occur in this change

#### Scenario: Reranker model cache reset preserved

- **WHEN** tests need a clean reranker state
- **THEN** `reset_model_cache()` MUST clear the process-wide model cache

#### Scenario: Graph and search share filtering

- **WHEN** canonical graph and standard retrieval filter the same fixtures
- **THEN** they MUST use the same score-kind, dense-eligibility, top-k, and
  reranker-failure rules

### Requirement: Behaviour preservation and test continuity

Existing retrieval, ingestion, metadata extraction, and answering operation
semantics SHALL remain compatible: public signatures, defaults, return
shapes, CLI commands, MCP tool signatures, and error contracts are preserved.
New graph APIs and the explicit web command are additive. Graph adapters SHALL
reuse shared algorithms and retain current lineage, score, recovery, and
citation safeguards.

#### Scenario: Full test suite passes

- **WHEN** the approved implementation validation runs
  `uv run pytest -m "not slow" --cov=omrg`
- **THEN** all tests MUST pass
- **AND** coverage MUST meet the recorded floors: Core + MCP ≥95%,
  Orchestration ≥85%, Overall ≥90%

#### Scenario: File size ceiling across the package

- **WHEN** `src/omrg/` is inspected
- **THEN** no Python file MUST exceed 500 lines, including modules outside
  `core/`

#### Scenario: MCP and CLI surfaces unchanged

- **WHEN** existing MCP tools and CLI commands are exercised after the change
- **THEN** their signatures and behaviour MUST remain compatible
- **AND** no-argument `omrg` MUST still start the MCP stdio server
