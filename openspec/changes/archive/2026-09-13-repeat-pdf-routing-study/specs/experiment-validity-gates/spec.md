## ADDED Requirements

### Requirement: PDF routing evaluations use approved cohorts and independent labels

A PDF routing evaluation SHALL record the operator-approved inclusion rule and selected documents before measurement. Ground-truth labels SHALL include an independent assessment of relevant page content, distinct from the classifier's output and aggregate character counts. Ambiguous cases SHALL be recorded explicitly. The protocol SHALL define how missing pages and whole-document routing are judged. Documents used to develop a candidate SHALL NOT count as independent held-out validation of that candidate.

#### Scenario: The operator selects papers and a long book
- **WHEN** the approved collection includes selected papers and a book as a stress case
- **THEN** discovery SHALL be limited to that selection
- **AND** reporting SHALL identify the collection composition without claiming it represents paper-only prevalence

#### Scenario: A long document has some unreadable pages
- **WHEN** aggregate character counts are high but relevant pages lack usable text
- **THEN** the evaluation SHALL retain the independently assessed missing-page evidence
- **AND** it SHALL apply the agreed routing judgement rather than infer correctness from the aggregate alone

#### Scenario: A known failure motivates a new rule
- **WHEN** a candidate was designed after examining a document
- **THEN** a successful replay on that document SHALL be labelled a development regression check
- **AND** independent validation SHALL use other approved documents whose outcomes were withheld during candidate design

### Requirement: Public experiment failures preserve document privacy

Public experiment records SHALL exclude private document names, paths and extracted text, including failure cases. Public error information SHALL use approved codes or classes. Detailed private diagnostics and identity mappings SHALL remain in ignored local storage. Privacy checks SHALL inspect serialised outputs rather than rely only on declarations of intended behaviour.

#### Scenario: An exception includes a document path
- **WHEN** document processing raises an exception containing private text or a path
- **THEN** the public checkpoint SHALL contain only approved diagnostic fields
- **AND** the private exception message SHALL NOT appear in public reports

### Requirement: Repeat-study protocols freeze before held-out measurement

A repeat routing study SHALL record the approved candidate, labels, development/held-out split and acceptance criteria in a committed artefact before any held-out scoring. Held-out outcomes SHALL NOT guide candidate design. The comparison SHALL evaluate the approved candidate against the historical policy pinned at its original revision; the current working tree SHALL NOT serve as an unnamed baseline. Negative results SHALL be retained and reported.

#### Scenario: Candidate designed on development evidence
- **WHEN** a candidate rule is developed using the approved book and development documents
- **THEN** the frozen protocol commit SHALL precede the first held-out measurement
- **AND** held-out documents SHALL be disjoint from every document examined during design

#### Scenario: Working tree differs from the historical policy
- **WHEN** the comparison runs
- **THEN** the baseline SHALL be the committed historical policy at its pinned revision
- **AND** uncommitted local changes SHALL NOT silently become the baseline

### Requirement: Real OCR measurement requires separate authorisation

A routing classification and replay evaluation SHALL NOT perform real OCR requests without a separate recorded authorisation naming the selected documents, a timeout and a runtime budget. A classification-only run SHALL report OCR cost as a projection and extraction-recovery quality as unmeasured. Fixture-derived runtime estimates SHALL be labelled as projections with their assumptions stated.

#### Scenario: Classification-only run
- **WHEN** the authorised scope covers classification and routing replay only
- **THEN** the report SHALL label any OCR runtime and slowdown figures as projections
- **AND** it SHALL record recovery quality as unmeasured rather than inferred

#### Scenario: OCR authorised for selected documents
- **WHEN** the operator authorises real OCR for a named document subset with a timeout and runtime budget
- **THEN** the measurement SHALL record elapsed classification time, timeout and failure behaviour and extraction outcomes
- **AND** it SHALL stop before exceeding the authorised budget
