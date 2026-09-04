# grounded-answer-synthesis Specification

## Purpose
Defines the grounded answering operation: answers are synthesised only
from retrieved evidence, citations are built deterministically from
stored chunk lineage (never from model-invented identifiers), and the
result carries a closed status schema that separates retrieval failure
from generation failure. The referential citation guarantee is
optionally backed by a semantic claim-verification judge (ADR-059),
which never weakens the guarantee when absent or skipped.

## Requirements

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

The citation wire format is normative:

- Supplied sources are numbered from 1 in the order they are placed in
  the prompt, and each prompt source is labelled with its ordinal in a
  bracket marker (`[1]`, `[2]`, ...).
- The model cites a source by emitting a bracket group of one or more
  comma-separated ordinals (`[1]`, `[2, 4]`); whitespace inside the
  brackets is tolerated.
- A bracket group containing anything non-numeric cites nothing: the
  whole group is dropped, so an answer mixing valid and invalid
  citations is grounded only in its valid ordinals.
- An ordinal string longer than nine digits SHALL be rejected with an
  actionable error (attributed to generation, with evidence retained)
  before integer conversion.
- Ordinals outside the supplied range (`< 1` or `> ` the number of
  supplied sources) are discarded, never resolved and never fabricated.
- Valid ordinals are deduplicated and reported in ascending order.
- Ordinal `N` maps to the `N`-th supplied evidence row, and the citation
  entry carries that row's `chunk_id` (re-fetchable as exactly one
  stored chunk), every constituent `chunk_id` of a merged assembly row,
  and its lineage fields (`source_id`, `source_version`, `source`,
  `source_chunk_index`).
- A non-empty answer from which no valid ordinal survives has status
  `generation_unverified` (never `ok`), and the supplied evidence is
  still returned.

#### Scenario: A citation resolves to exactly one stored chunk

- **GIVEN** an answer citing source N
- **WHEN** the `chunk_id` the system associated with source N is used as a
  metadata filter
- **THEN** exactly the corresponding stored chunk SHALL be retrieved

#### Scenario: Malformed and out-of-range citation groups cite nothing

- **GIVEN** a model answer whose bracket groups include a non-numeric
  entry (`[1, x]`), an out-of-range ordinal (`[99]`), and a valid one
  (`[2]`)
- **WHEN** the result is assembled
- **THEN** only ordinal 2 SHALL produce a citation
- **AND** no citation, identifier, or lineage SHALL be fabricated for the
  malformed or out-of-range entries

#### Scenario: A substantive answer needs a valid citation

- **GIVEN** the model returns a non-empty answer with no valid supplied source
  ordinal
- **WHEN** the result is assembled
- **THEN** the result MUST be marked as generation-unverified or error
- **AND** MUST NOT be represented as a grounded answer
- **AND** the supplied evidence MUST still be returned

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

### Requirement: Answer results carry a closed status schema

Every answering result SHALL carry the same top-level fields with
closed value sets, so consumers can branch on shape rather than probe
for keys. The fields are: `status`, `query`, `answer`, `citations`,
`evidence`, `failure_stage`, `error`, and `completion_source`. The
`status` value SHALL be one of `ok`, `no_evidence`,
`generation_unverified`, or `error`; `failure_stage`, when set, SHALL
be `retrieval` or `generation` and is `null` when no stage-attributed
failure occurred; `completion_source` SHALL be one of `none`,
`client_mrtr`, `client_legacy`, or `server`.

Per status:

- `ok`: a grounded answer. `answer` is the model text, `citations` is
  non-empty and built from supplied evidence, `evidence` is every chunk
  placed in the prompt, and `failure_stage` and `error` are `null`.
- `no_evidence`: retrieval returned nothing above threshold. `answer`
  is `null`, `citations` and `evidence` are empty, `failure_stage` and
  `error` are `null`, and no language-model call was made.
- `generation_unverified`: a non-empty answer with no valid supplied
  ordinal. `answer` and `evidence` are returned, `citations` is empty,
  and `failure_stage` and `error` are `null`.
- `error`: `answer` is `null`, `citations` is empty, and `error` names
  the failure actionably. `evidence` is the retrieved chunks when
  retrieval succeeded (generation-stage failures retain the evidence)
  and empty when it did not. `failure_stage` names the failed stage,
  or is `null` for failures outside both stages (for example the
  capability being disabled or no provider being configured).

A `diagnostics` field (with `retrieval_ms`, `generation_ms`, and
`completion_calls`) SHALL be present exactly when diagnostics were
requested, on every status.

#### Scenario: The result shape is identical across statuses

- **WHEN** any answering result is returned, on any status
- **THEN** it SHALL carry the eight top-level fields with the closed
  value sets above
- **AND** a consumer SHALL be able to branch on `status` without
  probing for keys

#### Scenario: Diagnostics are present exactly when requested

- **GIVEN** diagnostics are requested
- **WHEN** the result is returned, on any status
- **THEN** it SHALL carry `diagnostics` with retrieval and generation
  durations reported separately and the completion-call count
