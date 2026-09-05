# public-library-api Specification

## Purpose
Defines the public API surface of the `omrg` package: the names a library
consumer may import, the guarantee that importing the package has no side
effects, and the identity of the distribution and import name.

## Requirements

### Requirement: The package exposes a public API

The package SHALL export, from its top-level `__init__`, `Engine`,
`EffectiveSettings`, stable public result/error types and `__version__`. A
library consumer SHALL ingest, retrieve and answer through explicit Engine
methods without importing private modules or creating an implicit module-level
engine. Everything not exported SHALL be treated as internal and free to
change without a major version.

#### Scenario: Core operations are importable from the top level

- **WHEN** a consumer imports the package
- **THEN** the engine type, effective-settings type and stable result/error
  types SHALL be importable by name from the top level
- **AND** ingest, search and answer SHALL be documented Engine methods, with
  ingestion and answering async
- **AND** none of them SHALL require importing a module whose name begins with
  an underscore or that lives under an internal subpackage

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

The distribution name, import name, and only supported console command SHALL
be `omrg`. The previous `rag_mcp` import path, `rag-mcp` distribution name,
and `rag-mcp` console command SHALL be absent. No compatibility shim,
console-script alias, or automatic fallback SHALL be provided.

This is a v3 breaking change. Existing stored vector data remains compatible.
A legacy watcher is migrated only when its user explicitly reruns `omrg
install-login-watcher` and confirms replacement or supplies `--force`.

#### Scenario: The new import path works

- **WHEN** a consumer imports `omrg`
- **THEN** the import SHALL succeed

#### Scenario: The old import path is gone

- **WHEN** a consumer imports `rag_mcp`
- **THEN** the import SHALL fail with a standard `ModuleNotFoundError`
- **AND** no shim module SHALL exist to soften it

#### Scenario: Entry points follow the package

- **WHEN** a user installs the v3 distribution
- **THEN** the distribution SHALL install an `omrg` console command that
  resolves into the `omrg` package
- **AND** the distribution SHALL NOT install a `rag-mcp` console command

#### Scenario: The legacy command fails rather than falling back

- **WHEN** a user invokes `rag-mcp` after upgrading to v3
- **THEN** OMRG SHALL NOT provide a compatibility command or redirect
- **AND** the invocation SHALL fail rather than starting an OMRG transport

#### Scenario: Installed watchers survive the command rename

- **GIVEN** a legacy LaunchAgent whose label starts `com.rag-mcp.watch.` and
  whose ProgramArguments contain an absolute `rag-mcp` executable
- **WHEN** the user runs `omrg install-login-watcher` for the same watched
  directory
- **THEN** the installer SHALL discover the legacy plist
- **AND** the installer SHALL require interactive confirmation or `--force`
  before removing it
- **AND** a replacement watcher SHALL use an absolute `omrg` executable, a
  `com.omrg.watch.` label, and OMRG log paths
- **AND** the installer SHALL NOT retain or invoke the legacy executable

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
