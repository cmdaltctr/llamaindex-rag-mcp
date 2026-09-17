# ocr-routing-evaluation Specification

## ADDED Requirements

### Requirement: OCR routing evaluation includes natural positives and negatives

The measured corpus SHALL include genuinely OCR-required PDFs and genuinely non-OCR PDFs.

#### Scenario: Held-out set contains only born-digital PDFs
- **WHEN** the held-out set has no genuine OCR-positive documents
- **THEN** the experiment SHALL NOT claim held-out OCR recall
- **AND** the result SHALL be incomplete for the primary safety question

### Requirement: OCR need is labelled independently

Ground-truth OCR need SHALL be assessed independently from the classifier and current routing output.

#### Scenario: Classifier says mixed
- **WHEN** `pdf-inspector` labels a PDF as `mixed`
- **THEN** the ground-truth label SHALL still come from page/content assessment
- **AND** `mixed` SHALL NOT automatically mean that whole-document OCR is correct

### Requirement: False negatives are a primary safety outcome

The experiment SHALL report OCR-required documents that remain on the fast path as a primary result.

#### Scenario: An OCR-required PDF is not routed
- **WHEN** the current policy keeps a genuinely OCR-required PDF on the fast path
- **THEN** the result SHALL record a false negative
- **AND** the report SHALL identify the lost or at-risk evidence separately from false-positive cost
- **AND** text lost by a reader fallback tier on a correctly routed PDF SHALL be reported as reader-quality loss, not as an OCR false negative

### Requirement: Routing is observed on the shipped reader path

The experiment SHALL score the routing decision made after the `pdf-inspector` reader fallback chain has run, not a replay of raw classifier output. Routing correctness SHALL be scored per document.

#### Scenario: A reader-failure PDF is rescued
- **WHEN** a `text_based` PDF extracts no text and the reader fallback chain recovers it
- **THEN** the gate SHALL be scored on the corrected `pages_needing_ocr` evidence
- **AND** a fast-path route SHALL count as correct, not as a false negative

### Requirement: Real OCR requires separate authorisation

Routing evaluation SHALL NOT perform real OCR without the repository's required recorded authorisation and budget controls.

#### Scenario: Routing-only execution is approved
- **WHEN** approval covers classification and routing only
- **THEN** OCR runtime and recovery quality SHALL be reported as unmeasured or projected
- **AND** no real OCR request SHALL run

### Requirement: Current thresholds stay fixed during measurement

Experiment 33 SHALL evaluate the packaged routing policy without changing the `0.5` confidence threshold or `0.10` page-fraction threshold during held-out scoring.

#### Scenario: A new threshold appears promising
- **WHEN** exploratory analysis suggests another threshold
- **THEN** the held-out result SHALL remain scored against the frozen packaged policy
- **AND** threshold recalibration SHALL require a separate proposal
