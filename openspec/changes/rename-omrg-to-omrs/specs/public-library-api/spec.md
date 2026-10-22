## RENAMED Requirements

- FROM: `### Requirement: Package identity is `omrg``
- TO: `### Requirement: Package identity is `omrs``

## MODIFIED Requirements

### Requirement: Package identity is `omrs`

The distribution name, import name, and only supported console command SHALL
be `omrs`. The previous `omrg` and `rag_mcp` import paths, the `omrg` and
`rag-mcp` distribution names, and the `omrg` and `rag-mcp` console commands
SHALL be absent. No compatibility shim, console-script alias, or automatic
fallback SHALL be provided.

This is a breaking change. Existing stored vector data remains compatible.
A legacy watcher is migrated only when its user explicitly runs `omrs migrate`
or reruns `omrs install-login-watcher` and confirms replacement or supplies
`--force`.

#### Scenario: The new import path works

- **WHEN** a consumer imports `omrs`
- **THEN** the import SHALL succeed

#### Scenario: The old import path is gone

- **WHEN** a consumer imports `omrg` or `rag_mcp`
- **THEN** the import SHALL fail with a standard `ModuleNotFoundError`
- **AND** no shim module SHALL exist to soften it

#### Scenario: Entry points follow the package

- **WHEN** a user installs the distribution
- **THEN** the distribution SHALL install an `omrs` console command that
  resolves into the `omrs` package
- **AND** the distribution SHALL NOT install an `omrg` or `rag-mcp` console
  command

#### Scenario: The legacy command fails rather than falling back

- **WHEN** a user invokes `omrg` or `rag-mcp` after upgrading
- **THEN** OMRS SHALL NOT provide a compatibility command or redirect
- **AND** the invocation SHALL fail rather than starting an OMRS transport

#### Scenario: Installed watchers survive the command rename

- **GIVEN** a legacy LaunchAgent whose label starts `com.rag-mcp.watch.` or
  `com.omrg.watch.` and whose ProgramArguments contain an absolute `rag-mcp`
  or `omrg` executable
- **WHEN** the user runs `omrs install-login-watcher` for the same watched
  directory
- **THEN** the installer SHALL discover the legacy plist
- **AND** the installer SHALL require interactive confirmation or `--force`
  before removing it
- **AND** a replacement watcher SHALL use an absolute `omrs` executable, a
  `com.omrs.watch.` label, and OMRS log paths
- **AND** the installer SHALL NOT retain or invoke the legacy executable

#### Scenario: Stored data survives the rename

- **GIVEN** a collection indexed by a previous release
- **WHEN** it is opened after the rename
- **THEN** its vectors, metadata and lineage SHALL be readable unchanged
- **AND** no re-ingest SHALL be required by the rename itself
