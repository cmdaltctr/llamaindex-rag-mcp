# architecture-boundary-enforcement Specification

## Purpose
Defines the layering invariants that keep the codebase modular as it
grows: provider SDKs stay inside their implementation leaves,
configuration stays a leaf, integrations stay acyclic, business logic
lives under core, and no file outgrows the 500-line ceiling. The
lint-imports contracts and the file-size test are the executable forms
of these rules; this spec is the contract they enforce.

## Requirements

### Requirement: ChromaDB confined to the vector store implementation

Production code SHALL import `chromadb` only from modules in the
`src/omrg/core/vectordb/chroma/` folder. Every other module that needs
vector store access SHALL receive a `VectorStore` instance by injection. An
import-linter contract SHALL enforce this, and SHALL fail CI when any other
module imports `chromadb`.

#### Scenario: Codebase map uses the injected store

- **WHEN** the codebase map builds its file-type index
- **THEN** it MUST obtain document data through the injected `VectorStore`
- **AND** it MUST NOT call `chromadb.PersistentClient(...)` directly

#### Scenario: Contract fails on a new leak

- **WHEN** a module outside `core/vectordb/chroma/` adds `import chromadb`
- **THEN** `uv run lint-imports` MUST fail naming the offending module

### Requirement: Configuration is a leaf module

`omrg.config` SHALL NOT import from `omrg.core` business logic,
`omrg.compose`, `omrg.transports`, `omrg.integrations`, or
`omrg.daemon`. The only sanctioned upward references are the pure-data
subpackage settings models (`omrg.core.*.settings`). Runtime capability
probing (sparse backend availability, PDF reader availability) SHALL live in
`compose.py`, not in `config`. An import-linter contract SHALL enforce this.

#### Scenario: No business-logic import in config

- **WHEN** `src/omrg/config/__init__.py` is inspected
- **THEN** it MUST NOT import `_detect_native_sparse_capability` or any other
  symbol from `omrg.core.retrieval`, `omrg.core.ingestion`,
  `omrg.core.metadata`, or `omrg.core.vectordb`

#### Scenario: Capability probing lives in the composition root

- **WHEN** the effective sparse backend or PDF reader is resolved
- **THEN** the probe MUST execute in `compose.py`
- **AND** `config` MUST expose only the declared preference value

#### Scenario: Contract fails on a new upward import

- **WHEN** a developer adds an import from `omrg.config` to any `core/`
  module other than a `settings` model
- **THEN** `uv run lint-imports` MUST fail

---

### Requirement: Integrations are acyclic leaves

Modules under `src/omrg/integrations/` SHALL NOT import from
`omrg.core`, `omrg.transports`, or `omrg.daemon`. No module SHALL
import another module solely to preserve a test monkeypatch target. An
import-linter contract SHALL enforce the direction.

#### Scenario: Magika has no back-reference

- **WHEN** `src/omrg/integrations/magika.py` is inspected
- **THEN** it MUST NOT import `omrg.codebase_map` or
  `omrg.core.codebase.codebase_map` in any form

#### Scenario: Availability probe is patched at its own module

- **WHEN** a test needs to simulate Magika being unavailable
- **THEN** it MUST patch the probe on `omrg.integrations.magika`
- **AND** the codebase map MUST observe the patched result through its normal
  call into that module

---

### Requirement: Full-package import boundary coverage

The import-linter contract set SHALL cover every package under
`src/omrg/`. The business-layer contract SHALL include
`core.ingestion`, `core.retrieval`, `core.metadata`, `core.chunking`,
`core.vectordb`, `core.profiles`, `core.codebase`, `core.documents`,
`core.community`, `core.answer`, `core.pipelines`, `core.workspace`,
`core.plugins`, `core.experiments`, and `daemon`, forbidding concrete provider and transport dependencies under
the existing sanctioned exceptions. New packages SHALL not be omitted from
coverage.

#### Scenario: Every package is a contract source

- **WHEN** the contract set in `pyproject.toml` is compared against the
  packages present under `src/omrg/`
- **THEN** every package MUST appear as a source module in at least one
  applicable contract
- **AND** new graph/workspace packages MUST not depend on FastAPI, notebook
  runtimes, or transport modules

#### Scenario: Transport import from core fails

- **WHEN** any module under `core/` or `daemon/` imports from
  `omrg.transports`
- **THEN** `uv run lint-imports` MUST fail

### Requirement: Use-case subsystems live under core

The codebase-understanding subsystem SHALL live at `core/codebase/` and the
document-graph subsystem SHALL live at `core/documents/`. Domain algorithms
and graph execution SHALL remain under `core/`. Top-level modules SHALL
serve public API or composition responsibilities rather than implementing
domain algorithms. Domain subsystems SHALL share injected contracts and
settings without direct ingestion/retrieval cross-imports.

