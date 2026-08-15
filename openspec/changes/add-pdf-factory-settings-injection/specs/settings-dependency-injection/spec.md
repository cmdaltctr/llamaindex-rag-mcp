## MODIFIED Requirements

### Requirement: Core operations receive settings as a parameter

`search()` and `ingest_path_async()` SHALL accept an `EffectiveSettings`
parameter and SHALL pass it down to every module they call. Modules under
`core/` and `integrations/` SHALL NOT import a process-wide settings object
and SHALL NOT fetch the composition-root default settings. The producer of
the instance SHALL be `ProfileResolver.resolve(collection)` for
collection-bound operations and `compose.py` for operations with no
collection.

#### Scenario: No global settings read in core

- **WHEN** `src/rag_mcp/core/` and `src/rag_mcp/integrations/` are searched for
  `from ...config import settings` (or any equivalent import of the resolved
  settings singleton)
- **THEN** the search MUST return zero results

#### Scenario: No composition-root default fetch under integrations

- **WHEN** `src/rag_mcp/integrations/` is searched for callers of the
  composition-root default settings accessor
- **THEN** the search MUST return zero results
- **AND** every configuration value an integration needs MUST arrive as a
  parameter from its caller

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

#### Scenario: PDF reader factory receives the reader name

- **WHEN** the ingestion pipeline needs a PDF reader adapter
- **THEN** the call site SHALL pass the resolved reader name from its injected
  settings
- **AND** the factory SHALL perform no settings lookup of its own
