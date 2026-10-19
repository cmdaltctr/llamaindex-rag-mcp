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

### Requirement: Read-only graph runs on one Engine overlap

Graph runs on one Engine SHALL wait for each other only when both contain an enabled step that writes to a collection. A run with no enabled write step SHALL start at once, also while another run on the same Engine is in progress. The ingestion write lock and the per-run node limits SHALL stay in force.

#### Scenario: Two searches at the same time

- **WHEN** two read-only graphs start on one Engine at the same time
- **THEN** both runs MUST be in progress together before either one ends

#### Scenario: Two ingestions at the same time

- **WHEN** two graphs that each contain an enabled write step start on one Engine
- **THEN** the second run MUST start its steps only after the first run ends

#### Scenario: Search during ingestion

- **WHEN** a read-only graph starts while a writing graph runs on the same Engine
- **THEN** the read-only graph MUST run without waiting for the writing graph to end

### Requirement: The draft check reports effective control values

The draft check (`validatePipeline` with no run inputs) SHALL return `nodes` with the effective controls of each node: for each lever field, its `lever`, `value`, `source` and `detail`, in the same shape as the admission check. It SHALL resolve each node's collection from the node's collection parameter, then `graph.collection`, then the request `collection`, then the host default collection. It SHALL resolve settings from `graph.profile` when it names a built-in profile, else from that collection's profile, and SHALL then apply graph overrides and node parameters in the admission order. When the draft has issues, the error response SHALL still carry `nodes` for each node whose parameters are valid and whose profile resolves. The draft check SHALL run no node, call no model and write nothing.

#### Scenario: Values without run inputs

- **WHEN** a client validates a Search draft with no inputs, `graph.profile` `documents` and no node `top_k`
- **THEN** the response MUST hold the control `retrieval.top_k` for the Prepare query node with the value from `documents` and the source `profile`

#### Scenario: Node parameter wins

- **WHEN** the same draft sets `top_k` to 20 on the Prepare query node
- **THEN** the control MUST show the value 20 and the source `node`

#### Scenario: Collection profile when the graph names none

- **WHEN** a draft names no `graph.profile`, `graph.collection` is `code`, and collection `code` is tagged `codebase`
- **THEN** each control MUST come from the `codebase` settings

#### Scenario: Host default collection

- **WHEN** a draft names no collection, no node names one and the request names none
- **THEN** the controls MUST come from the profile of the host default collection

#### Scenario: Incomplete draft

- **WHEN** a draft has an unconnected input port on one node and valid parameters on the others
- **THEN** the response MUST be the validation failure with its issues
- **AND** it MUST carry `nodes` with the controls of the other nodes

#### Scenario: Same values as admission

- **WHEN** a client validates one graph once without inputs and once with inputs
- **THEN** each node's controls MUST be equal in both responses

### Requirement: Read document step selects its PDF reader

The `read.document` operation SHALL accept an optional `pdf_reader` setting. Its choices SHALL be the registered concrete readers. `null` SHALL inherit the host reader. A set value SHALL make that node read PDF sources with the selected reader through the shared reader factory. A graph-wide override of `pdf_reader` SHALL remain a host-owned setting.

#### Scenario: Inherit uses the host reader

- **WHEN** a Read document node leaves `pdf_reader` empty
- **THEN** the node SHALL read PDF sources with the host reader

#### Scenario: Step reader reads PDF sources

- **WHEN** the host reader is `pypdf` and a Read document node sets `pdf_reader` to `pdf_inspector`
- **THEN** the node SHALL read PDF sources with `pdf_inspector`
- **AND** the reader's declared `markdown` text format SHALL reach the chunking step

#### Scenario: Uninstalled reader is refused

- **WHEN** a Read document node selects a registered reader that the host reports as not installed
- **THEN** validation SHALL fail with issue code `option_unavailable`
- **AND** the issue SHALL name the node, the reader and the missing package
- **AND** no node SHALL run

#### Scenario: Unknown reader is refused

- **WHEN** a Read document node sets `pdf_reader` to `auto` or to a name the registry does not hold
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs

#### Scenario: Graph-wide reader override stays host-owned

- **WHEN** a graph sets `overrides.pdf_reader`
- **THEN** validation SHALL fail with issue code `host_owned_setting`
- **AND** the message SHALL tell the user to set the reader on the Read document step

### Requirement: OCR routing follows the step reader under host OCR settings

A Read document node SHALL apply the OCR routing that its effective reader supports, under the host OCR settings and with the Engine OCR client. A step reader SHALL NOT add an OCR route, start a worker the host has not configured, or change an OCR setting.

#### Scenario: Step selects a reader without OCR routing

- **WHEN** the host reader is `pdf_inspector` with OCR fallback enabled and a Read document node selects `pypdf`
- **THEN** the node SHALL read PDF sources without OCR routing

#### Scenario: Step selects pdf-inspector on a host with another default

- **WHEN** the host reader is `pypdf`, the host enables OCR fallback, and a Read document node selects `pdf_inspector`
- **THEN** OCR-required PDF sources SHALL route through the host OCR routes and the Engine OCR client
- **AND** when the host has no OCR route, the node SHALL keep the partial text and report the degradation, as the standard path does

### Requirement: Ingestion identity records the step reader

Before the reuse check, graph ingestion SHALL compute each source's index identity with the reader of the Read document node in the commit node's ancestor slice. The stored identity SHALL name the same reader and text format as the read.

#### Scenario: Reader change forces reprocessing

- **WHEN** a source was indexed through a graph whose Read document node inherits the host reader `pypdf`, and the node then selects `pdf_inspector`
- **THEN** the next explicit ingest SHALL process the source again
- **AND** SHALL NOT report it as unchanged

#### Scenario: Stored identity names the step reader

- **WHEN** graph ingestion commits a PDF source read with a step reader that differs from the host reader
- **THEN** the stored source identity SHALL equal the identity computed with the step reader
- **AND** SHALL differ from the identity computed with the host reader

#### Scenario: Unchanged step reader reuses the source

- **WHEN** the same graph ingests the same unchanged source again
- **THEN** the source SHALL be reported as unchanged and expensive work SHALL be skipped

#### Scenario: Inheriting the reader keeps the standard identity

- **WHEN** the canonical ingestion template runs with an empty `pdf_reader`
- **THEN** its sources SHALL keep the same identity as the standard ingest path

### Requirement: Catalogue reports unavailable choices per setting

The operation catalogue SHALL report, for each operation setting whose choices depend on the host, the choices the host cannot run with a reason, and the value the setting inherits. Operations without such settings SHALL report empty maps. Operation availability SHALL remain per operation.

#### Scenario: Uninstalled reader is listed with its reason

- **WHEN** a client requests the catalogue on a host where `pypdfium2` is not installed
- **THEN** `read.document` SHALL stay available
- **AND** its unavailable choices SHALL list `pypdfium2` with a reason that names the missing package
- **AND** a client SHALL have enough information to show the choice as disabled with that reason

#### Scenario: Inherited reader is reported

- **WHEN** a client requests the catalogue on a host whose reader is `pdf_inspector`
- **THEN** the catalogue SHALL report `pdf_inspector` as the value that the Read document `pdf_reader` setting inherits
