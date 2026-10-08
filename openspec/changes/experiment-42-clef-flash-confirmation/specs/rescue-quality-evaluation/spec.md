## ADDED Requirements

### Requirement: A confirmatory evaluation SHALL use only unseen documents

A confirmatory evaluation SHALL score only documents that no earlier rescue-quality experiment used. It SHALL check every new document against the earlier sets by SHA-256 and by source identifier before labelling.

#### Scenario: A new document matches an Experiment 33 document

- **WHEN** a sourced PDF has the same SHA-256 or the same source identifier as an Experiment 33 or Experiment 38 document
- **THEN** the document is removed from the confirmatory set
- **AND** the sourcing log records the removal

### Requirement: Confirmatory thresholds SHALL be frozen before any new document is scored

A confirmatory evaluation SHALL fit each candidate threshold once, on the earlier experiment's documents only. It SHALL record each value, the hash of its input and the git commit in `plan.json` before any new document is scored. It SHALL NOT refit a threshold on the new documents.

#### Scenario: Threshold recorded before scoring

- **WHEN** the first new page is sent to a candidate
- **THEN** `plan.json` already holds the frozen threshold for that candidate, with its input hash and commit

#### Scenario: Threshold fitted on the new documents

- **WHEN** the report shows a threshold fitted on the new documents
- **THEN** the report labels it as a diagnostic
- **AND** it does not decide any gate or the verdict

### Requirement: Gate priority SHALL be recorded before the run

The protocol SHALL state which gates are primary and which are secondary before any page is scored. The operator SHALL make this choice. When the protocol names no priority, every gate is primary. The priority SHALL NOT change after any score exists.

#### Scenario: Priority not recorded

- **WHEN** `plan.json` has no operator decision on gate priority
- **THEN** no page is scored

#### Scenario: Secondary gate missed

- **WHEN** the candidate passes every primary gate and misses a secondary gate
- **THEN** the verdict follows the primary gates
- **AND** the report states the secondary result and its interval in the verdict line

### Requirement: A confirmatory set SHALL meet a sample size stated before sourcing

The protocol SHALL state, before sourcing, minimum counts of healthy pages, junk pages, documents with a junk text layer and `usable` documents, and the largest share of junk pages one document may hold. It SHALL give the reason for each number. The run SHALL NOT start when a minimum is missed, unless a dated amendment written before any score accepts the smaller set.

#### Scenario: Too few healthy pages

- **WHEN** the labelled set holds fewer healthy pages than the stated minimum
- **THEN** scoring does not start
- **AND** the operator extends sourcing or records an amendment with a new power statement

#### Scenario: One document dominates the junk pages

- **WHEN** one document holds more than the stated share of junk pages
- **THEN** scoring does not start until sourcing adds documents or an amendment records the exception

### Requirement: A local decision-model runtime SHALL be verified before scoring

Before a local decision model scores any page, the run SHALL record and check the runtime build, the SHA-256 of the model file and the server bind address. The server SHALL accept connections only on `127.0.0.1`. The run SHALL reproduce a fixed set of earlier scores within a stated bound. Timing SHALL be measured with one request at a time.

#### Scenario: Model file hash differs

- **WHEN** the model file SHA-256 differs from the hash in `plan.json`
- **THEN** no page is scored

#### Scenario: Earlier scores do not reproduce

- **WHEN** a reproduction page differs from its committed score by more than the stated bound
- **THEN** scoring stops and the report records the build difference

## MODIFIED Requirements

### Requirement: Junk rescue text SHALL be defined by the frozen recall labels

The evaluation SHALL score each rescue text against a reference transcription with the Experiment 33 token rule. It SHALL use the thresholds of the frozen page rule. Text with body token recall below 0.50 is `junk`. Text with recall of 0.80 or more is `healthy`. Text between the two is `grey` and is reported, not scored. Pages whose reference has fewer than 10 body tokens, and pages the labels mark `unrecoverable` or `ambiguous`, SHALL be excluded. For Experiment 33 documents the reference is the frozen Experiment 33 transcription. For new documents the reference SHALL be made on the operator's machine and frozen by hash before any candidate scores a page.

#### Scenario: Handwritten page with a junk text layer

- **WHEN** LiteParse returns text for a page and that text has body token recall 0.24 against the reference
- **THEN** the page is `junk` for that rescue tier

#### Scenario: Labels are verified before use

- **WHEN** the run starts
- **THEN** `freeze.py --check` for Experiment 33 SHALL pass before any label or transcription is read
- **AND** no label SHALL be edited

#### Scenario: New documents are labelled locally

- **WHEN** a confirmatory run labels new documents
- **THEN** no page text or page image leaves the machine without a dated, operator-approved amendment
- **AND** the experiment's own `freeze.py --check` passes before any candidate scores a page

### Requirement: Adoption margin SHALL be fixed before the run

The protocol SHALL state, before any candidate is scored, the margin by which the model candidate must beat the deterministic candidate, with a reason for the number. A model candidate SHALL be adopted only if it beats the deterministic candidate by that margin and passes every primary gate. When the protocol names no gate priority, every gate is primary.

#### Scenario: Model candidate wins by less than the margin

- **WHEN** Julia 1 junk recall exceeds candidate A by less than the committed margin
- **THEN** candidate A is the recommended signal, if it passes the gates

#### Scenario: Model candidate passes primary gates and beats the margin

- **WHEN** Clef-flash beats candidate A by the committed margin and passes every primary gate
- **THEN** the verdict is PASS, and adoption still needs its own proposal and ADR

### Requirement: Motivating misses SHALL be checked at document level

The evaluation SHALL report whether `rf06` and `rf07` would route to OCR when the candidate's flags count as pages needing OCR. A confirmatory evaluation on new documents SHALL report the same for every document with a junk text layer: a document whose `junk` rescue pages reach 10% of its pages.

#### Scenario: Signal catches the handwritten records

- **WHEN** the candidate flags at least 10% of the pages of `rf06` and of `rf07`
- **THEN** both documents count as routed for that candidate

#### Scenario: A junk-layer document in the new set stays on the fast path

- **WHEN** a document with a junk text layer does not route under the candidate's flags
- **THEN** the report names the document and G1 fails
