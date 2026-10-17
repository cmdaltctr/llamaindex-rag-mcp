# pipeline-run-records Specification

## Purpose
Preserve local graph revisions and execution evidence so users can inspect, reconnect to, and explicitly repeat runs without changing their recorded inputs.

## Requirements

### Requirement: Execution revisions are immutable
The workspace SHALL store immutable execution revisions and their content identities. Presentation layout SHALL be stored separately. Saving a semantic change SHALL create a new revision; existing runs SHALL retain their admitted revision.

#### Scenario: Editing after submission
- **WHEN** a user saves changes while an earlier revision is queued or running
- **THEN** the earlier run SHALL retain its original revision
- **AND** the new revision SHALL affect only a subsequent submission

#### Scenario: Old revision is selected
- **WHEN** a user explicitly repeats a saved revision
- **THEN** the submitted execution document SHALL match that revision
- **AND** the new run SHALL capture current resource/index identities and identify the repeat

### Requirement: Runs capture sufficient provenance
Every admitted run SHALL record its identifier, graph revision/hash, redacted effective settings, operation versions, input identities/references, selected backend/model/index identities, state, and output reference. Records SHALL identify completed source mutations and failure attribution.

#### Scenario: A run is inspected
- **WHEN** a user opens a completed, failed, or cancelled run
- **THEN** the record SHALL show the graph/settings actually used and completed effects
- **AND** it SHALL not substitute the current draft or profile

#### Scenario: Secrets occur in runtime configuration
- **WHEN** run provenance is persisted or exported
- **THEN** credentials SHALL be excluded or redacted
- **AND** raw vectors and unbounded source text SHALL NOT become event fields

### Requirement: Local admission and supervision are bounded
The workspace SHALL provide one supervised local run consumer, a queue limit, and explicit queued/running/terminal states. Failed jobs SHALL not stop the consumer. Node concurrency SHALL remain subject to core resource limits.

#### Scenario: Queue is full
- **WHEN** admission exceeds the configured waiting-job limit
- **THEN** the submission SHALL fail visibly without starting work
- **AND** existing jobs SHALL retain their state

#### Scenario: One job fails
- **WHEN** a job fails
- **THEN** its terminal state SHALL be recorded
- **AND** a subsequent queued job SHALL remain executable

### Requirement: Events can be replayed consistently
Run events SHALL have monotonically increasing per-run sequences. A status update and its event SHALL be persisted together before subscriber notification. Clients SHALL reconnect from the last received sequence and deduplicate repeated events.

#### Scenario: Monitoring reconnects
- **WHEN** a client reconnects with a retained last-event sequence
- **THEN** later retained events SHALL be replayed in order
- **AND** the client SHALL refresh the authoritative run state

#### Scenario: Subscriber disconnects
- **WHEN** a browser closes or loses its connection
- **THEN** only monitoring SHALL detach
- **AND** the admitted run SHALL continue unless explicitly cancelled

#### Scenario: Durations overlap
- **WHEN** concurrent nodes report durations
- **THEN** node durations SHALL remain separate from end-to-end wall time
- **AND** their sum SHALL NOT be presented as measured total execution time

### Requirement: Restart reports interruption without implicit retry
On workspace restart, nonterminal runs from the stopped process SHALL become interrupted. The system SHALL preserve their recorded evidence and SHALL NOT automatically repeat model calls, source replacement, or deletion.

#### Scenario: Process stops between stores
- **WHEN** the server stops after a vector mutation but before a terminal app record
- **THEN** the next start SHALL report the run as interrupted with its available evidence
- **AND** the next start SHALL NOT perform a separate recovery step on the vector store
- **AND** an explicit retry SHALL apply the existing source completeness rules during its own ingestion, so complete sources are reused and incomplete sources are processed again

#### Scenario: User requests retry
- **WHEN** a user explicitly retries an interrupted or failed run
- **THEN** the system SHALL create a new run and perform fresh admission checks
- **AND** it SHALL preserve the original record

### Requirement: Application artefacts remain separate and bounded
Application records and run artefacts SHALL be separate from vector data and source files, with owner-only access where supported. Event and preview payloads SHALL have size limits. App-record schema upgrades and cleanup SHALL preserve recoverable records and require a preview before destructive cleanup.

#### Scenario: Workspace schema changes
- **WHEN** an existing app-record schema requires an upgrade
- **THEN** the previous records SHALL be backed up before mutation
- **AND** the upgrade SHALL NOT migrate or rebuild vector stores

#### Scenario: Large output is inspected
- **WHEN** a node produces more data than the preview limit
- **THEN** the preview SHALL be explicitly truncated and provide a protected inspection reference
- **AND** it SHALL NOT silently discard the run's outcome

#### Scenario: Cleanup is confirmed
- **WHEN** the user confirms a previewed workspace cleanup
- **THEN** only the previewed application artefacts SHALL be removed
- **AND** vectors, original sources, notebooks, and experiment outputs SHALL remain untouched

### Requirement: Truncated run output is readable through a protected route

When a stored run value is larger than its preview, the system SHALL keep the full redacted value as a run artefact and SHALL serve it through `GET /v1/runs/{run_id}/artefacts/{name}`. The route SHALL apply the same access policy as reading the run record: a caller that cannot read the run SHALL NOT read its artefacts, and a bearer credential bound to an experiment SHALL read only artefacts of that experiment's runs. The response SHALL contain the redacted value only. Credentials and raw vectors SHALL NOT appear in it. Errors SHALL NOT expose file system paths or exception text.

#### Scenario: Read a truncated summary in full

- **WHEN** a node summary was cut and carries `truncated: true` with an `artefact_ref` naming an artefact of that run
- **THEN** the route MUST return the full redacted value of that artefact

#### Scenario: Unknown artefact

- **WHEN** the run exists but no artefact has the requested name
- **THEN** the route MUST return 404 with a generic message

#### Scenario: Name outside the run

- **WHEN** the requested name holds a path separator, a dot segment or any value that is not one safe path segment
- **THEN** the route MUST refuse the request with 400 and MUST NOT read any file

#### Scenario: Bound credential and another experiment

- **WHEN** a bearer credential bound to one experiment requests an artefact of a run in another experiment or in the live workspace
- **THEN** the route MUST answer as for an unknown run and MUST NOT return the value

### Requirement: Profile requests create no run records

A search, answer or ingestion that runs a user profile's pipeline for Chat, Knowledge Base search, an MCP tool or an ingestion job SHALL run within that request. It SHALL NOT enter the run queue and SHALL NOT write a run record or run events. A run started from Studio SHALL keep creating a run record.

#### Scenario: Chat question on a user profile

- **WHEN** a user asks a question in Chat about a collection that uses a user profile
- **THEN** the run list MUST stay unchanged

#### Scenario: Studio run of a slot pipeline

- **WHEN** a user runs the Search pipeline of a user profile from Studio
- **THEN** the workspace MUST record that run with its revision, as for any other Studio run
