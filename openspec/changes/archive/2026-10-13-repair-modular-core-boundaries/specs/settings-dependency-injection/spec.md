# Dependency injection repair delta

## MODIFIED Requirements

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

## ADDED Requirements

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
