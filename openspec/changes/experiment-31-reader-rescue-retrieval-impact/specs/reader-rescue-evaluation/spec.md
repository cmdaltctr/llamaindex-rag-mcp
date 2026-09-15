# reader-rescue-evaluation Specification

## ADDED Requirements

### Requirement: Reader rescue evaluation uses paired cells

The experiment SHALL compare a `pdf-inspector`-only control with the current tiered reader rescue chain while keeping downstream retrieval variables fixed.

#### Scenario: A PDF has an empty control extraction
- **GIVEN** a measured PDF for which `pdf-inspector` returns no usable gold evidence
- **WHEN** both experiment cells ingest the same source
- **THEN** the control SHALL stop at the `pdf-inspector` result
- **AND** the candidate SHALL use the current configured rescue chain

### Requirement: Held-out evidence is independent of candidate design

The measured held-out corpus SHALL exclude documents used to design, debug, or select the reader rescue behaviour.

#### Scenario: A known Experiment 30 failure is reused
- **WHEN** a known failure document is used to verify the harness
- **THEN** it SHALL be labelled as development or regression evidence
- **AND** it SHALL NOT be counted as independent held-out evidence

### Requirement: Gold evidence is defined from the source document

Gold evidence SHALL be labelled from the source PDF independently of either extracted representation.

#### Scenario: Reader outputs disagree
- **WHEN** the two readers emit different text
- **THEN** scoring SHALL use source-grounded evidence labels
- **AND** it SHALL NOT treat either extraction as automatic ground truth

### Requirement: Retrieval impact is measured after evidence recovery

The experiment SHALL report evidence recoverability and downstream retrieval metrics separately.

#### Scenario: Evidence is recovered but not retrieved
- **WHEN** the candidate extraction contains the gold evidence but search misses it
- **THEN** the report SHALL classify the parser stage as successful
- **AND** it SHALL record the retrieval miss separately

### Requirement: Production behaviour is unchanged by the experiment

Experiment 31 SHALL NOT change packaged reader defaults, fallback order, OCR policy, or public APIs.

#### Scenario: Results suggest a production change
- **WHEN** the final report recommends changing production behaviour
- **THEN** that change SHALL require a separate OpenSpec proposal and decision record
