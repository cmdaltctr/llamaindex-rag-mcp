## ADDED Requirements

### Requirement: Answering is a distinct operation from searching

The system SHALL provide an answering operation separate from `search()`.
`search()` SHALL continue to return ranked chunks and SHALL NOT call a
language model.

#### Scenario: Search is unchanged

- **WHEN** `search()` is called
- **THEN** no language-model call SHALL be made
- **AND** the returned result shape SHALL be unchanged by this capability

#### Scenario: Answering retrieves through the same path

- **WHEN** the answering operation runs
- **THEN** it SHALL obtain its evidence through the existing retrieval path,
  honouring the same profile-resolved levers, metadata filters and
  context-assembly behaviour
- **AND** it SHALL NOT implement a second retrieval strategy

### Requirement: Answers are grounded in retrieved evidence

The prompt SHALL instruct the model to answer only from the supplied sources,
to cite the sources it used, and to state when the sources do not support an
answer. The operation SHALL return the exact chunks supplied as context
alongside the answer.

#### Scenario: Supplied context is returned with the answer

- **WHEN** an answer is produced
- **THEN** the result SHALL include every chunk that was placed in the prompt
- **AND** each SHALL carry its `chunk_id`, `source_id`, `source_version`,
  `source`, `source_chunk_index` and retrieval score

#### Scenario: The model is instructed to stay within the evidence

- **WHEN** the prompt is constructed
- **THEN** it SHALL instruct the model to use only the provided sources
- **AND** to indicate when the sources do not contain the answer
- **AND** to cite the sources supporting each claim

### Requirement: Citations are deterministic and verifiable

Citations SHALL be constructed by the system from retrieved chunk lineage.
The system SHALL NOT depend on the model to emit correct identifiers.

#### Scenario: A citation resolves to exactly one stored chunk

- **GIVEN** an answer citing source N
- **WHEN** the `chunk_id` the system associated with source N is used as a
  metadata filter
- **THEN** exactly the corresponding stored chunk SHALL be retrieved

#### Scenario: Model-invented identifiers are not trusted

- **GIVEN** a model response referring to a source number outside the supplied
  range
- **WHEN** the result is assembled
- **THEN** the system SHALL NOT fabricate a citation for it
- **AND** the returned citation list SHALL contain only chunks actually
  supplied as context

#### Scenario: Merged context reports every constituent

- **GIVEN** context assembly merged adjacent chunks before synthesis
- **WHEN** the answer is returned
- **THEN** every constituent `chunk_id` SHALL be reported, not only the merged
  row's representative

### Requirement: Absent evidence never produces an invented answer

When retrieval returns nothing, or returns nothing above the effective
threshold, the operation SHALL report that no supporting evidence was found
and SHALL NOT call the language model.

#### Scenario: Empty retrieval short-circuits

- **GIVEN** a query for which retrieval returns no chunks
- **WHEN** the answering operation runs
- **THEN** it SHALL return a result stating no supporting evidence was found
- **AND** no language-model call SHALL be made
- **AND** the citation list SHALL be empty

#### Scenario: Empty collection short-circuits

- **GIVEN** an empty or absent collection
- **WHEN** the answering operation runs
- **THEN** it SHALL return the no-evidence result rather than an error

### Requirement: Retrieval failure and generation failure are distinguishable

The result SHALL make clear which stage failed, so an operator can tell a
retrieval problem from a generation problem without reading logs.

#### Scenario: Generation fails after successful retrieval

- **GIVEN** retrieval returned chunks
- **AND** the language-model call fails
- **WHEN** the operation returns
- **THEN** the failure SHALL be attributed to generation
- **AND** the retrieved chunks SHALL still be returned, so the caller retains
  the evidence

#### Scenario: Retrieval fails before generation

- **GIVEN** retrieval raises
- **WHEN** the operation returns
- **THEN** the failure SHALL be attributed to retrieval
- **AND** no language-model call SHALL have been made

### Requirement: The answer model is injected, never resolved inside core

The language model SHALL be constructed by the composition root and passed
into the operation, following the established pattern for the vector store and
the reranker. Core retrieval and answering modules SHALL NOT import a concrete
provider module.

#### Scenario: Injected model is used

- **WHEN** the composition root supplies a model
- **THEN** the operation SHALL use it
- **AND** SHALL NOT construct its own

#### Scenario: Layering is enforced

- **WHEN** the import-linter contracts run
- **THEN** no new edge from core business logic to a concrete provider module
  SHALL be required
- **AND** no existing contract SHALL need a new ignore entry

#### Scenario: No provider configured

- **GIVEN** no answer model can be constructed from the current configuration
- **WHEN** the answering operation is invoked
- **THEN** it SHALL return an actionable error naming the setting to configure
- **AND** SHALL NOT silently fall back to returning chunks as though they were
  an answer

### Requirement: Client-side sampling is preferred where available

Where the calling MCP client advertises sampling capability, the tool SHALL be
able to obtain the completion from the client's model instead of a
server-side one. The choice SHALL be explicit and reported.

#### Scenario: Client sampling is used when advertised

- **GIVEN** an MCP client advertising sampling capability
- **AND** the server is configured to prefer client sampling
- **WHEN** the answering tool runs
- **THEN** the completion SHALL be requested from the client
- **AND** no server-side language-model call SHALL be made

#### Scenario: Falls back to the configured server model

- **GIVEN** a client that does not advertise sampling capability
- **WHEN** the answering tool runs
- **THEN** the configured server-side model SHALL be used if one is available
- **AND** the result SHALL report which was used

#### Scenario: Neither available

- **GIVEN** a client without sampling capability and no configured server model
- **WHEN** the answering tool runs
- **THEN** an actionable error naming both options SHALL be returned
- **AND** the tool SHALL NOT raise

### Requirement: The cost of answering is disclosed

Answering adds the project's first query-time language-model call. The tool
description and the operation's documentation SHALL state that, so a caller
chooses knowingly between chunks and an answer.

#### Scenario: Tool description states the cost

- **WHEN** the answering tool is advertised over MCP
- **THEN** its description SHALL state that it performs a language-model call
- **AND** SHALL name the cheaper chunk-returning tool as the alternative

#### Scenario: Timing is reported

- **WHEN** diagnostics are enabled
- **THEN** the result SHALL report retrieval and generation durations
  separately
