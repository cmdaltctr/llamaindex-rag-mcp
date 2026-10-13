# Internal boundary repair delta

## REMOVED Requirements

### Requirement: Metadata ChromaDB client lazy initialization is safe

**Reason**: Taxonomy now uses the supplied vector-store interface. The old
metadata-owned Chroma client/cache no longer exists and must not be restored
to satisfy this obsolete requirement.

**Migration**: Pass the owning store through classification and test its
context with captured prompts. Provider/store construction remains owned
by composition.

## ADDED Requirements

### Requirement: Codebase helper imports are order independent
Codebase map/cache modules and their shared data models SHALL import successfully in fresh processes regardless of cache-first or map-first order. Existing model import paths and serialised fields SHALL remain compatible.

#### Scenario: Cache imports first
- **WHEN** a fresh interpreter imports cache before the map facade
- **THEN** both imports SHALL succeed and the cache SHALL construct the shared model types

#### Scenario: Map imports first
- **WHEN** a fresh interpreter imports the map facade before cache
- **THEN** both imports SHALL succeed with the same model classes

#### Scenario: Existing model consumer imports through the facade
- **WHEN** a caller imports the existing inventory/map models through their current facade
- **THEN** those names SHALL resolve to the shared classes
- **AND** JSON round-trip fields SHALL remain unchanged

### Requirement: Codebase cache reuse proves its supplied context
Cache reuse SHALL require the current Git commit and compatible supplied settings/store context. Existing filename and map payload SHALL remain. Missing or unproven owner context SHALL be a safe miss; non-Git projects SHALL remain uncached. A process-local identity SHALL not be treated as durable across processes.

#### Scenario: Matching commit and owner
- **WHEN** commit and proven owner context match
- **THEN** the existing cached map SHALL be reusable

#### Scenario: Same path and commit but different owner
- **WHEN** two callers share a cache directory but differ in supplied store or map settings
- **THEN** one SHALL not return the other's cached map

#### Scenario: Old cache has no owner context
- **WHEN** an old record lacks a usable owner context
- **THEN** it SHALL be treated as a miss
- **AND** startup SHALL not delete cache, vector, or experiment data

#### Scenario: Owner context is unavailable
- **WHEN** reliable context cannot be established for persistent reuse
- **THEN** that context SHALL rebuild rather than return an unverified cache hit

#### Scenario: Commit changes or project is not Git
- **WHEN** the commit differs or no Git commit is available
- **THEN** existing invalidation/non-Git behaviour SHALL remain in force

### Requirement: Repair regressions exercise production seams
Regression tests SHALL invoke production chunk dispatch, actual prompt construction with fake model calls, explicit map/cache contexts, and fresh import orders. They SHALL fail when the corresponding repair is removed, rather than pass through a shared private helper or swallowed exception.

#### Scenario: Private splitting bypass is restored
- **WHEN** document dispatch returns to a private splitter despite a registered replacement
- **THEN** the production-dispatch regression SHALL fail

#### Scenario: Global lookup error is swallowed
- **WHEN** taxonomy loses supplied-store labels by swallowing a global lookup error
- **THEN** the prompt-content regression SHALL fail

#### Scenario: Passing structural checks coexist with a behavioural regression
- **WHEN** file-size/import checks pass but one repaired production seam regresses
- **THEN** its dedicated behavioural regression SHALL still fail
