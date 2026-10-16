# internal-maintainability Specification

## Purpose

Define internal code-quality boundaries for helper naming, lock naming, test isolation, and concurrency primitives so the codebase remains honest and auditable without changing user-facing behaviour.

## Requirements

### Requirement: Unsupported file discovery comments match behavior
Internal file discovery helpers SHALL not contain unreachable branches or comments claiming unsupported single files are tracked when callers reject unsupported single files earlier.

#### Scenario: Unsupported single file handling remains explicit
- **WHEN** `ingest_path_async()` receives a single file with an unsupported extension
- **THEN** it SHALL return an error explaining the unsupported extension
- **THEN** `_gather_supported_files()` SHALL not contain misleading unreachable logic for that case

### Requirement: Benchmark chunking helper boundary is explicit
The benchmark command SHALL use a chunking helper whose intended internal/public boundary is explicit.

#### Scenario: Benchmark chunks a file without indexing it
- **WHEN** `omrg benchmark --file path` runs
- **THEN** the command SHALL read and chunk the file without writing to ChromaDB
- **THEN** the helper used for read-and-chunk behavior SHALL be named or documented so maintainers know it is intentionally shared with benchmark

### Requirement: Shared watcher state lock is clearly named
Watcher synchronization primitives SHALL be named according to the state they protect.

#### Scenario: Lock protects timer and hash-cache state
- **WHEN** a lock protects both pending timers and hash-cache cleanup
- **THEN** its name SHALL reflect shared watcher state rather than only timers
- **THEN** watcher behavior SHALL remain unchanged

### Requirement: Test persist directory does not imply shared filesystem state
Tests SHALL not rely on a hardcoded shared ChromaDB persist path when an isolated path is available.

#### Scenario: Test environment isolation
- **WHEN** tests configure `CHROMA_PERSIST_DIR`
- **THEN** the configured path SHALL be isolated per test run or ignored by a documented in-memory ChromaDB patch
- **THEN** future readers SHALL not infer that tests write to a shared `/tmp` path

### Requirement: Documented source paths resolve

Documentation that cites a source file path SHALL cite a path that exists.
Every `src/omrg/**/*.py` path referenced in `docs/guides/`,
`tests/TEST_README.md`, the root `AGENTS.md` or a folder guidance file SHALL
resolve to a file on disk. A short citation that starts at a top-level
package folder (`core/`, `transports/`, `integrations/`, `config/` or
`daemon/`) and omits `src/omrg/` SHALL resolve below `src/omrg/` in the same
way. Records under `docs/adr/` are EXCLUDED: an ADR legitimately cites paths
that were correct when the decision was taken and have since moved.

#### Scenario: A guide cites a path deleted by a refactor

- **WHEN** a guide references `src/omrg/config.py` after the v2 split moved it to `src/omrg/config/__init__.py`
- **THEN** the documentation reference check SHALL fail
- **THEN** the failure SHALL name the citing file, its line, and the unresolved path

#### Scenario: A guide cites a moved file without the package prefix

- **WHEN** a guide references `core/vectordb/lancedb.py` after the file moved to `core/vectordb/lancedb/store.py`
- **THEN** the documentation reference check SHALL fail
- **THEN** the failure SHALL name the citing file, its line, and the unresolved path

#### Scenario: A folder guidance file cites a moved file

- **WHEN** `src/omrg/core/vectordb/AGENTS.md` cites a module path that no longer exists
- **THEN** the documentation reference check SHALL fail and name that file and line

#### Scenario: A historical ADR cites a since-deleted path

- **WHEN** `docs/adr/026-provider-registry-and-openrouter.md` references `src/omrg/metadata_extractor.py`, a v1 module deleted in v2.0.0
- **THEN** the check SHALL NOT fail
- **THEN** the ADR SHALL remain unmodified, its accuracy carried by a dated forward note instead

### Requirement: Documented provider names match the live registries

