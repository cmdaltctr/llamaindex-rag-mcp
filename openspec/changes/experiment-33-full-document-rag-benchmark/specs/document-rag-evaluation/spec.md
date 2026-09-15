# document-rag-evaluation Specification

## ADDED Requirements

### Requirement: Full document evaluation exercises the current pipeline

The primary benchmark SHALL exercise the current OMRG `documents` profile from raw source ingestion through retrieval and reranking, with grounded answering when the approved protocol includes answer scoring.

#### Scenario: A benchmark bypasses raw PDF ingestion
- **WHEN** a candidate run starts from pre-extracted benchmark text instead of the approved source PDF
- **THEN** it SHALL NOT count as the primary full-pipeline result
- **AND** it MAY be reported only as a separate diagnostic run

### Requirement: Stage-level evidence is retained

The benchmark SHALL record enough stage-level evidence to distinguish parsing, chunking, retrieval, reranking, and answer-stage failures.

#### Scenario: Gold evidence is absent after parsing
- **WHEN** source-grounded evidence is not present in the extracted representation
- **THEN** the failure SHALL be attributed to evidence recovery before retrieval scoring is interpreted
- **AND** the report SHALL NOT describe the miss as a pure embedding or ranking failure

### Requirement: Benchmark identity is frozen before measured execution

The final protocol SHALL freeze corpus membership, file hashes, queries, qrels or gold answers, scoring code, effective settings, model identities, and repository/dependency provenance before measured execution.

#### Scenario: A benchmark document changes after freeze
- **WHEN** a source hash differs from the frozen manifest
- **THEN** the measured run SHALL abort or create a distinct benchmark revision

### Requirement: Measured test data is not used for tuning

Production settings SHALL NOT be tuned using measured test outcomes from the same benchmark revision.

#### Scenario: A retrieval setting is changed after inspecting test scores
- **WHEN** a setting is changed because of measured test-set results
- **THEN** the resulting run SHALL be labelled exploratory
- **AND** a new held-out revision SHALL be required for confirmatory evidence

### Requirement: External framework comparison is out of scope

Experiment 33 SHALL establish a current OMRG baseline without claiming superiority over LlamaIndex, Haystack, LangChain, or historical OMRG.

#### Scenario: Future comparison uses the Experiment 33 corpus
- **WHEN** another framework is evaluated later
- **THEN** that comparison SHALL be governed by a separate proposal
- **AND** Experiment 33 SHALL remain the OMRG baseline record

### Requirement: Draft status blocks measured execution

The measured benchmark SHALL NOT run while the proposal is marked draft and its open protocol questions remain unresolved.

#### Scenario: Corpus and scoring choices are still open
- **WHEN** the benchmark corpus, model identity, or scoring rules are not frozen
- **THEN** only exploratory harness work MAY proceed
- **AND** no result SHALL be reported as the Experiment 33 baseline
