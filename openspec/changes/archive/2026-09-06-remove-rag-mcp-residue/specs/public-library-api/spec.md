## MODIFIED Requirements

### Requirement: Package identity is `omrg`

The distribution name, import name, and only supported console command SHALL be `omrg`. The previous `rag_mcp` import path, `rag-mcp` distribution name, and `rag-mcp` console command SHALL be absent. No compatibility shim, console-script alias, or automatic fallback SHALL be provided.

This is a v3 breaking change. Existing stored vector data remains compatible. A legacy watcher is migrated only when its user explicitly reruns `omrg install-login-watcher` and confirms replacement or supplies `--force`.

#### Scenario: The new import path works

- **WHEN** a consumer imports `omrg`
- **THEN** the import SHALL succeed

#### Scenario: The old import path is gone

- **WHEN** a consumer imports `rag_mcp`
- **THEN** the import SHALL fail with a standard `ModuleNotFoundError`
- **AND** no shim module SHALL exist to soften it

#### Scenario: Entry points follow the package

- **WHEN** a user installs the v3 distribution
- **THEN** the distribution SHALL install an `omrg` console command that resolves into the `omrg` package
- **AND** the distribution SHALL NOT install a `rag-mcp` console command

#### Scenario: The legacy command fails rather than falling back

- **WHEN** a user invokes `rag-mcp` after upgrading to v3
- **THEN** OMRG SHALL NOT provide a compatibility command or redirect
- **AND** the invocation SHALL fail rather than starting an OMRG transport

#### Scenario: Installed watchers survive the command rename

- **GIVEN** a legacy LaunchAgent whose label starts `com.rag-mcp.watch.` and whose ProgramArguments contain an absolute `rag-mcp` executable
- **WHEN** the user runs `omrg install-login-watcher` for the same watched directory
- **THEN** the installer SHALL discover the legacy plist
- **AND** the installer SHALL require interactive confirmation or `--force` before removing it
- **AND** a replacement watcher SHALL use an absolute `omrg` executable, a `com.omrg.watch.` label, and OMRG log paths
- **AND** the installer SHALL NOT retain or invoke the legacy executable

#### Scenario: Stored data survives the rename

- **GIVEN** a collection indexed by a previous release
- **WHEN** it is opened after the rename
- **THEN** its vectors, metadata and lineage SHALL be readable unchanged
- **AND** no re-ingest SHALL be required by the rename itself