- **AND** a result with diagnostics not requested SHALL omit the field

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

### Requirement: Modern client model requests use multi-round trips where available

Where the calling MCP client advertises model-request capability AND
the server is configured to prefer the client model
(`answer.prefer_client_sampling`), the tool SHALL prefer the current
protocol's multi-round-trip request mechanism and SHALL report the
selected completion source. Client sampling is opt-in: a capable client
without the preference set SHALL be served by the configured
server-side model, and preference wins over capability in neither
direction — both must hold for a client source to be selected. The tool
SHALL NOT use deprecated server-initiated sampling on a modern session.
A negotiated legacy session MAY use the older path as a labelled
compatibility mode, and only when legacy sampling is explicitly allowed.

#### Scenario: Modern client sampling uses MRTR

- **GIVEN** a modern MCP client advertising the required model-request
  capability
- **AND** the server is configured to prefer the client model
- **WHEN** the answering tool runs
- **THEN** completion SHALL be requested through an MRTR `Sample` resolver or
  `InputRequiredResult`
- **AND** no server-side language-model call SHALL be made
- **AND** deprecated `ctx.session.create_message()` SHALL NOT be called

#### Scenario: Legacy sampling is explicitly negotiated

- **GIVEN** an older negotiated MCP session that supports the legacy sampling
  back-channel
- **WHEN** compatibility sampling is selected
- **THEN** the result SHALL identify the legacy completion source
- **AND** the legacy API SHALL never be attempted merely because modern MRTR
  is unavailable

#### Scenario: Falls back to the configured server model

- **GIVEN** a client without an applicable model-request path
- **WHEN** the answering tool runs
- **THEN** the configured server-side model SHALL be resolved lazily and used
  if available
- **AND** the result SHALL report which source was used

#### Scenario: Neither available

- **GIVEN** a client without an applicable model-request path and no configured
  server model
- **WHEN** the answering tool runs
- **THEN** an actionable error naming both options SHALL be returned
- **AND** the tool SHALL NOT raise

### Requirement: The cost of answering is disclosed

Answering adds the project's first query-time generation path and may make one
or more completion calls when COMPACT refinement is needed. The tool
description and operation documentation SHALL state that, so a caller chooses
knowingly between chunks and an answer.

#### Scenario: Tool description states the cost

- **WHEN** the answering tool is advertised over MCP
- **THEN** its description SHALL state that it performs one or more
  language-model completion calls
- **AND** SHALL name the cheaper chunk-returning tool as the alternative

#### Scenario: Timing is reported

- **WHEN** diagnostics are enabled
- **THEN** core SHALL report retrieval and generation durations separately
- **AND** the MCP and CLI results SHALL surface those diagnostics
- **AND** the completion-call count SHALL be reported when available

### Requirement: Claim verification is an optional stage gated by configuration

The pipeline SHALL provide an optional claim-verification stage that
verifies each cited claim against its cited evidence before reporting `ok`.
The stage SHALL be disabled by default and SHALL be enabled by the
`ANSWER__VERIFY_CLAIMS` setting. When disabled, the existing referential-only
`ok` guarantee SHALL remain unchanged.

#### Scenario: Verification disabled by default

- **GIVEN** the default configuration
- **WHEN** an answer is produced with at least one valid citation
- **THEN** the result SHALL have `status="ok"` with no `verified` field
- **AND** no verification model call SHALL be made

#### Scenario: Verification enabled

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` and a verification provider is
  configured
- **WHEN** an answer is produced with at least one valid citation
- **THEN** the pipeline SHALL verify each claim against its cited evidence
- **AND** the result SHALL include a `verified` field

#### Scenario: Verification enabled but no citations

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **WHEN** an answer is produced with no valid citations
- **THEN** the result SHALL have `status="generation_unverified"` as before
- **AND** no verification model call SHALL be made

### Requirement: The judge evaluates claim–evidence pairs in isolation

The judge SHALL receive one claim and the text of the evidence its ordinal
cites, with no answer context. The judge SHALL return a structured verdict
of `supported`, `unsupported`, or `unparseable`. The prompt SHALL treat
evidence text as quoted data with explicit delimiters and an instruction
hierarchy, so an injected instruction inside a cited chunk cannot flip the
verdict.

#### Scenario: A supported claim

- **GIVEN** a claim that is entailed by its cited evidence
- **WHEN** the judge evaluates the pair
- **THEN** the verdict SHALL be `supported`

#### Scenario: An unsupported claim

- **GIVEN** a claim that is contradicted by or absent from its cited evidence
- **WHEN** the judge evaluates the pair
- **THEN** the verdict SHALL be `unsupported`

#### Scenario: Evidence text is treated as data

- **WHEN** the judge prompt is constructed
- **THEN** evidence text SHALL be wrapped in explicit quote delimiters
- **AND** the prompt SHALL state that text inside the delimiters is untrusted
  source material
- **AND** the instruction hierarchy SHALL be repeated after each evidence
  block

### Requirement: Verification failure produces an explicit status with evidence retained

When one or more claims fail verification, the result SHALL have
`status="unverified_claims"`. The answer text, citations, and evidence SHALL
be retained so the caller can decide what to do with the answer. The result
SHALL list which claims failed verification.

#### Scenario: Some claims fail verification

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` and an answer with three claims
- **AND** one claim is unsupported by its cited evidence
- **WHEN** verification completes
- **THEN** the result SHALL have `status="unverified_claims"`
- **AND** the result SHALL include the answer text
- **AND** the result SHALL include all citations and evidence
- **AND** the result SHALL list the unsupported claim(s)

