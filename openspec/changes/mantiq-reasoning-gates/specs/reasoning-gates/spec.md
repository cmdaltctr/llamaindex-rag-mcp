# Spec Delta

## Purpose

Defines the opt-in reasoning gates around grounded answering: a
conceptualisation gate that fixes what the query means before retrieval, an
extended four-way claim judgement that keeps the evidence's own conditions, an
inference gate that admits only valid inference forms over supported premises,
and an answer gate that lets only validated content through while reporting
what it rejected.

## ADDED Requirements

### Requirement: Reasoning gates are opt-in and off by default

The system SHALL expose two independent settings,
`answer.reasoning.concept_frame_enabled` and
`answer.reasoning.inference_gate_enabled`, both defaulting to `false`. When
both are `false` the answer operation SHALL produce a result, prompts and
status identical to the operation without this capability, and SHALL make no
additional model calls.

#### Scenario: Both gates disabled

- **GIVEN** the default configuration
- **WHEN** an answer is produced
- **THEN** the result SHALL contain no `concept_frame` key and no `reasoning`
  key
- **AND** the completion-call count SHALL equal the count without this
  capability

#### Scenario: Gates are independent

- **GIVEN** `concept_frame_enabled=true` and `inference_gate_enabled=false`
- **WHEN** an answer is produced
- **THEN** the result SHALL contain a `concept_frame` key and no `reasoning`
  key

#### Scenario: Profile overrides the global default

- **GIVEN** a collection bound to a profile whose YAML sets
  `answer.reasoning.inference_gate_enabled: true`
- **WHEN** an answer is produced against that collection
- **THEN** the inference gate SHALL run for that collection
- **AND** a collection bound to a profile without the key SHALL use the global
  default

### Requirement: The concept frame is bounded structured data built before retrieval

When `concept_frame_enabled` is `true`, the system SHALL build one
`ConceptFrame` from the query through the injected completion seam before
retrieval. The frame SHALL contain: `key_terms`, `resolved_meanings`,
`canonical_concept`, `broader_concepts`, `narrower_concepts`,
`excluded_concepts`, `scope` (one of `universal`, `particular`), `divisions`
(routing categories), `operational_definition` and `definition_checks`
(`inclusive`, `exclusive`, `non_circular`, each a boolean). Every list field
SHALL be capped at 12 items and every string field at 512 characters. A frame
that fails to parse SHALL be recorded as `concept_frame_skipped` with a reason
and SHALL NOT fail the answer.

#### Scenario: Frame built and echoed

- **GIVEN** `concept_frame_enabled=true` and a completion seam is available
- **WHEN** an answer is produced
- **THEN** the result SHALL contain a `concept_frame` object with every field
  above
- **AND** the object SHALL respect the item and character caps

#### Scenario: Frame guides retrieval without importing it

- **GIVEN** a built frame with non-empty `excluded_concepts`
- **WHEN** retrieval runs
- **THEN** the retrieval call SHALL receive the frame's include terms, exclude
  terms and scope as plain data
- **AND** `core/reasoning` SHALL NOT import `core/retrieval` or
  `core/ingestion`

#### Scenario: Unparseable frame degrades gracefully

- **GIVEN** `concept_frame_enabled=true` and the seam returns text that does
  not parse as a frame
- **WHEN** an answer is produced
- **THEN** the result SHALL contain `concept_frame_skipped` naming the reason
- **AND** retrieval and answering SHALL proceed on the raw query

#### Scenario: No seam available

- **GIVEN** `concept_frame_enabled=true` and no completion seam is injected
- **WHEN** an answer is produced
- **THEN** the result SHALL contain `concept_frame_skipped` with reason
  `no completion seam`
- **AND** no error status SHALL be raised for the frame alone

### Requirement: Extended claim judgement keeps evidence conditions

