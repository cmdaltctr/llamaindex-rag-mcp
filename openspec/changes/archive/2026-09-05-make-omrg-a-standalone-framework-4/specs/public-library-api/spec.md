## ADDED Requirements

### Requirement: The package exposes a public API

The package SHALL export, from its top-level `__init__`, exactly these public
names: `Engine`, `EffectiveSettings` and `__version__`. A library consumer
SHALL ingest, retrieve and answer through explicit Engine methods without
importing private modules or creating an implicit module-level engine.
Everything not exported SHALL be treated as internal and free to change
without a major version.

The initial surface is deliberately minimal. Internal registries, adapters,
builders and convenience functions SHALL NOT be exported "just in case".

#### Scenario: Core operations are importable from the top level

- **WHEN** a consumer imports the package
- **THEN** `Engine`, `EffectiveSettings` and `__version__` SHALL be
  importable by name from the top level
- **AND** none of them SHALL require importing a module whose name begins
  with an underscore or that lives under an internal subpackage

#### Scenario: Engine methods are the documented operation surface

- **WHEN** the `Engine` type is inspected
- **THEN** it SHALL provide: `ingest` (async, returning the existing
  ingestion result `dict`), `search` (sync, returning the existing
  `list[dict]` hit shape with the same retrieval-override keyword parameters
  as the core `search()`), `answer` (async, returning the existing answer
  result `dict`), `list_collections` (sync, returning `list[str]`),
  `delete_collection(name)` (sync) and `close()` (sync)
- **AND** no additional public methods SHALL be added beyond this set in
  this change

#### Scenario: Result and error shapes are the existing ones

- **WHEN** an Engine operation returns or fails
- **THEN** successful results SHALL use the existing plain `dict` /
  `list[dict]` shapes documented for the corresponding core operation
- **AND** failures SHALL propagate as the existing core exceptions (for
  example `ValueError` for invalid configuration, `ImportError` for a
  missing optional extra)
- **AND** no new result or exception DTO classes SHALL be introduced by this
  change

#### Scenario: The exported surface is declared

- **WHEN** the top-level module is inspected
- **THEN** `__all__` SHALL enumerate the public surface
- **AND** a name absent from `__all__` SHALL be documented as internal

#### Scenario: Importing the package has no side effects

- **WHEN** the package is imported
- **THEN** no settings SHALL be resolved
- **AND** no provider, vector store, model or network client SHALL be
  constructed
- **AND** no process-global state SHALL be mutated

#### Scenario: Optional dependencies do not break import

- **WHEN** the package is imported in an environment lacking any optional
  extra
- **THEN** the import SHALL succeed
- **AND** the failure SHALL occur only when the corresponding capability is
  used, with an actionable message naming the extra

### Requirement: Package identity is `omrg`

The distribution name and the import name SHALL both be `omrg`. The previous
`rag_mcp` import path and `rag-mcp` distribution name SHALL be removed rather
than aliased at the Python level.

No Python compatibility shim SHALL be provided. This follows the project's
established precedent: the v1 top-level shims were deleted outright in v2.0.0
rather than carried forward, and this change lands on the v3 breaking branch.

#### Scenario: The new import path works

- **WHEN** a consumer imports `omrg`
- **THEN** the import SHALL succeed

#### Scenario: The old import path is gone

- **WHEN** a consumer imports `rag_mcp`
- **THEN** the import SHALL fail with a standard `ModuleNotFoundError`
- **AND** no shim module SHALL exist to soften it

#### Scenario: Entry points follow the package

- **WHEN** the console scripts are invoked
- **THEN** the `omrg` entry points SHALL resolve into the `omrg` package
- **AND** the MCP server, CLI and watcher SHALL behave exactly as before the
  rename

#### Scenario: The old command survives as a one-major alias

- **GIVEN** the deprecated `rag-mcp` console alias retained for one major
- **WHEN** an installed LaunchAgent invokes the `rag-mcp` executable, or the
  watcher installer resolves the command
- **THEN** the alias SHALL resolve to the same entry point as `omrg`
- **AND** existing `com.rag-mcp.watch.*` labels and `~/Library/Logs/rag-mcp/`
  log paths SHALL remain valid and SHALL NOT be migrated in this change
- **AND** the installer MUST NOT create a duplicate watcher under a new label

#### Scenario: Stored data survives the rename

- **GIVEN** a collection indexed by a previous release
- **WHEN** it is opened after the rename
- **THEN** its vectors, metadata and lineage SHALL be readable unchanged
- **AND** no re-ingest SHALL be required by the rename itself

### Requirement: The reported version cannot drift

`__version__` SHALL derive from installed package metadata rather than a
hard-coded literal, so it cannot disagree with the distribution version.

The previous arrangement allowed exactly that: the literal in `__init__.py`
reported `1.8.0` while the distribution was at `2.2.0`, because the release
tool updated only the `pyproject.toml` value.

#### Scenario: Version matches the distribution

- **WHEN** `__version__` is read
- **THEN** it SHALL equal the installed distribution's version

#### Scenario: Release automation needs no second update site

- **WHEN** a release bumps the distribution version
- **THEN** no source literal SHALL require updating for `__version__` to be
  correct

#### Scenario: A regression test guards the invariant

- **WHEN** the test suite runs
- **THEN** a test SHALL assert `__version__` equals the metadata version
- **AND** it SHALL fail if a literal is reintroduced
