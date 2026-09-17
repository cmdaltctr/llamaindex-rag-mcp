# settings-dependency-injection Delta

## MODIFIED Requirements

### Requirement: Core operations receive settings as a parameter

`search()` and `ingest_path_async()` SHALL accept an `EffectiveSettings`
parameter and SHALL pass it down to every module they call. Modules under
`core/` and `integrations/` SHALL NOT import a process-wide settings object.
The producer of the instance SHALL be `ProfileResolver.resolve(collection)` for
collection-bound operations and `compose.py` for operations with no
collection.

#### Scenario: No global settings read in core

- **WHEN** `src/omrg/core/` and `src/omrg/integrations/` are searched for
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

#### Scenario: PDF reader factory receives the reader name

- **WHEN** the ingestion pipeline needs a PDF reader adapter
- **THEN** the call site SHALL pass the resolved reader name from its injected
  settings
- **AND** the factory SHALL perform no settings lookup of its own

#### Scenario: Content-type detection receives the injected settings

- **WHEN** `ingest_path_async()` runs in a process that constructed its
  `Engine` directly and installed no process-global default
  (`get_default_effective_settings()` would raise)
- **THEN** content-type detection MUST proceed using the operation's injected
  `EffectiveSettings`
- **AND** it MUST NOT raise, log, or otherwise fall back to extension-based
  routing because of a settings lookup
- **AND** a populated `content_type` MUST participate in the file's index
  identity exactly as it does in processes that installed the global
