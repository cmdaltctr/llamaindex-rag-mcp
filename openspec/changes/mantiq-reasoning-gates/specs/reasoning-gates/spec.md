# Spec Delta

## Purpose

Defines the opt-in manṭiq reasoning gates as pipeline graph operations and a
template: a concept frame before retrieval, a four-verdict claim judgement
that keeps the evidence's own conditions, an inference gate that admits only
valid inference forms over supported premises, and an answer gate that lets
only validated content through and reports the rest in its own result block.
The base answer path is unchanged.

## ADDED Requirements

### Requirement: Manṭiq runs only in a graph that uses its operations

The system SHALL register three graph operations, `mantiq.concept_frame`,
`mantiq.tasdiq` and `mantiq.qiyas`, and SHALL run them only when a saved
graph uses them. When no user profile binds a graph that uses a manṭiq
operation, the output of `Engine.answer`, of a profile graph answer and of
the MCP `answer_documents` tool SHALL be identical to the output without
this capability, timings excluded. Built-in profiles SHALL NOT run a manṭiq
operation.

#### Scenario: No profile binds a manṭiq graph

- **GIVEN** golden outputs recorded before this capability existed
- **WHEN** the same questions run through `Engine.answer`, a canonical answer
  graph and the MCP `answer_documents` tool
- **THEN** every output SHALL equal its golden output with timing fields
  removed
- **AND** the completion-call count SHALL equal the golden count

#### Scenario: Registration alone changes nothing

- **GIVEN** the operation catalogue with the three manṭiq operations
- **WHEN** a client lists the catalogue
- **THEN** it SHALL list the three operations with their parameters, ports
  and bypass
- **AND** the canonical ingestion, search and answer templates SHALL be
  unchanged

#### Scenario: Built-in profile

- **GIVEN** a collection bound to the built-in `documents` profile
- **WHEN** an answer is produced
- **THEN** no manṭiq operation SHALL run
- **AND** the result SHALL contain no `mantiq` key

#### Scenario: User profile bound to the manṭiq template

- **GIVEN** a collection bound to a user profile whose Answer pipeline was
  built from the `answer-mantiq` template
- **WHEN** an answer is produced
- **THEN** the three manṭiq operations SHALL run in graph order
- **AND** the result SHALL contain a `mantiq` block

#### Scenario: A disabled manṭiq node passes its value through

- **GIVEN** a graph in which a manṭiq node is disabled
- **WHEN** the graph runs
- **THEN** the node's input value SHALL reach its output unchanged
- **AND** the node SHALL make no model call

### Requirement: The manṭiq answer template is published

The system SHALL publish one `answer-mantiq` pipeline template beside the
canonical ingestion, search and answer templates. It SHALL be the canonical
answer graph shaped for the Engine, with `mantiq.concept_frame` before
retrieval, claim verification bypassed, and `mantiq.tasdiq` then
`mantiq.qiyas` before the `answer` output. Each experiment comparison cell
SHALL be a named graph built by the same transform.

#### Scenario: Templates are listed

- **WHEN** a client calls `GET /v1/pipeline-templates`
- **THEN** the response SHALL list `ingestion`, `search` and `answer` with
  documents unchanged, then `answer-mantiq`
- **AND** the `answer-mantiq` document SHALL pass draft validation on the
  same Engine

#### Scenario: The synthesis step keeps the original question

- **GIVEN** the `answer-mantiq` template
- **WHEN** its graph is inspected
- **THEN** the concept frame output SHALL feed only the retrieval chain
- **AND** the synthesis step SHALL receive the graph's original `query` input

#### Scenario: Experiment cell is reproducible

- **GIVEN** a named experiment cell
- **WHEN** its graph is built twice from the same base answer graph
- **THEN** both documents SHALL be equal

### Requirement: The concept frame is bounded data that only rewrites the query