#### Scenario: Ingestion no longer reaches upward

- **WHEN** ingestion needs file-type detection
- **THEN** it MUST call the core codebase detector through `core.codebase`
  (a core-to-core import) or the sanctioned `integrations.magika` leaf
- **AND** no `core/` module MUST import a top-level `omrg` module, except
  the one sanctioned lazy import of `omrg.capabilities` in
  `core/ingestion/pipeline.py` that builds an operation-owned OCR client
  when none is injected
- **AND** `uv run lint-imports` MUST fail when any other `core/` module
  imports a top-level `omrg` module

#### Scenario: Top-level business modules are gone

- **WHEN** `src/omrg/` is listed after the change
- **THEN** public API and composition modules such as `__init__.py`,
  `engine.py`, `compose.py`, the `compose_*.py` composition helpers,
  `capabilities.py` (runtime capability probes), and
  `pipeline_templates.py` (built-in graph templates) MAY exist
- **AND** ingestion, retrieval, graph scheduling, and workspace business
  algorithms MUST remain in their owning `core/` packages

#### Scenario: Subsystems share only settings

- **WHEN** domain subsystem imports are inspected
- **THEN** codebase/document graph packages MUST not import ingestion or
  retrieval implementations
- **AND** ingestion and retrieval MUST not import one another
- **AND** cross-domain orchestration MUST use injected contracts

### Requirement: Executable file-size ceiling

No Python file under `src/omrg/` SHALL exceed 500 lines. This ceiling SHALL
be asserted by an automated test rather than by review convention, and the test
SHALL report every offending file with its line count.

#### Scenario: Ceiling holds across the package

- **WHEN** the file-size test runs against `src/omrg/**/*.py`
- **THEN** it MUST pass with zero files over 500 lines

#### Scenario: Regression is caught

- **WHEN** a file grows past 500 lines
- **THEN** the test MUST fail naming that file and its line count

### Requirement: Community integration direction is acyclic
The shared community strategy package SHALL not import from codebase or document graph subsystems. Optional external community adapters SHALL remain integration leaves and SHALL not import from `core/`.

#### Scenario: Both graph subsystems use shared partitioning
- **WHEN** codebase and document graphs select a community strategy
- **THEN** both SHALL depend on the shared community strategy contract
- **AND** neither graph subsystem SHALL import the other

#### Scenario: Leiden adapter is inspected
- **WHEN** the optional Leiden adapter is inspected
- **THEN** it SHALL not import from `omrg.core`, `omrg.transports`, or `omrg.daemon`

### Requirement: Graph scheduling is independent of domain implementations
The generic graph runner SHALL receive operation adapters and resources through injection. It SHALL not import ingestion, retrieval, answering, provider, transport, or process-launch implementations. Domain adapters SHALL remain in their owning packages and use existing registries.

#### Scenario: New operation is registered
- **WHEN** a new compatible operation adapter is added and registered
- **THEN** the runner SHALL execute it without a name-specific branch or concrete implementation import

#### Scenario: Runner reaches into a domain implementation
- **WHEN** the runner imports a domain or transport implementation directly
- **THEN** executable boundary tests SHALL fail naming the offending edge

### Requirement: Application persistence and external tools remain injected leaves
Workspace services SHALL receive persistence and process-control interfaces from composition. Their adapters SHALL exchange pure data and avoid importing core business logic. Core graph execution SHALL not import SQLite, web frameworks, uv, or marimo implementations.

#### Scenario: Web runtime is unavailable
- **WHEN** graph validation/execution is imported without web or notebook dependencies
- **THEN** the import SHALL succeed without constructing an application or tool process

#### Scenario: External process wrapper imports business logic
- **WHEN** a process or persistence integration adds a core business import
- **THEN** executable boundary tests SHALL reject that dependency

### Requirement: HTTP route groups live in one routes folder

Every FastAPI route group of the local web transport SHALL live in the
`transports/api/routes/` folder. The `transports/api/` root SHALL hold the
application factory, the OpenAPI contract and the shared support modules,
and no module that declares a route group. The package file of the routes
folder SHALL import nothing. An automated layout check SHALL enforce these
rules. Moving a route group SHALL NOT change any HTTP path, method, scope
or response.

#### Scenario: Route group added at the transport root

- **WHEN** a module that creates an `APIRouter` is added at the
  `transports/api/` root
- **THEN** the layout check MUST fail and name the file

#### Scenario: Application registers every route group

- **WHEN** the application is built
- **THEN** it MUST register the route group of every module in
  `transports/api/routes/` that declares one
- **AND** the OpenAPI conformance check MUST pass with the same paths as
  before the move

#### Scenario: Source scans include the routes folder

- **WHEN** a test reads the transport source to check a rule, for example
  the workspace file names that must come from one place
- **THEN** it MUST read the modules in `transports/api/routes/` as well