#### Scenario: All claims pass verification

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` and every claim is supported
- **WHEN** verification completes
- **THEN** the result SHALL have `status="ok"` and `verified=true`

#### Scenario: Mixed supported and unparseable verdicts

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` and an answer with two claims
- **AND** one verdict is `supported` and one is `unparseable`
- **WHEN** verification completes
- **THEN** the result SHALL have `status="unverified_claims"`
- **AND** the unparseable claim SHALL be listed with `verdict="unparseable"`
- **AND** only an all-unparseable run degrades to `verification_skipped`

### Requirement: Verification degrades gracefully when the provider is unavailable

When the verification provider cannot be reached — missing API key, network
error, model not configured, or all verdicts are unparseable — the pipeline
SHALL NOT raise and SHALL NOT block the answer. The result SHALL report
`status="ok"` (the referential-only guarantee) with a `verification_skipped`
field naming the reason. The pipeline SHALL never silently treat a
verification failure as either a pass or a fail.

#### Scenario: Cloud provider not configured

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` but no verification provider API
  key is set
- **WHEN** the answer pipeline runs
- **THEN** the result SHALL have `status="ok"` with `verification_skipped`
  naming the missing configuration
- **AND** no verification model call SHALL be made

#### Scenario: Verification call fails

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` and the verification provider is
  configured
- **AND** the judge call raises a network or timeout error
- **WHEN** the pipeline handles the error
- **THEN** the result SHALL have `status="ok"` with `verification_skipped`
  naming the error
- **AND** the answer, citations, and evidence SHALL be retained

#### Scenario: All verdicts are unparseable

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` and the judge returns unparseable
  output for every claim
- **WHEN** verification completes
- **THEN** the result SHALL have `status="ok"` with `verification_skipped`
  naming the unparseable rate
- **AND** the answer, citations, and evidence SHALL be retained

### Requirement: Verification settings are injected, never global

The verification settings SHALL be carried on the frozen answer settings
block and threaded through the pipeline as a parameter, following the
existing settings-dependency-injection pattern (ADR-037). Core modules
SHALL NOT import a settings singleton. The composition root SHALL construct
the verification LLM and inject it, exactly as it constructs the answer LLM.

#### Scenario: Settings are injected

- **WHEN** the answer pipeline runs with verification enabled
- **THEN** the verification settings SHALL come from the injected
  `EffectiveSettings` answer block
- **AND** no core module SHALL call a settings singleton

#### Scenario: Verification LLM is injected

- **WHEN** the composition root constructs the answer pipeline
- **AND** `ANSWER__VERIFY_CLAIMS=true`
- **THEN** the composition root SHALL construct a verification LLM and
  inject it into the pipeline
- **AND** the pipeline SHALL NOT construct its own verification LLM

### Requirement: Profiles can override verification settings

Profile YAML bundles SHALL support optional `answer.verify_claims`,
`answer.verify_model`, and `answer.verify_provider` keys. A profile that
prioritises factual grounding MAY enable verification; a profile that
prioritises speed MAY leave it disabled. The profile-level value takes
precedence over the global default at operation time, following the
established profile override pattern.

#### Scenario: A profile enables verification

- **GIVEN** a profile bundle with `answer.verify_claims: true`
- **WHEN** a collection bound to that profile is answered
- **THEN** verification SHALL be enabled for that collection
- **AND** the global `ANSWER__VERIFY_CLAIMS` default SHALL be overridden

#### Scenario: A profile disables verification

- **GIVEN** a profile bundle with `answer.verify_claims: false`
- **AND** the global default is `ANSWER__VERIFY_CLAIMS=true`
- **WHEN** a collection bound to that profile is answered
- **THEN** verification SHALL be disabled for that collection

### Requirement: The cost of verification is disclosed

When verification is enabled, the tool description and documentation SHALL
state that the pipeline makes one or more additional language-model calls
to a cloud judge, adding latency per claim. The diagnostics SHALL report
verification duration and the number of judge calls separately from
retrieval and generation.

#### Scenario: Tool description states the verification cost

- **WHEN** the answering tool is advertised over MCP with verification
  enabled
- **THEN** its description SHALL state that verification adds one judge call
  per claim
- **AND** SHALL name the cloud dependency

#### Scenario: Verification timings are reported

- **WHEN** diagnostics are enabled and verification ran
- **THEN** the result SHALL report `verification_ms` and `verification_calls`
- **AND** those SHALL be separate from `retrieval_ms` and `generation_ms`
