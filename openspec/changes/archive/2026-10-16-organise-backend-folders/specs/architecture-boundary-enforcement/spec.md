## MODIFIED Requirements

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

## ADDED Requirements

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
