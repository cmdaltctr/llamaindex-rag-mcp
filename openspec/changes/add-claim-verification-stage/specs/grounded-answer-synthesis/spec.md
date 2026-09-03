## ADDED Requirements

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