`mantiq.concept_frame` SHALL build one frame from the query with the answer
model. The frame SHALL hold `key_terms`, `resolved_meanings`,
`canonical_concept`, `broader_concepts`, `narrower_concepts`,
`excluded_concepts`, `scope` (`universal` or `particular`), `divisions`,
`operational_definition` and `definition_checks` (`inclusive`, `exclusive`,
`non_circular`). Lists SHALL hold at most 12 items and strings at most 512
characters. The frame SHALL appear in the node summary.

#### Scenario: Frame built and recorded

- **GIVEN** an answer model is available
- **WHEN** the node runs
- **THEN** the node summary SHALL contain a frame with every field above,
  within the caps
- **AND** with `augment_query` on, the emitted query SHALL be the original
  text followed by the canonical and narrower concepts

#### Scenario: Unparseable frame degrades gracefully

- **GIVEN** the model returns text that does not parse as a frame
- **WHEN** the node runs
- **THEN** the node summary SHALL contain `concept_frame_skipped` naming the
  reason
- **AND** the emitted query SHALL equal the input query

#### Scenario: No answer model

- **GIVEN** no answer model resource is available
- **WHEN** the node runs
- **THEN** the node summary SHALL contain `concept_frame_skipped` with reason
  `no answer model`
- **AND** the run SHALL NOT fail for the frame alone

### Requirement: The Taṣdīq judgement uses four verdicts and keeps conditions

`mantiq.tasdiq` SHALL judge each cited claim with its own prompt and SHALL
return one of `supported`, `contradicted`, `unsupported`, `uncertain`, or
`unparseable` when the reply cannot be read. It SHALL also return
`conditions`: the qualifiers in the cited evidence (for example `may`, `if`,
`unless`, `only when`), at most 8. The base claim-verification verdicts and
prompt SHALL be unchanged.

#### Scenario: Four-verdict judgement

- **GIVEN** a cited claim and a judge
- **WHEN** the node runs
- **THEN** `mantiq.claims` SHALL give the claim one of the verdicts above
- **AND** `conditions` SHALL list the qualifiers found in the cited evidence

#### Scenario: Base verification is untouched

- **GIVEN** a canonical answer graph with claim verification on
- **WHEN** a claim is judged
- **THEN** the judge prompt SHALL be byte-identical to the ADR-059 prompt
- **AND** the verdict SHALL be `supported`, `unsupported` or `unparseable`

#### Scenario: Unsupported is not false

- **GIVEN** a claim judged `unsupported`
- **WHEN** the result is assembled
- **THEN** the result SHALL NOT describe the claim as false or contradicted
- **AND** the claim SHALL be excluded from the premise set

### Requirement: A gate without a judge skips and leaves the answer unchanged

When `mantiq.tasdiq` or `mantiq.qiyas` has no judge (no resource, a factory
that returns nothing, or a factory that raises), the node SHALL report a
skipped outcome with a reason and SHALL return the answer text, citations
and status unchanged. It SHALL NOT raise.

#### Scenario: No judge resource

- **GIVEN** an `answer-mantiq` graph and no judge available
- **WHEN** the graph runs
- **THEN** `mantiq.outcome` SHALL be `skipped` with `mantiq.skipped_reason`
  naming the cause
- **AND** `answer`, `citations` and `status` SHALL equal the values the node
  received

### Requirement: Premise eligibility respects authority labels when present

When evidence rows carry an `authority_status` field (supplied by the
authority-aware retrieval capability), a claim whose cited evidence is all
`superseded` or `conflicting` SHALL be `uncertain` with `uncertainty_reason`
naming the label, whatever the judge said. When no row carries the field,
every `supported` claim SHALL be a premise.

#### Scenario: Superseded evidence cannot support a premise

- **GIVEN** a claim cited only to rows with `authority_status="superseded"`
- **WHEN** the premise set is built
- **THEN** the claim SHALL be `uncertain` with `uncertainty_reason`
  `"evidence superseded"`

#### Scenario: Without authority labels all supported claims are premises

- **GIVEN** evidence rows without an `authority_status` field
- **WHEN** the premise set is built
- **THEN** every claim with verdict `supported` SHALL be in the premise set

### Requirement: Inferences are typed, checked and validated

