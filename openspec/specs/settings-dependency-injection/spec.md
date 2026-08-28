# settings-dependency-injection Specification

## Purpose
TBD - created by archiving change complete-architecture-v2-conformance. Update Purpose after archive.
## Requirements
### Requirement: Immutable effective settings value object

The system SHALL provide a single frozen `EffectiveSettings` value object that
carries every configuration value the `core/` and `integrations/` layers need:
the chunking, retrieval, and metadata blocks plus the cross-cutting fields
(storage identifiers, embedding model, PDF reader, document backend, magika
binary, thresholds). It SHALL live in a pure-data module with no imports from
`config`, `compose`, or any other `core/` module.

#### Scenario: Object is frozen

- **WHEN** any code attempts to mutate an `EffectiveSettings` attribute
- **THEN** the attempt MUST raise rather than silently change process-wide state

#### Scenario: Value object is pure data

- **WHEN** the import-linter check runs against the module defining
  `EffectiveSettings`
- **THEN** it MUST have no import from `rag_mcp.config`, `rag_mcp.compose`, or
  a sibling `core/` business module

#### Scenario: Covers every core-consumed knob

- **WHEN** a `core/` module needs a configuration value
- **THEN** that value MUST be reachable from the `EffectiveSettings` instance it
  was given, with no fallback lookup

---

### Requirement: Core operations receive settings as a parameter

`search()` and `ingest_path_async()` SHALL accept an `EffectiveSettings`
parameter and SHALL pass it down to every module they call. Modules under
`core/` and `integrations/` SHALL NOT import a process-wide settings object.
The producer of the instance SHALL be `ProfileResolver.resolve(collection)` for
collection-bound operations and `compose.py` for operations with no collection.

#### Scenario: No global settings read in core

- **WHEN** `src/rag_mcp/core/` and `src/rag_mcp/integrations/` are searched for
  `from ...config import settings` (or any equivalent import of the resolved
  settings singleton)
- **THEN** the search MUST return zero results

#### Scenario: Settings flow from the entry point

- **WHEN** `search()` is invoked with an `EffectiveSettings` whose
  `retrieval.top_k` is 20
- **THEN** the dense retriever, fusion, policy, and reranker stages MUST all
  observe 20 without consulting any other source

#### Scenario: Two operations with different settings in one process

- **WHEN** two `search()` calls run in the same process with
  `EffectiveSettings` instances differing in `rerank_enabled`
- **THEN** each call MUST honour its own instance
- **AND** neither call MUST be affected by the other

#### Scenario: Tests inject rather than patch

- **WHEN** a test needs a non-default configuration value
- **THEN** it MUST construct an `EffectiveSettings` and pass it into the
  operation
- **AND** it MUST NOT patch attributes on a module-level settings singleton

---

### Requirement: No settings singleton outside the composition root

The resolved `Settings` singleton SHALL NOT be instantiated at module import
time. `config` SHALL expose `get_settings()` and SHALL NOT expose a
module-level `settings` object. `compose.py` SHALL be the only caller of
`get_settings()`.

#### Scenario: Import does not resolve settings

- **WHEN** `rag_mcp.config` is imported
- **THEN** no `Settings()` instance MUST be constructed as a side effect
- **AND** no environment or YAML resolution MUST occur until `get_settings()`
  is called

#### Scenario: Single call site

- **WHEN** the codebase is searched for `get_settings()`
- **THEN** the only production call site MUST be in `compose.py`

---

### Requirement: No import-time settings snapshots

No module SHALL capture a configuration value into a module-level constant or
into the construction of a module-level object at import time. Values SHALL be
read from the injected `EffectiveSettings` at call time.

#### Scenario: Chunk size is read at call time

- **WHEN** the markdown chunk size is needed during chunking
- **THEN** it MUST be read from the injected settings at that moment
- **AND** MUST NOT come from a module-level constant captured at import

#### Scenario: Concurrency limiter is built at call time

- **WHEN** the ingestion embedding concurrency limiter is needed
- **THEN** it MUST be created with the injected concurrency value during
  composition or at operation start
- **AND** MUST NOT be a module-level object constructed at import time

#### Scenario: Deliberate compatibility exports are documented

- **WHEN** a module-level constant derived from settings is retained
- **THEN** it MUST be an explicitly documented compatibility export with a
  recorded rationale (for example the reranker model name kept per ADR-033)
- **AND** it MUST NOT be consumed as the live value by any code path

