## Purpose

Define the modular subpackage structure for the core RAG pipeline: metadata extraction, ingestion, chunking, and retrieval. Phase 1 of the five-phase modular refactor — mechanical extraction with backward-compatible shims, no behaviour change.

## Requirements

### Requirement: Metadata subpackage extraction

The system SHALL provide all metadata-extraction behaviour formerly in
`metadata_extractor.py` from a `core/metadata/` subpackage containing one
module per extraction backend (`keyword.py`, `ollama.py`, `llamaindex.py`,
`llamacpp.py`), an orchestrator module (`extractor.py`) that dispatches to the
configured backend, and a `taxonomy.py` module holding the hybrid category
logic (ADR-013).

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

---

### Requirement: Ingestion and chunking subpackage extraction

The system SHALL provide ingestion orchestration from a `core/ingestion/`
subpackage (`loader.py`, `chunker.py`, `writer.py`) exposing
`ingest_path_async()` as its public entry point, and SHALL provide the four
existing chunking strategies from a `core/chunking/` strategy folder
(`code.py`, `markdown.py`, `sentence.py`, `config_file.py`).

#### Scenario: Content-type dispatch preserved

- **WHEN** a file with a known content type (e.g. `.py`, `.md`, `.yaml`) is
  ingested
- **THEN** the chunker MUST route it to the same strategy as before the
  refactor (content-type precedence is unchanged)

#### Scenario: Only existing strategies extracted

- **WHEN** the `core/chunking/` folder is inspected after Phase 1
- **THEN** it MUST contain exactly the four pre-existing strategies
- **AND** MUST NOT contain `structural.py` or `evidence_md.py` (net-new
  strategies deferred to a later change)

#### Scenario: Async ingestion entry point preserved

- **WHEN** a caller invokes ingestion
- **THEN** `ingest_path_async` MUST remain the sole ingestion entry point
  with an unchanged signature (AGENTS.md invariant #4)

---

### Requirement: Retrieval subpackage grouping

The system SHALL group dense retrieval, sparse retrieval, fusion, reranking,
the `search()` orchestrator, and the rerank threshold policy under a
`core/retrieval/` subpackage, including a `pipeline.py` module owning the
end-to-end `search()` orchestration and a `policy.py` module owning the
`HARD_TECHNICAL_THRESHOLD` ÷30 rerank threshold policy.

#### Scenario: End-to-end search dispatch

- **WHEN** `search()` is called through the new subpackage
- **THEN** `pipeline.py` MUST orchestrate dense + sparse + RRF + rerank policy
  exactly as the pre-refactor `retrieval.py` did

#### Scenario: Threshold policy relocated intact

- **WHEN** the rerank threshold policy is inspected in `core/retrieval/policy.py`
- **THEN** the `HARD_TECHNICAL_THRESHOLD = 0.3` ÷30 scaling logic MUST be
  numerically identical to the pre-refactor implementation (AGENTS.md gotcha
  #3 — recalibration requires re-running experiment 1)

#### Scenario: Reranker singleton preserved

- **WHEN** tests reset `CrossEncoderReranker._instance = None`
- **THEN** the reset MUST affect the same class object used by the pipeline
  (the class moves unchanged; DI conversion is out of scope for Phase 1)

---

### Requirement: Backward-compatible import shims

The system SHALL keep every pre-refactor public import path resolving via a
compat shim that re-exports from the new location and emits a
`DeprecationWarning` naming the new import path. Shims are scheduled for
removal in v2.0.0.

#### Scenario: Old import paths resolve

- **WHEN** code executes `from rag_mcp.metadata_extractor import ...`,
  `from rag_mcp.ingestion import ...`, `from rag_mcp.retrieval import ...`,
  `from rag_mcp.sparse_retriever import ...`, or `from rag_mcp.reranker import ...`
- **THEN** the import MUST succeed and resolve to the same objects as the new
  `rag_mcp.core.*` paths
- **AND** a `DeprecationWarning` MUST be emitted naming the new import path

#### Scenario: No constant/config surface changes

- **WHEN** any module reads configuration
- **THEN** it MUST read it from `rag_mcp.config` exactly as before (the
  config surface is unchanged in Phase 1; the PEP 562 shim is Phase 2 scope)

---

### Requirement: Behaviour preservation and test continuity

The refactor SHALL NOT change any observable behaviour: public function
signatures, CLI commands, MCP tool signatures, return shapes, and error
contracts are identical before and after the extraction.

#### Scenario: Full test suite passes

- **WHEN** `uv run pytest -m "not slow" --cov=rag_mcp` is run at the phase
  boundary
- **THEN** all tests MUST pass with no assertion modifications (only test
  import paths may change)
- **AND** overall coverage MUST NOT regress below the recorded baseline of
  88% (`notes/baseline.md`), excluding deprecated compat shim files which
  carry no test consumers by design

#### Scenario: File size ceiling

- **WHEN** the new `core/` tree is inspected
- **THEN** no file MUST exceed 500 lines

#### Scenario: MCP and CLI surfaces unchanged

- **WHEN** the MCP server and CLI are exercised after the extraction
- **THEN** every tool signature and subcommand MUST behave identically to the
  pre-refactor versions
