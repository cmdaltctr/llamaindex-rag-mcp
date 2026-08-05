## Purpose

Define the modular subpackage structure for the core RAG pipeline: metadata extraction, ingestion, chunking, and retrieval. Phase 1 of the five-phase modular refactor — mechanical extraction with backward-compatible shims, no behaviour change.
## Requirements
### Requirement: Metadata subpackage extraction

The system SHALL provide all metadata-extraction behaviour formerly in
`metadata_extractor.py` from a `core/metadata/` subpackage containing one
module per extraction backend (`keyword.py`, `ollama.py`, `llamaindex.py`,
`llamacpp.py`), an orchestrator module (`extractor.py`) that dispatches to the
configured backend, and a `taxonomy.py` module holding the hybrid category
logic (ADR-013). `extractor.py` SHALL select a backend by resolving it through
`core/metadata/registry.py` and SHALL NOT dispatch by an if/elif chain over
backend names, nor import concrete backend modules at the top level.

#### Scenario: Backend split is faithful

- **WHEN** the extraction is complete
- **THEN** each of the four extraction backends MUST live in its own module
  under `core/metadata/`
- **AND** OpenRouter MUST NOT exist as a standalone backend module (it routes
  through the llamaindex/local mode via the provider registry)

#### Scenario: Behaviour preservation

- **WHEN** any supported metadata mode (`keyword`, `ollama`, `llamaindex`,
  `llamacpp`, `disabled`) is exercised through the new subpackage
- **THEN** the extracted metadata output MUST be identical to the pre-refactor
  output for the same input and configuration

#### Scenario: Backend resolved through the registry

- **WHEN** the extractor dispatches to a backend
- **THEN** it MUST call `registry.get(<backend name>)`
- **AND** `core/metadata/extractor.py` MUST contain no if/elif chain over
  backend names and no module-level import of a concrete backend module

#### Scenario: Disabled sentinel honoured

- **WHEN** metadata extraction is configured as disabled
- **THEN** the extractor MUST short-circuit without resolving a backend

#### Scenario: Extraction results unchanged

- **WHEN** each backend runs against the same input as before the change
- **THEN** the extracted metadata MUST be identical

---

### Requirement: Ingestion and chunking subpackage extraction

The system SHALL provide ingestion orchestration from a `core/ingestion/`
subpackage (`loader.py`, `chunker.py`, `writer.py`) exposing
`ingest_path_async()` as its public entry point, and SHALL provide the four
existing chunking strategies from a `core/chunking/` strategy folder
(`code.py`, `markdown.py`, `sentence.py`, `config_file.py`). The chunker
SHALL select a strategy by resolving it through `core/chunking/registry.py`,
and SHALL NOT import concrete strategy modules at the top level.

#### Scenario: Content-type dispatch preserved

- **WHEN** a file with a known content type (e.g. `.py`, `.md`, `.yaml`) is
  ingested
- **THEN** the chunker MUST route it to the same strategy as before the
  refactor (content-type precedence is unchanged)

#### Scenario: Strategy resolved through the registry

- **WHEN** the chunker resolves the strategy for a file
- **THEN** it MUST call `registry.get(<strategy name>)`
- **AND** `core/ingestion/chunker.py` MUST have no module-level import of
  `core.chunking.code`, `core.chunking.markdown`, `core.chunking.sentence`, or
  `core.chunking.config_file`

#### Scenario: Only existing strategies extracted

- **WHEN** the `core/chunking/` folder is inspected
- **THEN** it MUST contain exactly the four pre-existing strategies
- **AND** MUST NOT contain `structural.py` or `evidence_md.py` (net-new
  strategies deferred to a later change)

#### Scenario: Async ingestion entry point preserved

- **WHEN** a caller invokes ingestion
- **THEN** `ingest_path_async` MUST remain the sole ingestion entry point
  (AGENTS.md invariant #4), accepting an `EffectiveSettings` parameter

---

### Requirement: Retrieval subpackage grouping

The system SHALL group dense retrieval, sparse retrieval, fusion, reranking,
the `search()` orchestrator, and the rerank threshold policy under a
`core/retrieval/` subpackage, including a `pipeline.py` module owning the
end-to-end `search()` orchestration and a `policy.py` module owning the
`HARD_TECHNICAL_THRESHOLD` ÷30 rerank threshold policy. `pipeline.py` SHALL
resolve retrieval stages through `core/retrieval/registry.py` and SHALL NOT
import concrete stage modules at the top level.

#### Scenario: End-to-end search dispatch

- **WHEN** `search()` is called through the new subpackage
- **THEN** `pipeline.py` MUST orchestrate dense + sparse + RRF + rerank policy
  exactly as the pre-refactor `retrieval.py` did

#### Scenario: Stages resolved through the registry

- **WHEN** `pipeline.py` needs the dense, fusion, policy, or reranker stage
- **THEN** it MUST resolve it through `registry.get(...)`
- **AND** `pipeline.py` MUST have no module-level import of those stage modules

#### Scenario: Threshold policy relocated intact

- **WHEN** the rerank threshold policy is inspected in `core/retrieval/policy.py`
- **THEN** the `HARD_TECHNICAL_THRESHOLD = 0.3` ÷30 scaling logic MUST be
  numerically identical to the pre-refactor implementation (AGENTS.md gotcha
  #3 — recalibration requires re-running experiment 1)

#### Scenario: Reranker model cache reset preserved

- **WHEN** tests need a clean reranker state
- **THEN** `reset_model_cache()` MUST clear the process-wide model cache
  (AGENTS.md gotcha #2)

---

### Requirement: Behaviour preservation and test continuity

The refactor SHALL NOT change any observable runtime behaviour of retrieval,
ingestion, or metadata extraction: public operation semantics, CLI commands,
MCP tool signatures, return shapes, and error contracts are identical before
and after. Changes to Python import paths, the configuration surface, and
removed compatibility modules are governed by the breaking-change
requirements of this change and are excluded from this preservation
guarantee.

#### Scenario: Full test suite passes

- **WHEN** `uv run pytest -m "not slow" --cov=rag_mcp` is run at the change
  boundary
- **THEN** all tests MUST pass
- **AND** coverage MUST meet the recorded floors: Core + MCP ≥95%,
  Orchestration ≥85%, Overall ≥90%

#### Scenario: File size ceiling across the package

- **WHEN** `src/rag_mcp/` is inspected
- **THEN** no Python file MUST exceed 500 lines, including modules outside
  `core/`

#### Scenario: MCP and CLI surfaces unchanged

- **WHEN** the MCP server and CLI are exercised after the change
- **THEN** every tool signature and subcommand MUST behave identically to the
  pre-change versions

