## Purpose

Define Markdown-specific chunking behaviour and evidence-level evaluation
requirements so structured Markdown documents preserve heading boundaries
without producing uncapped oversized chunks.

## Requirements

### Requirement: Markdown files use heading-aware chunking with a size cap

The system SHALL chunk Markdown text using a heading-aware node parser chained
with a sentence splitter capped at `CHUNKING__MARKDOWN_CHUNK_SIZE`. Text
counts as Markdown when the source file has extension `.md`, **or** when the
reader that produced it declares its emitted text format as `markdown`.
Heading boundaries SHALL be respected wherever the heading-bounded section is
at most `CHUNKING__MARKDOWN_CHUNK_SIZE` characters; sections longer than
`CHUNKING__MARKDOWN_CHUNK_SIZE` SHALL be further split by the sentence splitter
so that no produced chunk exceeds `CHUNKING__MARKDOWN_CHUNK_SIZE` within the
splitter's tokenisation tolerance. Text from readers declaring `plain` SHALL
retain the existing splitter behaviour and global `CHUNKING__CHUNK_SIZE`
default.

#### Scenario: Markdown headings remain intact when sections fit

- **GIVEN** a Markdown document with multiple `##` sections, each shorter than `CHUNKING__MARKDOWN_CHUNK_SIZE`
- **WHEN** the document is ingested
- **THEN** chunk boundaries SHALL align with heading boundaries
- **THEN** no chunk SHALL contain a partial heading line followed by unrelated section text

#### Scenario: Long heading-bounded section is further split

- **GIVEN** a Markdown document whose single `##` section text exceeds `CHUNKING__MARKDOWN_CHUNK_SIZE`
- **WHEN** the document is ingested
- **THEN** that section SHALL be split into more than one chunk
- **THEN** every produced chunk SHALL have length at most `CHUNKING__MARKDOWN_CHUNK_SIZE` within the splitter's tokenisation tolerance

#### Scenario: Non-Markdown files are unchanged

- **GIVEN** a `.txt` file, or a `.pdf` read by a reader declaring `plain`
- **WHEN** the file is ingested
- **THEN** chunking SHALL use the existing default splitter
- **THEN** the chunk count and content SHALL match the previous default behaviour for the same file
- **THEN** no `header_path` SHALL be fabricated

#### Scenario: Markdown-format reader output uses the heading-aware path

- **GIVEN** a `.pdf` read by a reader declaring its emitted text format as `markdown`
- **WHEN** the file is ingested
- **THEN** the heading-aware node parser SHALL run before sentence splitting
- **THEN** the emitted chunks SHALL carry `header_path`
- **THEN** the `CHUNKING__MARKDOWN_CHUNK_SIZE` budget SHALL apply

#### Scenario: Markdown without headings still chunks

- **GIVEN** a `.md` file with no headings
- **WHEN** the file is ingested
- **THEN** chunking SHALL still produce non-empty chunks
- **THEN** ingestion SHALL succeed without raising

#### Scenario: Reader-produced Markdown honours the recovery knobs

- **GIVEN** reader-produced Markdown text
- **WHEN** the file is ingested
- **THEN** `ensure_heading_metadata`, `apply_heading_prepend` and
  `drop_small_markdown_chunks` SHALL apply with the same configured behaviour
  they have for `.md` files

### Requirement: Markdown files support configurable Markdown-only recovery knobs

The Markdown branch SHALL support a Markdown-only chunk-size override,
optional heading-path prepend, optional small-chunk filtering, and defensive
heading metadata propagation. Heading prepend and small-chunk filtering SHALL
remain opt-in. Defensive heading metadata propagation SHALL be idempotent.

#### Scenario: Markdown branch can use a different chunk size from non-Markdown files

- **GIVEN** `CHUNKING__CHUNK_SIZE=512` and `CHUNKING__MARKDOWN_CHUNK_SIZE=1024`
- **WHEN** a `.md` file is ingested
- **THEN** the Markdown branch SHALL use `CHUNKING__MARKDOWN_CHUNK_SIZE` for the second-stage `SentenceSplitter`
- **AND** non-Markdown files SHALL continue using `CHUNKING__CHUNK_SIZE`

