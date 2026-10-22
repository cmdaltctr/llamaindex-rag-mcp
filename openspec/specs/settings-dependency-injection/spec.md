# settings-dependency-injection Specification

## Purpose
Defines how configuration reaches the code: one frozen
EffectiveSettings value object, threaded through operations as a
parameter (ADR-037). No settings singleton outside the composition
root, and no import-time snapshots — a deployment's configuration is a
fact about an operation, not about the process.

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
- **THEN** it MUST have no import from `omrs.config`, `omrs.compose`, or
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
The producer SHALL remain the collection profile resolver or composition
boundary. Documented legacy entry-boundary resolution SHALL occur only when
explicit settings are omitted; lower helpers SHALL receive the resolved value.
Codebase-map generation, detection, communities, document thresholds, and
cache helpers SHALL use supplied settings rather than independently reading
defaults.

#### Scenario: No global settings read in core
- **WHEN** production core/integrations are checked for resolved configuration-singleton imports
- **THEN** the search SHALL return zero forbidden results

#### Scenario: Settings flow from the entry point
- **WHEN** search receives effective settings with retrieval top-k 20
- **THEN** its dense, fusion, policy, and reranker operations SHALL observe that instance without another lookup

#### Scenario: Two operations with different settings in one process
- **WHEN** two searches receive different reranker settings
- **THEN** each SHALL honour its own supplied settings without interference

#### Scenario: Tests inject rather than patch
- **WHEN** a test needs a non-default value
- **THEN** it SHALL pass an explicit effective-settings instance
- **AND** it SHALL not patch a settings singleton to simulate injection

#### Scenario: PDF reader factory receives the reader name
- **WHEN** ingestion selects a PDF reader
- **THEN** the factory SHALL receive the reader from injected settings without its own settings lookup

#### Scenario: Content-type detection receives the injected settings
- **WHEN** an explicit Engine ingests with no process-default settings installed
- **THEN** detection SHALL use its supplied settings
- **AND** it SHALL not fall back because a global settings getter failed
- **AND** detected content type SHALL retain its existing index-identity role

#### Scenario: Two codebase contexts choose different cache directories
- **WHEN** callers supply settings with distinct cache locations
- **THEN** each map/cache operation SHALL use the supplied location
- **AND** a poisoned default-settings getter SHALL not affect either call

#### Scenario: Document graph threshold is supplied
- **WHEN** map construction builds document communities and cross-links
- **THEN** both document-graph calls SHALL receive the supplied similarity threshold
- **AND** an omitted argument SHALL not cause a leaf default lookup

#### Scenario: Legacy MCP supplies its context
- **WHEN** the existing MCP codebase tool is called with its unchanged parameters
- **THEN** its boundary SHALL supply composed settings/store to core
- **AND** its signature, annotations, path validation, and error shape SHALL remain compatible

### Requirement: No settings singleton outside the composition root

The resolved `Settings` singleton SHALL NOT be instantiated at module import
time. `config` SHALL expose `get_settings()` and SHALL NOT expose a
module-level `settings` object.

`get_settings()` SHALL remain the environment-and-file resolution path, and
its production call sites SHALL remain limited to the composition root.
`Engine.from_environment()` SHALL delegate to that root rather than calling
`get_settings()` itself. An engine constructed from caller-supplied settings
SHALL NOT call it at all.

This preserves the existing sole-caller rule while adding an explicit Engine
factory over it; direct Engine construction accepts already-resolved
`EffectiveSettings` and never reads config.

#### Scenario: Import does not resolve settings

- **WHEN** `omrs.config` is imported
- **THEN** no `Settings()` instance MUST be constructed as a side effect
- **AND** no environment or YAML resolution MUST occur until `get_settings()`
  is called

#### Scenario: Single call site

- **WHEN** the codebase is searched for `get_settings()`
- **THEN** the composition root MUST remain the sole production call site
- **AND** no module under `core/` or `integrations/` MUST call it

#### Scenario: Explicit settings bypass resolution entirely

- **WHEN** an engine is constructed from a caller-supplied settings object
- **THEN** `get_settings()` MUST NOT be called
- **AND** no environment variable or configuration file MUST be read

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

### Requirement: Default accessor guards cover repaired leaves
Executable guards SHALL detect forbidden default-store and default-effective-settings access in metadata taxonomy and codebase/cache leaves, including aliases, qualified calls, and local imports. Documented compatibility entry resolution SHALL have narrow allowances that do not exempt leaf reads.

#### Scenario: A leaf reintroduces a default getter
- **WHEN** a guard fixture or repaired leaf contains a forbidden default read
- **THEN** the guard SHALL fail naming its source and line

#### Scenario: Alias hides the accessor
- **WHEN** a forbidden accessor is imported under another name or called through a module qualifier
- **THEN** the guard SHALL still detect the access

#### Scenario: Supplied values bypass compatibility defaults
- **WHEN** an entry boundary receives explicit settings/store
- **THEN** the behavioural regression SHALL prove that no default accessor is called
