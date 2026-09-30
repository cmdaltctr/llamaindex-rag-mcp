# local-tier-escalation-evaluation Specification

## Purpose

Defines how OMRG evaluates an escalation rule for the local OCR tier before any change replaces the shipped confidence post-check.

## ADDED Requirements

### Requirement: Escalation rules SHALL be scored on existing local OCR rows against frozen labels

The evaluation SHALL use the Experiment 33 local OCR rows and saved page text, and the frozen body recall of each row. It SHALL NOT run new OCR. `freeze.py --check` SHALL pass before any label is read.

#### Scenario: Rule needs a signal the rows do not hold

- **WHEN** a candidate needs engine output that the rows and saved text do not contain
- **THEN** the candidate is reported as not testable on this data
- **AND** no OCR is run to produce the signal

### Requirement: Pass criteria SHALL be fixed before the run

The protocol SHALL state, before any candidate is scored, the bound on non-Latin pages kept, the bound on the share of kept pages with body recall below 0.5, and the bound on the share escalated, each with a reason.

#### Scenario: Candidate meets the recall bound by escalating too much

- **WHEN** a candidate keeps no page below 0.5 recall but escalates more than the committed bound
- **THEN** the candidate fails

### Requirement: Pages the local model cannot read SHALL NOT be kept

A passing rule SHALL keep zero pages from documents in a script the packaged model has no recogniser for.

#### Scenario: One Arabic page passes the confidence cut

- **WHEN** a rule keeps one `io02` page whose local recall is 0.000
- **THEN** the rule fails this criterion

### Requirement: The typography blind spot SHALL be reported apart

The evaluation SHALL report `io06` apart from the gated population, and SHALL state whether any signal in the rows separates it.

#### Scenario: No row signal separates io06

- **WHEN** no candidate escalates a majority of the `io06` pages with recall below 0.5
- **THEN** the report names the engine output a future rule would need

### Requirement: Production behaviour SHALL stay unchanged by the experiment

The experiment SHALL NOT change `OCR_LOCAL_MIN_CONFIDENCE`, the post-check, or any default.

#### Scenario: Combination rule passes

- **WHEN** the report recommends a combination rule
- **THEN** production keeps the ADR-069 post-check until a separate change ships
