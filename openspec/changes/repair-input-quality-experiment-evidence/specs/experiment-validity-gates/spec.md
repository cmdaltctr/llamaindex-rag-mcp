## ADDED Requirements

### Requirement: Verdicts require complete identified observations

An experiment summariser SHALL check each measured cell against its declared observation set before evaluating gates. Each expected observation SHALL occur exactly once. Comparisons SHALL join observations by identity and validate their declared workload classes. Missing observations SHALL produce INCOMPLETE; duplicate, unexpected or incompatible observations SHALL produce INVALID. Neither status SHALL produce a promotion recommendation.

#### Scenario: A smoke run would pass the numeric gates
- **WHEN** a runner records only a permitted smoke subset of the full declared query set
- **THEN** the summariser SHALL report INCOMPLETE
- **AND** it SHALL NOT report PASS or recommend promotion even if the subset clears every numeric threshold

#### Scenario: Equal counts hide different query membership
- **WHEN** two cells have equal row counts but different query identities or workload labels
- **THEN** the summariser SHALL report INVALID before evaluating a paired effect

#### Scenario: Complete historical cells remain valid
- **WHEN** all declared observations occur exactly once with matching provenance
- **THEN** summarisation SHALL reproduce the applicable frozen-gate verdict
- **AND** the original raw records SHALL remain unchanged

### Requirement: Checkpoint reuse requires matching measurement identity

Resuming an experiment SHALL validate its corpus, observation identifiers, plan, effective treatments and relevant code and dependency provenance before skipping work. A changed population or routing policy SHALL require a distinct run or an explicit compatible migration. Local document mappings SHALL remain stable across resume. A checkpoint without sufficient provenance SHALL remain usable as labelled historical evidence and SHALL NOT silently authorise new work or a mixed-provenance run.

#### Scenario: A document is added to the selected collection
- **WHEN** the collection identity differs from the saved checkpoint
- **THEN** the runner SHALL refuse resume before replacing its saved mapping or recording measurements
- **AND** it SHALL explain how to start a separate run

#### Scenario: The routing policy changes
- **WHEN** saved classifications contain decisions from another routing-policy revision
- **THEN** the runner SHALL NOT treat those decisions as measurements of the current revision
- **AND** a replay SHALL identify both the source evidence and the evaluated policy

### Requirement: Paid rebuilds require current estimates and approval

An experiment rebuild SHALL preserve existing indexes and require an offline estimate of the actual prepared embedding requests. The estimate SHALL cover the declared corpus and effective configuration, report token counts and an explicit pricing basis, and distinguish estimated cost from billing. Paid execution SHALL require operator approval tied to that estimate, destination and spending limit. Missing, invalid or stale estimates SHALL block spending. The experiment 25 estimate SHALL display baseline and candidate token counts, their percentage difference and approximate monetary cost before requesting spending approval. The frozen 15% extra-token threshold SHALL evaluate experiment acceptance only. Exceeding that threshold SHALL NOT invalidate an otherwise valid estimate or block an approved build. A force option SHALL NOT bypass the estimate, approval or destination checks.

#### Scenario: A forced rebuild has no approved estimate
- **WHEN** the operator requests a forced rebuild without a valid approved estimate
- **THEN** the builder SHALL stop before any paid request
- **AND** it SHALL explain the missing approval or estimate

#### Scenario: The approved inputs change
- **WHEN** corpus, tokenizer, embedding configuration, request preparation or destination differs from the approved estimate
- **THEN** the builder SHALL refuse to use that approval

#### Scenario: Offline accounting encounters a fallback
- **WHEN** preparation cannot reproduce the declared tokenizer or request-text contract
- **THEN** the estimate SHALL be invalid
- **AND** it SHALL NOT authorise a paid build

#### Scenario: The candidate estimate exceeds the 15% threshold
- **WHEN** a valid candidate estimate exceeds the baseline token count by more than 15%
- **THEN** the builder SHALL display the estimated token increase and approximate cost and request spending approval
- **AND** it SHALL permit the build when valid approval matches the estimate, destination and spending limit
- **AND** the frozen 15% threshold SHALL remain unchanged for evaluating the measured experiment result

#### Scenario: A rebuild is approved
- **WHEN** a valid estimate and explicit approval match the requested build
- **THEN** the builder SHALL use a separate approved output location
- **AND** it SHALL leave the preserved historical index unchanged

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

### Requirement: Reports distinguish measurements from explanations and decisions

Reports SHALL distinguish measured results, projections, exploratory interpretations and approved operator decisions. A statistical calculation SHALL NOT be presented as the source of an operator-selected practical threshold. Historical gates and raw evidence SHALL be preserved when explanations are corrected. A machine verdict SHALL NOT be recorded as operator acceptance without explicit approval.

#### Scenario: Runtime is extrapolated from fixtures
- **WHEN** a report estimates corpus runtime from fixture timings
- **THEN** it SHALL label the runtime and derived slowdown as projections
- **AND** it SHALL state assumptions including whole-request timeout behaviour

#### Scenario: A metric matches while rankings differ
- **WHEN** repeated retrieval measurements have equal recall but different returned rankings
- **THEN** the report SHALL describe the measured agreement and differences
- **AND** it SHALL NOT claim that metric equality proves deterministic execution

#### Scenario: The operator has not decided whether to promote OCR
- **WHEN** the experiment has a verdict but operator approval remains outstanding
- **THEN** the decision record and promotion task SHALL remain pending
- **AND** packaged defaults SHALL remain unchanged

#### Scenario: A repeated combined experiment has no approved purpose
- **WHEN** the operator has not confirmed that the combined treatment is still a desired candidate
- **THEN** the workflow SHALL retain the historical result and defer new paid measurement
- **AND** the decision to rerun or close the repeat request SHALL be recorded explicitly
