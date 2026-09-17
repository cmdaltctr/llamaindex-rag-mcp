# reader-rescue-evaluation Specification

## Purpose

Defines the controlled evaluation contract for measuring whether the tiered PDF reader rescue path improves evidence recovery and retrieval.

## Requirements

### Requirement: Reader rescue evaluation uses paired cells

The experiment SHALL run a `pdf-inspector`-only sanity-check cell, the current tiered reader rescue chain as the candidate, and a pypdf-only rescue as the reference, while keeping downstream retrieval variables fixed. The candidate against the reference SHALL be the measured comparison.

#### Scenario: A PDF has an empty control extraction
- **GIVEN** a measured PDF that meets the rescue trigger
- **WHEN** all experiment cells ingest the same source
- **THEN** the sanity-check cell SHALL stop at the `pdf-inspector` result and produce zero chunks
- **AND** the candidate SHALL use the current configured rescue chain
- **AND** the reference SHALL use pypdf as the only rescue tier

#### Scenario: The sanity-check cell produces chunks
- **WHEN** the sanity-check cell produces one or more chunks for a measured PDF
- **THEN** the harness SHALL treat the PDF as failing the trigger check
- **AND** it SHALL NOT count the PDF as held-out evidence

### Requirement: Measured PDFs meet the production rescue trigger

A measured held-out PDF SHALL be classified as text-based, SHALL have at least one page, and SHALL return an empty `pdf-inspector` extraction.

#### Scenario: A PDF has a partial extraction
- **WHEN** a candidate PDF returns partial or whitespace-only text from `pdf-inspector`
- **THEN** it SHALL be excluded from the measured corpus
- **AND** the report SHALL record the count of excluded partial extractions

### Requirement: Held-out evidence is independent of candidate design

The measured held-out corpus SHALL exclude documents used to design, debug, or select the reader rescue behaviour.

#### Scenario: A known Experiment 30 failure is reused
- **WHEN** a known failure document is used to verify the harness
- **THEN** it SHALL be labelled as development or regression evidence
- **AND** it SHALL NOT be counted as independent held-out evidence

### Requirement: Measured indexes contain distractor documents

Each cell SHALL index the held-out PDFs together with the same frozen set of healthy distractor PDFs.

#### Scenario: A query targets one held-out PDF
- **WHEN** a measured query runs in any cell
- **THEN** retrieval SHALL search an index that also contains the other held-out PDFs and the distractor PDFs

### Requirement: OCR routing does not rescue any cell

The experiment SHALL disable OCR worker dispatch in all cells and SHALL record per document whether OCR was required and whether OCR was used.

#### Scenario: A measured document uses OCR
- **WHEN** any measured document reports that OCR was used
- **THEN** the harness SHALL abort that cell
- **AND** it SHALL NOT report scores for the aborted cell

### Requirement: Gold evidence is defined from the source document

Gold evidence SHALL be labelled from the source PDF independently of any extracted representation.

#### Scenario: Reader outputs disagree
- **WHEN** the readers emit different text
- **THEN** scoring SHALL use source-grounded evidence labels
- **AND** it SHALL NOT treat any extraction as automatic ground truth

### Requirement: Evidence matching uses one frozen text-span rule

Qrels SHALL store gold evidence as text spans. One matching rule, frozen before measured runs, SHALL decide both evidence recoverability and retrieval hits in every cell.

#### Scenario: Cells split the same text differently
- **WHEN** two cells extract the same evidence with different line breaks, hyphenation, or chunk boundaries
- **THEN** scoring SHALL apply the same normalised matching rule in both cells
- **AND** it SHALL NOT use chunk identifiers as qrels

### Requirement: Retrieval impact is measured after evidence recovery

The experiment SHALL report evidence recoverability and downstream retrieval metrics separately.

#### Scenario: Evidence is recovered but not retrieved
- **WHEN** a rescue cell's extraction contains the gold evidence but search misses it
- **THEN** the report SHALL classify the parser stage as successful
- **AND** it SHALL record the retrieval miss separately

### Requirement: Production behaviour is unchanged by the experiment

Experiment 31 SHALL NOT change packaged reader defaults, fallback order, OCR policy, or public APIs.

#### Scenario: Results suggest a production change
- **WHEN** the final report recommends changing production behaviour
- **THEN** that change SHALL require a separate OpenSpec proposal and decision record