`mantiq.qiyas` SHALL produce an `InferenceRecord` for each answer sentence
that carries an inference marker or cites two or more evidence rows, cited or
not. A record SHALL hold `inference_id`, `premise_claim_ids`, an
`inference_type` from a closed set, `conclusion`, `validity_status`
(`valid`, `invalid`, `unverifiable`) and boolean `checks`. A record SHALL be
`valid` only when every applicable check passes.

#### Scenario: Closed sets

- **WHEN** a record is produced
- **THEN** `inference_type` SHALL be one of `iqtirani_hamli`,
  `iqtirani_sharti`, `istithnai_muttasil_affirm`, `istithnai_muttasil_deny`,
  `istithnai_munfasil`, `unclassified`
- **AND** `checks` SHALL hold `premises_supported`, `form_valid`,
  `no_affirmed_consequent`, `no_denied_antecedent`,
  `alternatives_exhaustive`, `qualifiers_preserved`, `quantity_preserved`,
  `no_surplus_content`

#### Scenario: Uncited inference sentence

- **GIVEN** an answer sentence "Therefore B." with no citation, after cited
  claims "A" and "if A then B"
- **WHEN** the inference gate runs
- **THEN** an `InferenceRecord` SHALL exist for that sentence
- **AND** its `premise_claim_ids` SHALL name the two cited claims

#### Scenario: Valid conditional chain

- **GIVEN** supported premises "if A then B" and "if B then C" and the
  conclusion "if A then C"
- **WHEN** the inference gate runs
- **THEN** the record SHALL have `inference_type="iqtirani_sharti"` and
  `validity_status="valid"`

#### Scenario: Affirming the consequent is rejected

- **GIVEN** supported premises "if A then B" and "B" and the conclusion "A"
- **WHEN** the inference gate runs
- **THEN** `checks.no_affirmed_consequent` SHALL be `false`
- **AND** `validity_status` SHALL be `invalid`

#### Scenario: Denying the antecedent is rejected

- **GIVEN** supported premises "if A then B" and "not A" and the conclusion
  "not B"
- **WHEN** the inference gate runs
- **THEN** `checks.no_denied_antecedent` SHALL be `false`
- **AND** `validity_status` SHALL be `invalid`

#### Scenario: Disjunctive inference needs an exhaustive division

- **GIVEN** a supported premise "the value is X or Y" whose evidence does not
  state the list is exhaustive, a supported premise "not X", and the
  conclusion "Y"
- **WHEN** the inference gate runs
- **THEN** `checks.alternatives_exhaustive` SHALL be `false`
- **AND** `validity_status` SHALL be `unverifiable`

#### Scenario: A qualifier may not be strengthened

- **GIVEN** a supported premise whose `conditions` include `may` and a
  conclusion that states the same relation with `always` or `must`
- **WHEN** the inference gate runs
- **THEN** `checks.qualifiers_preserved` SHALL be `false`
- **AND** `validity_status` SHALL be `invalid`

#### Scenario: Categorical quantity may not be strengthened

- **GIVEN** supported premises "some A are B" and "all B are C" and the
  conclusion "all A are C"
- **WHEN** the inference gate runs
- **THEN** the record SHALL have `inference_type="iqtirani_hamli"`
- **AND** `checks.quantity_preserved` SHALL be `false` and `validity_status`
  SHALL be `invalid`

#### Scenario: Valid categorical chain

- **GIVEN** supported premises "all A are B" and "all B are C" and the
  conclusion "all A are C"
- **WHEN** the inference gate runs
- **THEN** `checks.quantity_preserved` SHALL be `true`
- **AND** `validity_status` SHALL be `valid`

#### Scenario: An uncertain premise cannot license a conclusion

- **GIVEN** an inference whose `premise_claim_ids` include a claim with
  verdict `uncertain`
- **WHEN** the inference gate runs
- **THEN** `checks.premises_supported` SHALL be `false`
- **AND** `validity_status` SHALL be `unverifiable`

#### Scenario: Surplus content is rejected

- **GIVEN** a conclusion that names an entity, number or condition present in
  no premise
