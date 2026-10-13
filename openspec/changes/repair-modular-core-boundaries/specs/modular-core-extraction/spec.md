# Modular core repair delta

## MODIFIED Requirements

### Requirement: Metadata subpackage extraction

Metadata extraction SHALL remain in `core/metadata/`, with registered
keyword, Ollama, LlamaIndex, llama.cpp, and OpenRouter implementations and
shared prompt/taxonomy helpers. Dispatch SHALL use
`core/metadata/registry.py` without name-specific branching or module-level
imports of concrete backends. Existing positional text, filename, and
settings arguments SHALL remain valid; built-in strategies SHALL also accept
the documented optional keyword-only store context. Supplied context SHALL
reach shared classification and fallback paths.

#### Scenario: Backend split is faithful
- **WHEN** the metadata subpackage is inspected
- **THEN** each supported implementation SHALL remain in its owning backend module
- **AND** OpenRouter SHALL retain its existing registered implementation

#### Scenario: Behaviour preservation
- **WHEN** an existing metadata mode runs with the same intended settings/store
- **THEN** output shape, retry policy, parsing, and degradation behaviour SHALL remain unchanged
- **AND** accidental cross-store category lookup SHALL be corrected

#### Scenario: Backend resolved through the registry
- **WHEN** the extractor selects a backend
- **THEN** it SHALL use the metadata registry
- **AND** dispatch SHALL contain no name-specific branch or top-level concrete-backend import

#### Scenario: Disabled sentinel honoured
- **WHEN** metadata extraction is disabled
- **THEN** it SHALL return without category lookup or backend resolution

#### Scenario: Extraction results unchanged
- **WHEN** the selected backend succeeds with the same supplied category context
- **THEN** returned category/keyword/summary fields SHALL retain their existing semantics

#### Scenario: Fallback preserves the owning store
- **WHEN** LlamaIndex or local extraction falls back to another configured backend
- **THEN** the supplied store and resolved settings SHALL reach that fallback
- **AND** no default store SHALL replace them

### Requirement: Ingestion and chunking subpackage extraction

Ingestion SHALL remain under `core/ingestion/`, exposing async
`ingest_path_async()` with injected settings. Existing chunking modules and
registered strategies SHALL be reused. Both structured and unstructured
document branches SHALL invoke the selected registered document strategy,
rather than private implementation helpers. Reading, metadata attachment,
reader declarations, and degradation reporting SHALL retain their existing
owners and semantics.

#### Scenario: Content-type dispatch preserved
- **WHEN** a source has a recognised code, configuration, or document type
- **THEN** existing content-type precedence and specialised routing SHALL remain unchanged

#### Scenario: Strategy resolved through the registry
- **WHEN** either document branch selects sentence splitting
- **THEN** it SHALL resolve and await the sentence registry callable
- **AND** the chunker SHALL not call sentence splitting/post-processing helpers directly

#### Scenario: Only existing strategies extracted
- **WHEN** this repair is applied
- **THEN** it SHALL add no new chunking algorithm
- **AND** existing code, Markdown, sentence, and configuration behaviour SHALL remain available

#### Scenario: Async ingestion entry point preserved
- **WHEN** an existing caller invokes ingestion
- **THEN** the async entry point and its effective-settings argument SHALL remain available

#### Scenario: Registered replacement reaches production dispatch
- **WHEN** the sentence registry resolves a sentinel replacement
- **THEN** structured and unstructured production document dispatch SHALL invoke it
- **AND** the test SHALL fail if either branch returns to a private splitter

#### Scenario: Reader-produced Markdown remains intact
- **WHEN** a non-Markdown source is read as declared Markdown
- **THEN** the selected strategy SHALL receive that declaration
- **AND** headings, model-token settings, and post-processing SHALL be applied exactly once

#### Scenario: Metadata degradation survives dispatch
- **WHEN** unstructured metadata extraction reports degradation
- **THEN** returned chunk results SHALL retain that marker through the registered strategy call
