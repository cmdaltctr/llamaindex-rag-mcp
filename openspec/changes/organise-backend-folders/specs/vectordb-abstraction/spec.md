## MODIFIED Requirements

### Requirement: ChromaDB as first implementation

The system SHALL provide the Chroma backend in the `core/vectordb/chroma/`
folder, with `core/vectordb/chroma/store.py` implementing the
`VectorStore` ABC, absorbing all logic from `chroma_utils.py` and the
ChromaDB-specific collection management formerly in the ingestion writer.
`chroma_utils.py` SHALL cease to exist as a top-level module.
Modules in `core/vectordb/chroma/` SHALL be the **only** modules in the
package that import `chromadb` or construct a ChromaDB client; every other
consumer, including the codebase map, SHALL go through the `VectorStore`
interface.

#### Scenario: Single chromadb import site

- **WHEN** `src/omrg/` is searched for `import chromadb` or
  `chromadb.PersistentClient`
- **THEN** every match MUST be in a module under `core/vectordb/chroma/`

#### Scenario: Codebase map goes through the interface

- **WHEN** the codebase map needs indexed-document information
- **THEN** it MUST call `VectorStore` methods on an injected store
- **AND** it MUST NOT create its own ChromaDB client or persist directory
  handle

#### Scenario: Existing collections keep working

- **WHEN** the server starts against an existing flat `chroma_persist_dir`
  (default `./chroma_db`) containing collections
- **THEN** all previously indexed collections MUST be readable and queryable
  with no data migration

#### Scenario: Existing tests pass against the implementation

- **WHEN** `uv run pytest -m "not slow" --cov=omrg` runs
- **THEN** all pre-existing tests MUST pass against the ChromaDB-backed
  implementation with no assertion changes beyond injected-settings plumbing

### Requirement: Chroma client construction SHALL keep one import boundary

All Chroma SDK imports and local/cloud client construction SHALL remain in
the `core/vectordb/chroma/` folder. The composition root SHALL pass resolved
primitive settings into the Chroma factory without importing or constructing
a Chroma SDK client itself.

#### Scenario: Single chromadb import site after cloud support

- **WHEN** production source is searched for direct `chromadb` imports
- **THEN** modules under `core/vectordb/chroma/` SHALL remain the only
  matching modules

### Requirement: Vector-store dense queries return canonical scored rows

The `VectorStore.query_dense()` contract SHALL return store-neutral result rows whose `score` is higher-is-better and conforms to the canonical dense score contract defined by `retrieval-score-semantics`. Backend-native distance fields MAY be retained only as optional diagnostics; core retrieval SHALL NOT require them to compute public relevance scores.

#### Scenario: Chroma adapter owns Chroma metric conversion
- **WHEN** ChromaDB returns its native distance representation
- **THEN** `core/vectordb/chroma/store.py` SHALL convert it to the canonical dense score before returning the store-neutral row
- **AND** `core/retrieval/dense.py` SHALL not apply a Chroma-specific formula

#### Scenario: Lance adapter owns Lance metric conversion
- **WHEN** LanceDB returns `_distance` or another native score
- **THEN** the Lance adapter SHALL convert it to the same declared canonical score semantics before core retrieval consumes it

## ADDED Requirements

### Requirement: Each vector-store backend keeps its code in its own folder

Code that serves one vector-store backend SHALL live in that backend's
folder under `core/vectordb/` (`core/vectordb/lancedb/` and
`core/vectordb/chroma/`). The `core/vectordb/` root SHALL hold only the
shared contract modules. The package file of a backend folder SHALL import
nothing. An automated layout check SHALL enforce these rules.

#### Scenario: Backend module placed at the root

- **WHEN** a module that serves one backend, for example `lance_cache.py`,
  is added at the `core/vectordb/` root
- **THEN** the layout check MUST fail and name the file

#### Scenario: The shared root matches its allow-list

- **WHEN** the layout check lists `core/vectordb/`
- **THEN** the root modules MUST be exactly `__init__`, `base`, `identity`,
  `legacy`, `naming`, `registry`, `score`, `summary` and `validation`
- **AND** the subfolders MUST be exactly `chroma` and `lancedb`

#### Scenario: Backend package file imports nothing

- **WHEN** the `__init__.py` of `core/vectordb/chroma/` or
  `core/vectordb/lancedb/` is inspected
- **THEN** it MUST contain no import statement

#### Scenario: Chroma helper imports in the base install

- **GIVEN** the `chroma` extra is not installed
- **WHEN** a module in `core/vectordb/chroma/` that does not import
  `chromadb`, such as the paged-read mixin, is imported
- **THEN** the import MUST succeed
- **AND** no `chromadb` module MUST be loaded

#### Scenario: The LanceDB folder does not shadow the LanceDB SDK

- **WHEN** the LanceDB store module imports `lancedb`
- **THEN** the name MUST resolve to the installed LanceDB distribution
- **AND** it MUST NOT resolve to the `core/vectordb/lancedb/` folder

#### Scenario: Relative import with a wrong level

- **WHEN** a module under `core/vectordb/` contains a relative import, at
  module level or inside a function, that names a module that does not
  exist
- **THEN** the layout check MUST fail and name the file and line

### Requirement: Vector-store registry import strings resolve

Every lazy `module:attribute` string in the vector-store registry metadata
(backend factory, native sparse probe and storage summary) SHALL name a
module that exists and an attribute that the module defines. A check SHALL
prove this for every registered backend without importing an optional
backend SDK.

#### Scenario: Stale probe path

- **WHEN** a registry string names a module path that no longer exists
- **THEN** the check MUST fail and name the backend and the string

#### Scenario: Missing attribute

- **WHEN** a registry string names an existing module but an attribute the
  module does not define
- **THEN** the check MUST fail and name the backend and the string

#### Scenario: Chroma extra absent

- **GIVEN** the `chroma` extra is not installed
- **WHEN** the check runs
- **THEN** it MUST still verify the Chroma factory and summary strings
- **AND** no `chromadb` module MUST be loaded
