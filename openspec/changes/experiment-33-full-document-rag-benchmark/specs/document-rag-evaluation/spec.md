# document-rag-evaluation Specification

## ADDED Requirements

### Requirement: Document baseline uses a frozen FinanceBench subset

Experiment 33A SHALL evaluate the current OMRG `documents` profile on a small frozen FinanceBench subset using the source PDFs.

#### Scenario: A run starts from pre-extracted benchmark text
- **WHEN** the run bypasses the approved source PDF
- **THEN** it SHALL NOT count as the primary 33A result
- **AND** it MAY be reported only as a diagnostic run

### Requirement: Document evaluation exercises the current production path

The 33A run SHALL use the current document ingestion, reader/OCR routing, chunking, embedding, vector store, retrieval, reranking, and answer path defined by the frozen profile.

#### Scenario: A benchmark-only setting changes the production path
- **WHEN** a setting is changed only to improve measured benchmark scores
- **THEN** the run SHALL be labelled exploratory
- **AND** it SHALL NOT replace the frozen baseline

### Requirement: Document failures are attributable by stage

The harness SHALL distinguish source evidence recovery, chunk preservation, retrieval/reranking, and answer-stage failures.

#### Scenario: Gold evidence is absent after parsing
- **WHEN** source-grounded evidence is not present in the extracted representation
- **THEN** the failure SHALL be attributed before retrieval
- **AND** the report SHALL NOT describe it as a pure ranking failure

### Requirement: Document retrieval metrics remain primary

The primary 33A result SHALL report Evidence Recall@1/@3/@5/@10, MRR@10, no-hit rate, and nDCG@10 where the qrels support it.

#### Scenario: RAGAS answer scores improve while retrieval degrades
- **WHEN** secondary answer metrics improve but primary retrieval metrics worsen
- **THEN** the report SHALL present both outcomes
- **AND** it SHALL NOT hide the retrieval regression behind the secondary score

### Requirement: FinanceBench subset identity is frozen

The measured subset SHALL freeze question IDs, source PDF identities, file hashes, query order, and scoring inputs before execution.

#### Scenario: The subset changes after scoring starts
- **WHEN** a question or source PDF is added, removed, or replaced
- **THEN** the run SHALL use a new benchmark revision