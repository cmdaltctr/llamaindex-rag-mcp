## ADDED Requirements

### Requirement: Worker sample review SHALL measure PaddleOCR-VL on real corpus documents before fix work

The isolated OCR worker's output quality on the corpus SHALL be established by operator review of a bounded sample before any follow-up fix work is planned against it. The sample SHALL be frozen in a committed manifest before the run, SHALL not exceed 50 pages, and SHALL include the named problem documents (early-modern typography, multi-column with images, two-column and table pages) plus at least one clean control document. The corpus and its labels SHALL be read-only for the run.

The run SHALL drive the worker through its protocol with a per-document soft timeout and a wall-clock cap, checkpointing per document so an interruption resumes without re-running completed documents. The review surface SHALL present the original page image beside the worker's extracted Markdown for every sampled page, and SHALL persist the operator's per-page checklist verdicts to a committed JSON file. The verdicts, not automatic scores, are the experiment's result.

#### Scenario: The sample is frozen before any worker page runs

- **GIVEN** the Experiment 33 corpus and labels in their worktree
- **WHEN** the sample manifest is prepared
- **THEN** it SHALL list at most 50 pages including the operator's spot-checked problem pages
- **AND** it SHALL be committed before the worker run starts
- **AND** the corpus and labels SHALL not be modified

#### Scenario: The operator reviews original against extraction

- **WHEN** the worker run completes for the sampled pages
- **THEN** a review page SHALL show each page's original image and the worker's Markdown side by side
- **AND** a per-page checklist SHALL record text accuracy, column order, heading structure, table readability, readiness for an LLM, and a free-text note
- **AND** the saved verdicts SHALL be committed unchanged as the experiment's result

#### Scenario: An interrupted run resumes cleanly

- **GIVEN** the worker run stopped before completing the sample
- **WHEN** the run is restarted
- **THEN** completed documents SHALL not be re-run
- **AND** the run SHALL continue within the same budget rules