The provider names listed in `docs/guides/providers.md` SHALL match the names
registered in the embedding and LLM provider registries exactly. The guide
SHALL delimit these names in a machine-readable block so the check reads a
declared list rather than inferring one from prose.

#### Scenario: A provider is added without updating the guide

- **WHEN** a new provider is registered in `core/providers/embeddings/registry.py` via `register()`
- **AND** `docs/guides/providers.md` is not updated to list it
- **THEN** the registry contract test SHALL fail
- **THEN** the failure SHALL name the provider present in the registry but absent from the guide

#### Scenario: The guide names a provider that no longer exists

- **WHEN** `docs/guides/providers.md` lists a provider name absent from `available()`
- **THEN** the registry contract test SHALL fail
- **THEN** the failure SHALL name the provider documented but unregistered

#### Scenario: Guide and registries agree

- **WHEN** the documented names equal `embed_registry.available()` for embeddings and `llm_registry.available()` for LLMs
- **THEN** the check SHALL pass without requiring any suppression or allowlist entry

### Requirement: Test modules restore logging state they install

Test modules SHALL NOT leave logging handlers, levels, or stream bindings
installed after their tests complete when that configuration was added or
replaced during the module's execution. CLI tests that parse command output
as JSON SHALL receive output uncontaminated by logging-machinery error
banners regardless of which test module ran earlier in the same session.

#### Scenario: MCP tool tests precede a CLI JSON test

- **WHEN** pytest executes `tests/test_mcp_tools.py` immediately before
  `tests/test_cli.py::TestIngestCLI::test_ingest_json_output`
- **THEN** `json.loads(result.output)` succeeds
- **AND** the captured output contains no `--- Logging error ---` banner

#### Scenario: Isolation behaviour is unchanged

- **WHEN** the CLI JSON test runs alone
- **THEN** it passes exactly as before the fix

#### Scenario: A test module reconfigures logging

- **WHEN** a test module adds or replaces root logging handlers during its
  execution
- **THEN** teardown restores the handler and level configuration that existed
  before the module ran

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

### Requirement: Key source folders carry agent guidance files

Each of these folders SHALL contain an `AGENTS.md` file and a `CLAUDE.md`
symbolic link that points to it: `src/omrg/`, `src/omrg/core/`,
`src/omrg/core/vectordb/`, `src/omrg/core/retrieval/`,
`src/omrg/core/ingestion/`, `src/omrg/core/pipelines/`,
`src/omrg/transports/`, `src/omrg/integrations/`, `web/src/` and `tests/`.
Each guidance file SHALL be at most 40 lines and SHALL link to the root
`AGENTS.md`. An automated check SHALL enforce these rules.

#### Scenario: Guidance file missing

- **WHEN** one of the listed folders has no `AGENTS.md`
- **THEN** the check SHALL fail and name the folder

#### Scenario: Claude link points elsewhere

- **WHEN** a listed folder has a `CLAUDE.md` that is a regular file, or a link whose target is not `AGENTS.md`
- **THEN** the check SHALL fail and name the folder

#### Scenario: Guidance file grows too long

- **WHEN** a guidance file has more than 40 lines
- **THEN** the check SHALL fail and name the file and its line count

#### Scenario: Guidance file does not link back

- **WHEN** a guidance file contains no link to the root `AGENTS.md`
- **THEN** the check SHALL fail and name the file

### Requirement: Agent guidance files stay out of the wheel

The built wheel SHALL contain no `AGENTS.md` and no `CLAUDE.md` file at any
depth. The release wheel check SHALL report each such file it finds.

#### Scenario: Wheel built from the source tree

- **WHEN** a wheel is built from a tree that holds folder guidance files under `src/omrg/`
- **THEN** no `AGENTS.md` or `CLAUDE.md` entry SHALL appear in the wheel

#### Scenario: A guidance file leaks into a wheel

- **WHEN** the release wheel check reads a wheel that contains `omrg/core/AGENTS.md`
- **THEN** the check SHALL fail and name that entry
