## ADDED Requirements

### Requirement: Experiment 25 remains closed during the evidence repair

The repair SHALL preserve Experiment 25's historical COMPLETE PASS result,
ADR-063, original plans, raw evidence, indexes and unconditional build
refusal. It SHALL record that the operator declined a rerun on 2026-09-10.
It SHALL NOT introduce Experiment 25 implementation code, a rerun, a live
builder, compatibility repairs or paid-run infrastructure. ADR-064 SHALL
also remain unchanged.

#### Scenario: Later repair work encounters the old estimator suggestion
- **GIVEN** an older record suggests implementing a future pre-spend estimator
- **WHEN** the local agent performs this repair
- **THEN** it records the declined rerun in an additive close-out record
- **AND** it leaves the refusal, historical result and original records unchanged
- **AND** it does not implement the suggested estimator

#### Scenario: Preserved evidence changes
- **GIVEN** baseline hashes were recorded before repair
- **WHEN** a protected Experiment 25 or ADR file differs afterwards
- **THEN** preservation verification fails
- **AND** the stage cannot be marked complete by refreshing the expected hash

### Requirement: Experiment 26 and 27 verdicts require complete query evidence

Experiment 26 and 27 summarisers SHALL validate every required cell against
the frozen ground truth before producing a performance verdict. They SHALL
require exactly one row per expected query, consistent categories, valid
rankings and finite non-negative measured latencies. Checkpoint completion
IDs SHALL be unique and agree with row IDs. Ground-truth IDs SHALL also be
unique. Experiment 27 SHALL validate its reference cells as well as its two
measured cells.

#### Scenario: Equally sized incomplete Experiment 26 arms
- **GIVEN** both arms contain the same proper subset of the 223 expected queries
- **WHEN** the summariser assesses them
- **THEN** evidence is INCOMPLETE
- **AND** the performance verdict is null and the command exits non-zero

#### Scenario: Equal counts conceal duplicate or mismatched IDs
- **GIVEN** two arms have equal counts but contain duplicate, unknown or differing query IDs
- **WHEN** validation runs
- **THEN** it refuses a performance verdict
- **AND** it does not calculate the verdict from their intersection

#### Scenario: Experiment 27 reference cell is incomplete
- **GIVEN** both measured cells are complete but an earlier reference cell is incomplete
- **WHEN** the four-cell comparison is assembled
- **THEN** the assembled comparison cannot receive a PASS or FAIL performance verdict
- **AND** the assessment identifies the incomplete reference cell

#### Scenario: Malformed observations
- **GIVEN** a row has a missing ranking, invalid category, negative latency, NaN or infinity
- **WHEN** the summariser validates evidence
- **THEN** it records INVALID evidence and refuses the performance verdict
- **AND** it does not substitute zero for the missing observation

#### Scenario: Valid empty retrieval result
- **GIVEN** a complete supported observation contains an empty ranked parent-ID list
- **WHEN** the query is scored
- **THEN** it receives the existing zero-quality score
- **AND** the empty result is not treated as missing execution

#### Scenario: Completion metadata disagrees with rows
- **GIVEN** a checkpoint lists a completed ID without its row or repeats a completed ID
- **WHEN** validation runs
- **THEN** it refuses a performance verdict and identifies invalid completion evidence

### Requirement: Repaired gate evaluation retains precision and frozen rules

Experiment 26 and 27 gate comparisons SHALL use unrounded values and the
frozen plan's required gate definitions. Formatting SHALL NOT affect
decisions. Missing or duplicate required gates, unsupported comparators or
changed thresholds SHALL cause refusal. Metric definitions and the existing
percentile convention SHALL remain unchanged.

#### Scenario: Rounded recall would cross a threshold
- **GIVEN** an unrounded recall is just below its frozen minimum
- **AND** display rounding would put it at that minimum
- **WHEN** the gate is evaluated
- **THEN** the gate fails using the unrounded value

#### Scenario: Rounded latency would pass a cap
- **GIVEN** unrounded p95 latency is just above its frozen cap
- **WHEN** the gate is evaluated
- **THEN** the gate fails even if the displayed value rounds to the cap

