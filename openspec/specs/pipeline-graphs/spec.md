# pipeline-graphs Specification

## Purpose
Define executable user-connected RAG graphs that reuse OMRG operations, resolve settings per run, and retain retrieval and ingestion safeguards.

## Requirements

### Requirement: Saved connections determine execution
The system SHALL execute versioned graph documents containing registered operations, parameters, inputs, outputs, and typed connections. Graphs SHALL support compatible branches and joins. Presentation layout SHALL remain separate from execution semantics.

#### Scenario: Changing a connection changes execution
- **GIVEN** two valid revisions connect different retrieval branches to an output
- **WHEN** each revision executes against the same fixture
- **THEN** its connections SHALL determine the invoked nodes and returned output
- **AND** execution SHALL NOT substitute a fixed template pipeline

#### Scenario: Moving a node changes presentation only
- **WHEN** a user moves nodes or changes the viewport without changing operations or connections
- **THEN** execution identity and ingestion index identity SHALL remain unchanged

#### Scenario: Unsupported graph version
- **WHEN** a graph declares an unsupported schema version
- **THEN** validation SHALL fail with an actionable compatibility message before execution

### Requirement: Operation contracts are discoverable
Each operation SHALL declare its version, parameter schema, named port types, input cardinality, required capabilities, effects, and supported bypass behaviour. The catalogue SHALL identify unavailable operations and their reason. Existing domain registries SHALL remain the source of strategy implementations.

#### Scenario: Catalogue drives node configuration
- **WHEN** a client requests the operation catalogue
- **THEN** it SHALL receive enough information to build and validate the supported node controls
- **AND** unavailable optional capabilities SHALL have an actionable reason

#### Scenario: A strategy is reused
- **WHEN** a graph node selects an existing registered reader, chunker, or retrieval implementation
- **THEN** it SHALL dispatch through the same domain implementation as the standard operation

#### Scenario: Invalid bypass
- **WHEN** a user disables a node whose input and output have no declared compatible bypass
- **THEN** validation SHALL reject the graph
- **AND** the system SHALL NOT invent an output or pass incompatible data onward

### Requirement: Graph preflight rejects invalid work
The system SHALL validate operation names, parameters, required ports, compatible types and provenance, resource availability, topology, and write conflicts before node execution. It SHALL reject cycles, arbitrary executable code, and overrides outside the allowed operation schema.

#### Scenario: Invalid graph does not execute
- **WHEN** a graph has an unknown node type, missing required input, incompatible connection, or cycle
- **THEN** validation SHALL name the node or connection
- **AND** no graph node, model call, or store mutation SHALL run

#### Scenario: Identity conflict
- **WHEN** a graph targets a collection with an incompatible embedding provider or model
- **THEN** admission SHALL fail before execution even if vector dimensions match

#### Scenario: Executable text is submitted
- **WHEN** a graph contains a Python expression, shell command, or dynamic import instead of a registered operation
- **THEN** the system SHALL reject it as unsupported data

#### Scenario: Conflicting commits
- **WHEN** an ingestion recipe has more than one enabled commit destination
- **THEN** preflight SHALL reject the recipe with the `multiple_commit_destinations` issue
- **AND** it SHALL reject it whether or not the destinations target the same source and collection

### Requirement: Branches and joins have deterministic semantics
The runner SHALL execute ready nodes within its resource and concurrency limits. Required joins SHALL wait for all inputs and preserve declared port order. Fan-out SHALL isolate mutable branch values. Empty results SHALL remain valid inputs.

#### Scenario: Branches finish in different orders
- **WHEN** two branches finish in either order
- **THEN** the join SHALL receive the same named inputs in the same declared order
- **AND** the output SHALL retain stable ordering under the operation's contract

#### Scenario: One branch has no results
- **WHEN** an empty dense result joins a non-empty sparse result
- **THEN** the join SHALL execute according to the registered fusion contract
- **AND** it SHALL NOT treat the empty list as a missing dependency

#### Scenario: Resource limit is reached
- **WHEN** more nodes are ready than their allowed concurrency
- **THEN** excess nodes SHALL wait
- **AND** the runner SHALL NOT bypass model, embedding, or write limits

### Requirement: Run settings are immutable and explicit
Each run SHALL capture collection settings, its inherited or explicit operational profile, and validated graph/node overrides before execution. Node overrides SHALL precede graph overrides and resolved defaults. Existing environment priority within profile resolution SHALL remain intact. Runs SHALL NOT alter collection profile metadata or persistent configuration.

#### Scenario: Inherited profile
- **WHEN** a graph omits its operational profile
- **THEN** each collection-bound operation SHALL inherit its collection's resolved profile

#### Scenario: Explicit graph profile
- **WHEN** a graph selects documents or codebase
- **THEN** the corresponding existing bundle SHALL supply its defaults
- **AND** the collection's stored profile tag SHALL remain unchanged
- **AND** the bundle's hybrid setting SHALL NOT add or remove a sparse branch: the graph wiring decides which retrieval stages run

#### Scenario: Explicit node override
- **WHEN** a reranker node explicitly disables reranking
- **THEN** that node SHALL bypass inference regardless of the inherited reranker default
- **AND** the result SHALL record the effective control and its source

#### Scenario: Settings change during execution
- **WHEN** a profile or draft graph changes after a run is admitted
- **THEN** the admitted run SHALL retain its captured settings and graph
- **AND** later runs SHALL resolve their own snapshots

#### Scenario: Unsupported composition override
- **WHEN** a graph requests a different provider/model, secret, storage URI, or operational hybrid profile
- **THEN** validation SHALL reject the request with an actionable explanation

