# rescue-quality-evaluation Specification

## Purpose

Defines how OMRG evaluates a quality signal on reader-rescue text before any change lets that signal decide whether a rescue zeroes OCR evidence.

## ADDED Requirements

### Requirement: Junk rescue text SHALL be defined by the frozen recall labels

The evaluation SHALL score each rescue text against the Experiment 33 frozen reference transcription with the Experiment 33 token rule. It SHALL use the thresholds of the frozen page rule. Text with body token recall below 0.50 is `junk`. Text with recall of 0.80 or more is `healthy`. Text between the two is `grey` and is reported, not scored. Pages whose reference has fewer than 10 body tokens, and pages the frozen labels mark `unrecoverable` or `ambiguous`, SHALL be excluded.

#### Scenario: Handwritten page with a junk text layer

- **WHEN** LiteParse returns text for a page and that text has body token recall 0.24 against the reference
- **THEN** the page is `junk` for that rescue tier

#### Scenario: Labels are verified before use

- **WHEN** the run starts
- **THEN** `freeze.py --check` for Experiment 33 SHALL pass before any label or transcription is read
- **AND** no label SHALL be edited

### Requirement: Adoption margin SHALL be fixed before the run

The protocol SHALL state, before any candidate is scored, the margin by which the model candidate must beat the deterministic candidate, with a reason for the number. A model candidate SHALL be adopted only if it beats the deterministic candidate by that margin and passes every gate.

#### Scenario: Model candidate wins by less than the margin

- **WHEN** Julia 1 junk recall exceeds candidate A by less than the committed margin
- **THEN** candidate A is the recommended signal, if it passes the gates

### Requirement: False-positive cost SHALL be measured at page and document level

The evaluation SHALL report the share of `healthy` pages flagged, and SHALL report every document labelled `usable` that the signal would newly route to OCR. The OCR gate thresholds `0.5` and `0.10` SHALL NOT change.

#### Scenario: Signal flags healthy pages in one document

- **WHEN** flagged healthy pages reach 10% of a `usable` document's pages
- **THEN** the report names that document as newly routed and states the projected OCR cost

### Requirement: Motivating misses SHALL be checked at document level

The evaluation SHALL report whether `rf06` and `rf07` would route to OCR when the candidate's flags count as pages needing OCR.

#### Scenario: Signal catches the handwritten records

- **WHEN** the candidate flags at least 10% of the pages of `rf06` and of `rf07`
- **THEN** both documents count as routed for that candidate

### Requirement: Candidate models SHALL run locally without PyTorch in OMRG

Every candidate SHALL run on the operator's machine. No page text SHALL leave the machine. The evaluation SHALL NOT add PyTorch to the OMRG install. A model download SHALL wait for operator approval.

#### Scenario: Hosted model proposed

- **WHEN** a candidate needs a hosted service that receives page text
- **THEN** it is excluded from the evaluation

#### Scenario: ONNX route does not match the reference model

- **WHEN** the ONNX parity check fails its preregistered bound
- **THEN** candidate B is not scored, and the operator decides the runtime

### Requirement: Production behaviour SHALL stay unchanged by the experiment

The experiment SHALL NOT change TDR-024 behaviour, the reader chain or any default. A winning signal SHALL need its own proposal and ADR.

#### Scenario: Candidate A passes every gate

- **WHEN** the report recommends candidate A
- **THEN** production still zeroes OCR evidence after a successful rescue until a separate change ships