When `inference_gate_enabled` is `true`, the claim-verification judge SHALL
return one of exactly four verdicts per claim: `supported`, `contradicted`,
`unsupported`, `uncertain`. The judge SHALL also return `conditions`: the
modal or conditional qualifiers present in the cited evidence for that claim
(for example `may`, `if`, `unless`, `only when`), as a list of strings capped
at 8 items. When `inference_gate_enabled` is `false` the two-way judge and its
prompt SHALL be unchanged.

#### Scenario: Four-way verdict when gate enabled

- **GIVEN** `inference_gate_enabled=true` and a judge is configured
- **WHEN** a claim is judged
- **THEN** its verdict SHALL be one of the four values
- **AND** `conditions` SHALL list the qualifiers found in the cited evidence

#### Scenario: Two-way verdict when gate disabled

- **GIVEN** `inference_gate_enabled=false` and `verify_claims=true`
- **WHEN** a claim is judged
- **THEN** the judge prompt SHALL be byte-identical to the prompt without this
  capability
- **AND** the verdict SHALL be `supported`, `unsupported` or `unparseable`

#### Scenario: Unsupported is not false

- **GIVEN** a claim judged `unsupported`
- **WHEN** the result is assembled
- **THEN** the result SHALL NOT describe the claim as false or contradicted
- **AND** the claim SHALL be excluded from the premise set

### Requirement: Premise eligibility respects authority labels when present

When evidence rows carry an `authority_status` field (supplied by the
authority-aware retrieval capability), a claim whose cited evidence is all
`superseded` or `conflicting` SHALL be marked `uncertain` with
`uncertainty_reason` naming the label, regardless of the judge's verdict.
When no row carries the field, every `supported` claim SHALL be an eligible
premise.

#### Scenario: Superseded evidence cannot support a premise

- **GIVEN** a claim cited only to rows with `authority_status="superseded"`
- **WHEN** the premise set is built
- **THEN** the claim SHALL be `uncertain` with `uncertainty_reason`
  `"evidence superseded"`

#### Scenario: Without authority labels all supported claims are premises

- **GIVEN** evidence rows without an `authority_status` field
- **WHEN** the premise set is built
- **THEN** every claim with verdict `supported` SHALL be in the premise set

### Requirement: Inferences are typed, checked and validated before they reach the answer

When `inference_gate_enabled` is `true`, every answer sentence that carries
citations to two or more evidence rows, or that the judge marks as not
directly entailed by any single cited row, SHALL produce an `InferenceRecord`
with: `inference_id`, `premise_claim_ids`, `inference_type` from the closed
set {`iqtirani_hamli`, `iqtirani_sharti`, `istithnai_muttasil_affirm`,
`istithnai_muttasil_deny`, `istithnai_munfasil`, `unclassified`},
`conclusion`, `validity_status` from {`valid`, `invalid`, `unverifiable`},
and `checks`, an object with boolean results for `premises_supported`,
`form_valid`, `no_affirmed_consequent`, `no_denied_antecedent`,
`alternatives_exhaustive`, `qualifiers_preserved`, `no_surplus_content`.
The record SHALL be `valid` only when every applicable check passes.

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

#### Scenario: An uncertain premise cannot license a conclusion

- **GIVEN** an inference whose `premise_claim_ids` include a claim with verdict
  `uncertain`
- **WHEN** the inference gate runs
- **THEN** `checks.premises_supported` SHALL be `false`
- **AND** `validity_status` SHALL be `unverifiable`

#### Scenario: Surplus content is rejected

- **GIVEN** a conclusion that names an entity, number or condition present in
  no premise
- **WHEN** the inference gate runs
- **THEN** `checks.no_surplus_content` SHALL be `false`
- **AND** `validity_status` SHALL be `invalid`

### Requirement: The answer gate admits only validated content and reports the rest