#### Scenario: Required gate is absent
- **GIVEN** a required gate is missing or duplicated
- **WHEN** the summariser attempts a verdict
- **THEN** evidence is INVALID and no PASS is emitted

### Requirement: Recovery and recomputation preserve historical provenance

The local agent SHALL inspect and selectively restore only provenance-checked
recovery candidates. It SHALL record input SHA-256 hashes, origins and
selection rationale. It SHALL NOT extract an archive wholesale over the
checkout, fabricate unavailable recovery content, overwrite original evidence
or present current observations as historical runtime facts.

#### Scenario: Recovery candidate has no established origin
- **GIVEN** a local recovery file differs from the committed file
- **AND** its relationship to the historical run cannot be established
- **WHEN** it is assessed
- **THEN** it remains unverified
- **AND** it is not used to support an admissible verdict

#### Scenario: Historical runtime manifest lacks mandatory provenance
- **GIVEN** rows exist but historical effective execution is not established under TDR-014
- **WHEN** an amended assessment is produced
- **THEN** it states the missing provenance and withholds a fresh performance verdict
- **AND** descriptive recomputed tables, if present, are explicitly labelled
- **AND** current settings are not inserted into the historical manifest

#### Scenario: Valid recovery input is used
- **GIVEN** a recovery candidate has verified origin and is selected
- **WHEN** an amendment consumes it
- **THEN** the amendment records its hash, role, origin and selection rationale
- **AND** the committed original remains byte-identical

#### Scenario: Hash mismatch before recomputation
- **GIVEN** a selected input no longer matches its recorded SHA-256
- **WHEN** the summariser reads the evidence manifest
- **THEN** it refuses the verdict before calculation
- **AND** it does not update the expected digest automatically

### Requirement: Amended results remain separate and accurately labelled

Experiment 26 and 27 amended assessments SHALL use new separate output
directories. They SHALL preserve original reports, summaries, discussions,
raw checkpoints, manifests and plans. Each amendment SHALL record original
measurement dates where known, recomputation time, repair code identity and
input provenance. Invalid or incomplete evidence SHALL produce a diagnostic
assessment with a null performance verdict and a non-zero command exit.

#### Scenario: Output destination aliases historical evidence
- **GIVEN** an amendment destination is inside or resolves into a protected historical path
- **WHEN** the summariser starts
- **THEN** it refuses before any write

#### Scenario: Output directory already contains an amendment
- **GIVEN** the chosen amendment directory already exists
- **WHEN** another invocation targets it
- **THEN** the command refuses to replace the previous amendment

#### Scenario: Recomputed Experiment 27 comparison
- **GIVEN** existing Experiment 22, 26 and 27 inputs are recomputed offline
- **WHEN** the amended report is generated
- **THEN** it labels earlier reference cells and historical measured cells separately
- **AND** it does not describe recomputation as a new experiment run
- **AND** interaction remains descriptive across dates and indexes
- **AND** it makes no claim that OCR was exercised

#### Scenario: Claims exceed the retained evidence
- **GIVEN** the old report claims endpoint determinism, verified execution or exact billed calls without supporting records
- **WHEN** the amendment is written
- **THEN** it distinguishes observed metrics from those unsupported claims
- **AND** it preserves the old report and recorded historical verdict

### Requirement: Every implemented repair has local fail-before and pass-after evidence

Each bug fix in this change SHALL have a regression that demonstrates the
specific wrong behaviour before repair and passes after repair. The local
agent SHALL own execution, historical hash checks, recovery verification,
linting, tests and runtime validation. Synthetic tests SHALL NOT invoke paid
services or personal-document discovery.

#### Scenario: A test fails only because a new API is absent
- **GIVEN** a proposed fail-before test fails at import or argument parsing only
- **WHEN** the local agent assesses its proof
- **THEN** that failure does not establish the behavioural defect
- **AND** the agent adds a baseline-compatible reproducer of the wrong behaviour

#### Scenario: Repaired synthetic test passes
- **GIVEN** the same behavioural assertion fails before and passes after the fix
- **WHEN** the local agent records verification
- **THEN** it records commands, code identities, outcomes and evidence paths
- **AND** it does not claim that a historical experiment was rerun
