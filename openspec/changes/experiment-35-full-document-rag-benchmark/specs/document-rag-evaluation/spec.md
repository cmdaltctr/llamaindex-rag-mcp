# document-rag-evaluation Specification

## ADDED Requirements

### Requirement: Document baseline uses a frozen FinanceBench subset

Experiment 35A SHALL evaluate the current OMRS `documents` profile on a small frozen FinanceBench subset using the source PDFs.

#### Scenario: A run starts from pre-extracted benchmark text
- **WHEN** the run bypasses the approved source PDF
- **THEN** it SHALL NOT count as the primary 35A result
- **AND** it MAY be reported only as a diagnostic run

### Requirement: Document evaluation exercises the current production path

The 35A run SHALL use the current document ingestion, reader/OCR routing, chunking, embedding, vector store, retrieval, reranking, and answer path defined by the frozen profile.

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

The primary 35A result SHALL report Evidence Recall@1/@3/@5/@10, MRR@10, no-hit rate, and nDCG@10 where the qrels support it. A hit SHALL be a retrieved chunk from the gold document and the gold page, with the zero-indexed FinanceBench page number converted by one frozen, tested function.

#### Scenario: A chunk comes from the gold page
- **WHEN** a retrieved chunk comes from the gold document and its page equals the gold `evidence_page_num` after conversion from zero-indexed numbering
- **THEN** the chunk SHALL count as a hit

#### Scenario: The page index is not converted
- **WHEN** the harness compares zero-indexed `evidence_page_num` values with stored page numbers without the frozen conversion
- **THEN** the page-index unit test SHALL fail before any measured run

#### Scenario: RAGAS answer scores improve while retrieval degrades
- **WHEN** secondary answer metrics improve but primary retrieval metrics worsen
- **THEN** the report SHALL present both outcomes
- **AND** it SHALL NOT hide the retrieval regression behind the secondary score

### Requirement: FinanceBench subset identity is frozen

The measured subset SHALL freeze question IDs, source PDF identities, file hashes, query order, and scoring inputs before execution.

#### Scenario: The subset changes after scoring starts
- **WHEN** a question or source PDF is added, removed, or replaced
- **THEN** the run SHALL use a new benchmark revision