When `inference_gate_enabled` is `true`, the returned answer text SHALL
contain only sentences that are either a claim with verdict `supported` or the
conclusion of an inference with `validity_status="valid"`. Every removed
sentence SHALL appear in `result["reasoning"]["rejected"]` with its text,
the reason (`verdict` or `validity_status`) and the failing check names. The
result SHALL also carry `reasoning.claims` and `reasoning.inferences`. If the
gate removes every sentence, the status SHALL be `generation_unverified` and
the original text SHALL be preserved under `reasoning.original_answer`.

#### Scenario: Only validated sentences remain

- **GIVEN** an answer with one supported claim and one invalid inference
- **WHEN** the answer gate runs
- **THEN** the returned `answer` SHALL contain the supported claim only
- **AND** `reasoning.rejected` SHALL contain the invalid inference with its
  failing checks

#### Scenario: Nothing survives

- **GIVEN** an answer in which every sentence is rejected
- **WHEN** the answer gate runs
- **THEN** `status` SHALL be `generation_unverified`
- **AND** `reasoning.original_answer` SHALL hold the pre-gate text

#### Scenario: The status schema stays closed

- **GIVEN** any combination of gate outcomes
- **WHEN** the result is assembled
- **THEN** `status` SHALL be one of the values already defined by the
  grounded-answer-synthesis capability
- **AND** no new status value SHALL be introduced

### Requirement: The judge is injected and may be a decision model

The judge used for the four-way verdict and for inference-form classification
SHALL be injected through the composition root as an async callable. The
setting `answer.reasoning.judge` SHALL select `seam` (the ADR-059 completion
seam, the default), `onnx_decision` (a local ONNX decision model returning one
option from a closed list with probabilities) or `nli` (a local NLI
cross-encoder). `core/reasoning` SHALL NOT import a provider, a model runtime
or a settings singleton. A judge name whose runtime is not installed SHALL
fail at composition time with a message naming the setting and the missing
extra.

#### Scenario: Default judge is the completion seam

- **GIVEN** `answer.reasoning.judge` unset
- **WHEN** the inference gate runs
- **THEN** the same async seam type used by claim verification SHALL be used
- **AND** no ONNX or NLI runtime SHALL be imported

#### Scenario: Decision model judge returns a closed choice

- **GIVEN** `answer.reasoning.judge="onnx_decision"` with the runtime installed
- **WHEN** a claim is judged
- **THEN** the verdict SHALL be one of the four values
- **AND** the record SHALL carry `judge_confidence` in the closed interval
  0 to 1

#### Scenario: Missing runtime fails at composition

- **GIVEN** `answer.reasoning.judge="nli"` and the NLI runtime is not
  installed
- **WHEN** the engine is composed
- **THEN** composition SHALL fail with a message naming
  `ANSWER__REASONING__JUDGE` and the extra to install
- **AND** `core/reasoning` SHALL NOT have imported the runtime

#### Scenario: Layering enforced

- **GIVEN** the import-linter contracts
- **WHEN** they run
- **THEN** `omrg.core.reasoning` SHALL be listed as a source module of the
  core-business contract
- **AND** it SHALL import nothing from `omrg.integrations`,
  `omrg.transports`, `omrg.compose*` or `omrg.core.providers`

### Requirement: Reasoning cost and timing are disclosed

The answer tool description SHALL state that the concept frame adds one
completion call and that the inference gate adds one judge call per claim and
per inference. When diagnostics are requested and a gate ran, the result SHALL
include `concept_frame_ms`, `inference_ms`, `concept_frame_calls` and
`inference_calls`.

#### Scenario: Diagnostics when gates ran

- **GIVEN** both gates enabled and `include_diagnostics=true`
- **WHEN** an answer is produced
- **THEN** `diagnostics` SHALL contain all four fields

#### Scenario: Diagnostics when gates did not run

- **GIVEN** both gates disabled and `include_diagnostics=true`
- **WHEN** an answer is produced
- **THEN** `diagnostics` SHALL contain none of the four fields