### Requirement: Retrieval and answering contracts survive graph execution
Graph operations SHALL preserve score kinds, threshold transforms, ranking provenance, source/chunk lineage, context assembly, citation checks, and explicit verification outcomes. These rules SHALL use shared production algorithms.

#### Scenario: Threshold sees an incompatible score
- **WHEN** a graph connects a fusion result to a threshold operation
- **THEN** port validation or the shared score-kind guard SHALL reject the connection, or the operation SHALL apply the threshold only to the dense similarity score it was calibrated for (the dense gate before fusion, as `search()` does)
- **AND** it SHALL NOT compare a fusion score with a dense similarity threshold
- **AND** it SHALL NOT label that score as dense similarity

#### Scenario: Reranker degrades
- **WHEN** the existing reranker fallback applies
- **THEN** graph execution SHALL use the same pre-rerank score and filtering rules
- **AND** it SHALL record the fallback reason

#### Scenario: Answer has no evidence
- **WHEN** an answer graph receives no usable evidence
- **THEN** it SHALL return the existing no-evidence outcome without generation

#### Scenario: Citation is inspected
- **WHEN** a graph answer cites a stored chunk
- **THEN** its reference SHALL resolve through the existing lineage contract
- **AND** claim verification status SHALL remain separate from reference validity

### Requirement: Graph ingestion retains source and write safeguards
Graph ingestion SHALL preserve content detection, reader declarations, complete-source checks, source/chunk identities, structural embedding validation, and protected replacement. Index identity SHALL include index-shaping graph operations, versions, parameters, and connections. It SHALL exclude presentation and query-only changes.

#### Scenario: Same complete source is reused
- **WHEN** source content and its complete index-shaping identity match
- **THEN** expensive parse, chunk, embedding, and write work SHALL be skipped

#### Scenario: Ingestion graph changes
- **WHEN** an index-shaping operation, parameter, version, or connection changes
- **THEN** the affected source SHALL require reprocessing on its next explicit ingest
- **AND** saving the graph alone SHALL NOT change vectors

#### Scenario: Explicit parameter equals its default
- **WHEN** an index-shaping node sets a parameter explicitly to the value it would inherit
- **THEN** the index identity SHALL count the explicit value as a change
- **AND** the affected source SHALL be processed again once on its next explicit ingest, then reused

#### Scenario: Existing lineage is invalid
- **WHEN** the existing source compatibility guard rejects legacy or inconsistent lineage
- **THEN** the graph SHALL fail before mutation
- **AND** it SHALL NOT perform automatic legacy repair

#### Scenario: Replacement reaches commit
- **WHEN** a source replacement begins persistent mutation
- **THEN** write, verification, and stale cleanup SHALL remain one protected operation
- **AND** raw graph nodes SHALL NOT bypass its guards

#### Scenario: Reader declares Markdown or structured output
- **WHEN** a graph reads a source through an existing backend
- **THEN** text-format and structured-output declarations SHALL reach the shared chunking logic unchanged

#### Scenario: Directory ingestion remains bounded
- **WHEN** a source graph processes a directory
- **THEN** it SHALL process source units without materialising the directory's complete chunk/vector corpus
- **AND** existing per-file error reporting and successful sibling commits SHALL be retained

### Requirement: Execution exposes actual outcomes and cancellation
Graph execution SHALL emit ordered run/node events with actual states, safe progress, failures, and completed effects. Cancellation SHALL be run-scoped and cooperative. It SHALL stop further work, check before commit, and allow an entered protected commit to finish.

#### Scenario: A node fails
- **WHEN** a node fails outside a declared domain fallback
- **THEN** the affected execution unit SHALL fail and dependent nodes SHALL be skipped
- **AND** the result SHALL name the failing node and completed effects

#### Scenario: Cancellation precedes commit
- **WHEN** cancellation is requested before a protected source commit starts
- **THEN** that commit SHALL not start
- **AND** sibling or later work SHALL observe the same run-specific cancellation

#### Scenario: Cancellation arrives during commit
- **WHEN** cancellation is requested after protected mutation starts
- **THEN** verification and cleanup SHALL finish before terminal cancellation
- **AND** the result SHALL disclose committed sources

#### Scenario: Blocking inference continues
- **WHEN** a running provider call cannot be interrupted safely
- **THEN** the run SHALL remain cancelling until it reaches a safe boundary
- **AND** the system SHALL NOT report that computation has stopped prematurely

### Requirement: Standard and editable paths share algorithms
Canonical graph templates SHALL reproduce standard ingestion, retrieval, and answering semantics through shared algorithms. Existing public signatures, result shapes, defaults, and failure contracts SHALL remain compatible.

#### Scenario: Canonical retrieval parity
- **WHEN** the standard search and its canonical graph run against deterministic fixtures
- **THEN** ranking, text, scores, score kinds, lineage, and fallback behaviour SHALL agree

#### Scenario: Canonical ingestion and answer parity
- **WHEN** the standard operations and canonical graphs process the same fixtures
- **THEN** stored chunks, source identities, citations, statuses, and degradation markers SHALL agree

#### Scenario: Repaired document strategy is reused
- **WHEN** a registered sentence replacement is selected for structured or unstructured document splitting
- **THEN** standard and graph ingestion SHALL invoke the selected callable
- **AND** reader-declared Markdown and degradation markers SHALL remain intact

#### Scenario: Metadata enrichment retains the owning store
- **WHEN** two Engine contexts enrich unstructured sources through graph adapters
- **THEN** each captured classification prompt SHALL use its owning store and seeds
- **AND** no process-default store SHALL replace that context
