## MODIFIED Requirements

### Requirement: Markdown files use heading-aware chunking with configurable Markdown-only recovery knobs
The system SHALL chunk files with extension `.md` using the heading-aware Markdown pipeline. The Markdown branch SHALL support a Markdown-only chunk-size override, optional heading-path prepend, optional small-chunk filtering, and defensive heading metadata propagation. All recovery knobs SHALL default to current behaviour unless explicitly enabled.

#### Scenario: Markdown branch can use a different chunk size from non-Markdown files
- **GIVEN** `CHUNK_SIZE=512` and `MARKDOWN_CHUNK_SIZE=1024`
- **WHEN** a `.md` file is ingested
- **THEN** the Markdown branch SHALL use `MARKDOWN_CHUNK_SIZE` for the second-stage `SentenceSplitter`
- **AND** non-Markdown files SHALL continue using `CHUNK_SIZE`

#### Scenario: Heading metadata is defensively preserved
- **GIVEN** a Markdown section that is split into more than one child chunk
- **WHEN** ingestion emits the child nodes
- **THEN** the system SHALL defensively copy heading metadata from the source node when available
- **AND** the operation SHALL be idempotent when the child node already carries the heading metadata

#### Scenario: Heading text can be prepended before embedding
- **GIVEN** `MARKDOWN_HEADING_PREPEND=true`
- **WHEN** a Markdown chunk has a non-empty heading path
- **THEN** the system SHALL prepend the heading path to the chunk text before embedding
- **AND** the system SHALL avoid double-prepending the same prefix on repeated processing

#### Scenario: Small Markdown chunks can be filtered
- **GIVEN** `MARKDOWN_MIN_CHUNK_FRACTION > 0.0`
- **WHEN** Markdown chunks are emitted after splitting
- **THEN** chunks smaller than `MARKDOWN_CHUNK_SIZE * 4 * MARKDOWN_MIN_CHUNK_FRACTION` characters SHALL be filtered before embedding
- **AND** the system SHALL log how many chunks were filtered

### Requirement: Experiment 6c validates Markdown chunking recovery on Qasper
The system SHALL keep Experiment 6c self-contained and SHALL evaluate the small-bore recovery knobs against the same Qasper corpus and ground truth used in Experiment 6b.

#### Scenario: Experiment 6c is self-contained
- **GIVEN** the completed Experiment 6c directory
- **WHEN** a reviewer inspects its artefacts
- **THEN** the directory SHALL contain its own `corpus/`, `ground-truth.json`, rebuilt `chroma_baseline/`, and candidate ChromaDBs under `chroma_candidate_runs/`
- **AND** the ChromaDB result metadata SHALL point at `experiments/6c-markdown-chunking-quickwins-2026-05-28/corpus/`, not at an older 6b path

#### Scenario: Phase 1 top-k sweep is recorded
- **GIVEN** the rebuilt 512-token Markdown candidate under `chroma_candidate_runs/baseline_6b/`
- **WHEN** Experiment 6c runs Phase 1
- **THEN** it SHALL produce Pass A and Pass B result JSONs for `top_k` values 5, 10, and 20

#### Scenario: Phase 2 chunk-size sweep is recorded
- **GIVEN** rebuilt candidates at Markdown chunk sizes 768 and 1024
- **WHEN** Experiment 6c runs Phase 2
- **THEN** it SHALL produce Pass A and Pass B result JSONs for `top_k` values 5 and 10 for each chunk size

#### Scenario: Results document explains the decision in plain English
- **GIVEN** completed Phase 1 and Phase 2 result JSONs
- **WHEN** `results.md` is written
- **THEN** it SHALL identify the best production-shape cell
- **AND** it SHALL explain whether the lift is chunker-driven, reranker-driven, or both
- **AND** it SHALL state whether any production default should move in a follow-up change