#### Scenario: Heading metadata is defensively preserved

- **GIVEN** a Markdown section that is split into more than one child chunk
- **WHEN** ingestion emits the child nodes
- **THEN** the system SHALL defensively copy heading metadata from the source node when available
- **AND** the operation SHALL be idempotent when the child node already carries the heading metadata

#### Scenario: Heading text can be prepended before embedding

- **GIVEN** `CHUNKING__MARKDOWN_HEADING_PREPEND=true`
- **WHEN** a Markdown chunk has a non-empty heading path
- **THEN** the system SHALL prepend the heading path to the chunk text before embedding
- **AND** the system SHALL avoid double-prepending the same prefix on repeated processing

#### Scenario: Small Markdown chunks can be filtered

- **GIVEN** `CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION > 0.0`
- **WHEN** Markdown chunks are emitted after splitting
- **THEN** chunks smaller than `CHUNKING__MARKDOWN_CHUNK_SIZE * 4 * CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION` characters SHALL be filtered before embedding
- **AND** the system SHALL log how many chunks were filtered

### Requirement: Markdown chunking evaluations use evidence-level labels

The system SHALL validate Markdown-aware chunking with an evidence-dense
retrieval evaluation rather than source-file matching alone. The canonical
Experiment 6b corpus SHALL be Qasper-dev, normalised through the local Qasper
adapter. HiChunk / HiCBench schema support MAY remain as historical
compatibility, but SHALL NOT be required for the canonical evaluation.

#### Scenario: Qasper adapter normalises evidence labels

- **GIVEN** the Qasper dev split
- **WHEN** Experiment 6b prepares the corpus with `--source qasper`
- **THEN** it SHALL produce Markdown documents suitable for both chunkers
- **THEN** it SHALL produce QA records with query text, expected document, evidence snippets, and hierarchy / section labels when available

#### Scenario: Evidence-sparse datasets are rejected

- **GIVEN** an Experiment 6b query set with document-level labels only
- **WHEN** the evaluator validates the query set
- **THEN** it SHALL fail before running retrieval
- **THEN** the failure SHALL explain that source-file Hit@K alone cannot evaluate chunking quality

#### Scenario: Retrieval is judged at evidence level

- **GIVEN** baseline and candidate indexes built from the same Experiment 6b corpus
- **WHEN** the evaluator runs the same QA set against both indexes with reranking disabled
- **THEN** it SHALL compute Evidence Recall@1/@3/@5, Evidence MRR, section / hierarchy Match@1, and nDCG@5
- **THEN** a result SHALL NOT be counted correct solely because its source filename matches the expected document

### Requirement: Retrieval results expose chunk metadata to evaluators

The system SHALL include the full chunk metadata dict in every result row
returned by `retrieval.search()` so evaluators can inspect heading or
hierarchy labels without parsing chunk text. The metadata field SHALL preserve
the keys ChromaDB returns (e.g. `heading_path`, `header`, `file_path`) and
SHALL be present even when reranking is enabled.

#### Scenario: Search results carry metadata

- **GIVEN** an indexed Markdown chunk whose metadata records a heading path
- **WHEN** `retrieval.search()` returns a result row referencing that chunk
- **THEN** the result row SHALL include a `metadata` key whose value is a dict
- **THEN** the dict SHALL preserve the heading metadata produced at ingest time

#### Scenario: Section metrics use metadata, not text fallback

- **GIVEN** Experiment 6b candidate retrieval results with non-null `metadata`
- **WHEN** the evaluator computes Section / hierarchy Match@1
- **THEN** the metric SHALL prefer structured metadata over regex-parsed headings
- **THEN** the regex fallback SHALL only be used when metadata does not include any heading-related key

### Requirement: Experiment 6c validates Markdown chunking recovery on Qasper

The system SHALL keep Experiment 6c self-contained and SHALL evaluate the
small-bore recovery knobs against the same Qasper corpus and ground truth used
in Experiment 6b.

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
