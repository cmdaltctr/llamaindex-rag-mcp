# ocr-routing-evaluation Specification

## ADDED Requirements

### Requirement: OCR routing evaluation includes natural positives and negatives

The measured corpus SHALL include genuinely OCR-required PDFs and genuinely non-OCR PDFs.

#### Scenario: Held-out set contains only born-digital PDFs
- **WHEN** the held-out set has no genuine OCR-positive documents
- **THEN** the experiment SHALL NOT claim held-out OCR recall
- **AND** the result SHALL be incomplete for the primary safety question

#### Scenario: Only synthetic positives are present
- **WHEN** every OCR-positive document in the corpus is synthetic
- **THEN** the experiment SHALL NOT claim natural held-out OCR recall

### Requirement: OCR need is labelled independently

Ground-truth OCR need SHALL be assessed independently from the classifier and current routing output.

#### Scenario: Classifier says mixed
- **WHEN** `pdf-inspector` labels a PDF as `mixed`
- **THEN** the ground-truth label SHALL still come from page/content assessment
- **AND** `mixed` SHALL NOT automatically mean that whole-document OCR is correct

### Requirement: Scans with an existing OCR text layer are a distinct class

The natural corpus SHALL include scanned PDFs carrying an existing OCR text layer, labelled apart from image-only scans and reader-failure PDFs.

#### Scenario: Junk OCR text layer
- **WHEN** a page's existing text layer does not match its rendered page image under the frozen usability rule
- **THEN** the page SHALL be labelled `needs_ocr`
- **AND** the label SHALL NOT be decided by character count alone
- **AND** a fast-path route of a document above tolerance SHALL count as a false negative

#### Scenario: Faithful OCR text layer
- **WHEN** the existing text layer matches the rendered page image
- **THEN** the page SHALL be labelled `usable`
- **AND** a fast-path route SHALL count as correct

### Requirement: Unrecoverable content is labelled apart from OCR need

Labels SHALL include `unrecoverable` for content that no reader or OCR engine can be expected to recover.

#### Scenario: Stage A scoring
- **WHEN** a document is labelled `unrecoverable`
- **THEN** it SHALL be excluded from routing recall and precision denominators
- **AND** its routing decision SHALL be reported separately

#### Scenario: Stage B output on unrecoverable pages
- **WHEN** real OCR runs on an unrecoverable page
- **THEN** the result SHALL record whether a failure was reported or text was emitted
- **AND** emitted text SHALL NOT be counted as recovery

### Requirement: Synthetic degraded documents are reported apart

Synthetic documents SHALL be labelled synthetic and SHALL NOT contribute to natural held-out measurements.

#### Scenario: Character error rate
- **WHEN** real OCR runs on a synthetic document
- **THEN** CER SHALL be computed against the source PDF text
- **AND** degradation parameters, seed, and source hash SHALL be recorded

#### Scenario: Boundary probe
- **WHEN** synthetic documents probe the page-fraction boundary
- **THEN** results SHALL be reported as exploratory
- **AND** the frozen thresholds SHALL NOT change

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