- **WHEN** the inference gate runs
- **THEN** `checks.no_surplus_content` SHALL be `false`
- **AND** `validity_status` SHALL be `invalid`

### Requirement: The answer gate reports in its own block and keeps base fields

`mantiq.qiyas` SHALL record `mantiq.claims`, `mantiq.inferences`,
`mantiq.rejected` (text, reason, failing checks) and `mantiq.outcome`
(`all_admitted`, `some_rejected`, `nothing_admitted` or `skipped`). With
`filter_answer` on and at least one admitted sentence, `answer` SHALL hold
only supported claims and valid conclusions. A manṭiq node SHALL NOT change
`status`, `citations`, `evidence` or the base verification fields.

#### Scenario: Only validated sentences remain

- **GIVEN** an answer with one supported claim and one invalid inference
- **WHEN** the answer gate runs with `filter_answer` on
- **THEN** `answer` SHALL contain the supported claim only
- **AND** `mantiq.rejected` SHALL list the invalid inference with its failing
  checks, and `mantiq.original_answer` SHALL hold the text before the gate

#### Scenario: Nothing survives

- **GIVEN** an answer in which every sentence is rejected
- **WHEN** the answer gate runs
- **THEN** `answer` SHALL equal the text the node received
- **AND** `mantiq.outcome` SHALL be `nothing_admitted`

#### Scenario: The status and verdict schemas stay closed

- **GIVEN** any combination of gate outcomes
- **WHEN** the result is assembled
- **THEN** `status` SHALL equal the status the first manṭiq answer node
  received
- **AND** no new status, verification verdict or answer stage value SHALL be
  introduced

### Requirement: Manṭiq stays outside the base packages

No base package SHALL import the manṭiq package. Only the composition modules
that register its operations and build its template SHALL import it. The
manṭiq package SHALL NOT import a provider, a transport, the retrieval domain,
the ingestion domain or a settings singleton. Import contracts SHALL enforce
both rules with no ignore entry.

#### Scenario: Layering enforced

- **GIVEN** the import-linter contracts
- **WHEN** they run
- **THEN** a contract SHALL forbid every `omrs.core` package other than
  `omrs.core.mantiq`, and `omrs.transports`, from importing
  `omrs.core.mantiq`
- **AND** `omrs.core.mantiq` SHALL import nothing from
  `omrs.core.providers`, `omrs.transports`, `omrs.core.retrieval` or
  `omrs.core.ingestion`

### Requirement: Manṭiq cost and timing are disclosed per node

Each manṭiq node SHALL record in its node summary its model call count, its
elapsed milliseconds and its outcome. Gate options SHALL be node parameters
in the saved graph. The system SHALL add no setting, environment variable or
profile key for manṭiq.

#### Scenario: Node summary after a run

- **GIVEN** an `answer-mantiq` graph run with a judge
- **WHEN** the run record is read
- **THEN** each manṭiq node summary SHALL contain `calls`, `elapsed_ms` and
  `outcome`

### Requirement: The workspace offers the manṭiq template and shows its results

The Studio canvas SHALL let the user load the `answer-mantiq` template into a
user profile's Answer pipeline draft. A built-in profile SHALL NOT offer it.
The chat SHALL show the `mantiq` block of an answer: the outcome, each
rejected sentence with its failing checks, and the skip reason when a gate
skipped.

#### Scenario: Load the template

- **GIVEN** a user profile open on its Answer pipeline
- **WHEN** the user picks "Use the manṭiq answer template"
- **THEN** the draft SHALL hold the `answer-mantiq` graph
- **AND** the user SHALL save it as a revision before it runs

#### Scenario: Show gate results

- **GIVEN** an answer whose result has a `mantiq` block with one rejected
  sentence
- **WHEN** the chat shows the answer
- **THEN** the turn SHALL show the outcome and the rejected sentence with its
  failing checks

#### Scenario: Answer without a manṭiq block

- **GIVEN** an answer whose result has no `mantiq` key
- **WHEN** the chat shows the answer
- **THEN** the turn SHALL look the same as it does without this capability
