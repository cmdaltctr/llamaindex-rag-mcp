# Spec Delta

## ADDED Requirements

### Requirement: Answering can report its stage

The answering operation SHALL accept an optional stage callback. It SHALL call the callback once for each stage it enters, in this order: `searching`, `writing`, `citing`, `verifying`. A stage SHALL be reported when its work starts. A stage whose work does not run SHALL NOT be reported. `verifying` SHALL be reported only when claim verification is on, the answer is grounded and a judge model is available. With no callback, the operation and its result SHALL be unchanged. The result SHALL be the same with or without a callback.

#### Scenario: Full answer with verification

- **GIVEN** retrieval returns evidence, a model is available, claim verification is on and a judge model is set
- **WHEN** the answering operation runs with a stage callback
- **THEN** the callback MUST receive `searching`, `writing`, `citing` and `verifying` in that order, each once

#### Scenario: Verification is off

- **GIVEN** claim verification is off
- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST receive `searching`, `writing` and `citing`
- **AND** it MUST NOT receive `verifying`

#### Scenario: No judge model

- **GIVEN** claim verification is on and no judge model is set
- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST NOT receive `verifying`
- **AND** the result MUST report `verification_skipped` as before

#### Scenario: No evidence

- **GIVEN** retrieval returns nothing
- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST receive `searching` only
- **AND** it MUST NOT receive `writing`, because no model call is made

#### Scenario: No model, answering disabled or a bad request

- **WHEN** no answer model is available, answering is disabled, or the request fails its limits
- **THEN** the callback MUST receive no `writing` stage
- **AND** a disabled operation or a rejected request MUST report no stage at all

#### Scenario: A stage that fails is the last one reported

- **GIVEN** the model call fails after `writing` was reported
- **WHEN** the operation returns the generation failure result
- **THEN** the callback MUST NOT have received `citing` or `verifying`

#### Scenario: A failing callback never fails the answer

- **WHEN** the stage callback raises an error
- **THEN** the operation MUST log the error and continue
- **AND** the result MUST equal the result of a run without a callback

### Requirement: User-profile pipelines report the same stages

When a collection follows a user profile, the answering operation SHALL report stages with the same four names, the same order and the same rule: a stage is reported when its work starts. `searching` SHALL be reported when the first step of the Answer graph starts. `writing`, `citing` and `verifying` SHALL be reported only when a step does that work. A step that is bypassed, skipped, returns early or has an unknown operation SHALL report nothing. A stage SHALL NOT be reported twice in a row or after a later stage.

#### Scenario: Default Answer graph

- **GIVEN** the default Answer graph with claim verification on and a judge model set
- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST receive `searching`, `writing`, `citing` and `verifying` in that order, each once

#### Scenario: Verification is off in the settings

- **GIVEN** the default Answer graph and claim verification off, so the claim step starts and returns at once
- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST NOT receive `verifying`

#### Scenario: Claim step is switched off in the graph

- **GIVEN** the claim step is disabled in the graph, so the runner bypasses it
- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST NOT receive `verifying`

#### Scenario: No evidence in a graph run

- **GIVEN** the graph's retrieval steps return nothing, so the synthesis step starts and returns the no-evidence result
- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST receive `searching` only

#### Scenario: A user edits the graph

- **GIVEN** a graph with an extra step whose operation has no stage, and a graph without a citation step
- **WHEN** the operation runs with a stage callback
- **THEN** the answer MUST finish as it would without a callback
- **AND** the callback MUST receive only the stages whose work ran

#### Scenario: Several retrieval steps

- **GIVEN** a graph that runs a dense step, a sparse step and a rerank step
- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST receive `searching` once

#### Scenario: Both paths agree

- **GIVEN** the same question, collection content and settings
- **WHEN** it is answered through a built-in profile and through a user profile with the default Answer graph
- **THEN** both callbacks MUST receive the same stage list

### Requirement: The model call stays whole-reply

Reporting stages SHALL NOT change how the answer model is called. The grounded-answer seam SHALL return the whole reply and SHALL refuse streaming. No part of the answer text SHALL reach a stage callback.

#### Scenario: Seam still refuses streaming

- **WHEN** a caller asks the grounded-answer seam for a streamed completion
- **THEN** the seam MUST refuse as before

#### Scenario: Callback sees no text

- **WHEN** the operation runs with a stage callback
- **THEN** the callback MUST receive stage names only
- **AND** it MUST NOT receive question text, evidence text, answer text or error text
