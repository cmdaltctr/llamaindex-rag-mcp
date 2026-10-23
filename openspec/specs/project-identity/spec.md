# project-identity Specification

## Purpose
Name the project OMRS and keep every identifier it creates on a user's machine under that name. It also fixes what stays readable from before the rename and guards against the old name returning in live files.

## Requirements

### Requirement: The project is named OMRS

The project SHALL be named OMRS, short for "Opinionated Modular RAG System". Live user-facing text SHALL use that name: the CLI help, the web workspace title, the HTTP API title, the MCP server instructions and the live documentation. The name OMRG SHALL NOT appear in live user-facing text.

#### Scenario: The CLI names the project

- **WHEN** a user runs `omrs --help`
- **THEN** the help text SHALL name OMRS
- **AND** the help text SHALL NOT contain the word OMRG

#### Scenario: The web workspace names the project

- **WHEN** a user opens the web workspace
- **THEN** the page title SHALL name OMRS

### Requirement: Runtime identifiers use the omrs prefix

Every identifier the project creates on a user's machine or sends to a client SHALL use `omrs`. The identifiers are:

| Identifier | Value |
| --- | --- |
| Distribution and import name | `omrs` |
| Console command | `omrs` |
| MCP server name (client tool prefix) | `omrs` |
| Environment variable prefix | `OMRS_` |
| Settings file | `omrs.jsonc` |
| Config folder | `$OMRS_CONFIG_DIR`, else `$XDG_CONFIG_HOME/omrs`, else `~/.config/omrs` |
| Data folder | `~/.omrs` |
| Secret reference path | `file://~/.config/omrs/secrets/<name>.key` |
| macOS keychain service | `omrs` |
| launchd labels | `com.omrs.web`, `com.omrs.watch.<id>` |
| Log folder | `~/Library/Logs/omrs` |
| Session cookie and token prefixes | `omrs_session`, `omrs_bs_`, `omrs_ss_`, `omrs_bt_` |
| OpenAPI extension keys | `x-omrs-scopes`, `x-omrs-scope-catalogue` |
| Browser storage key prefix | `omrs-` |
| LanceDB dataset epoch key | `omrs_dataset_epoch` |
| Workspace job layout key | `omrs_task` |
| Large-data folder (owner's machine) | `~/Development/DATA/omrs` |

No identifier SHALL be created or read under an `omrg` name. No compatibility alias, startup check or migration command SHALL be provided: the old names stop working.

#### Scenario: A new install creates only omrs identifiers

- **GIVEN** a machine with no previous install
- **WHEN** a user runs the web server, saves a setting, stores a key in the keychain and installs the login item
- **THEN** every folder, file, keychain entry and launchd label created SHALL use the `omrs` names in the table

#### Scenario: The old environment prefix is not read

- **GIVEN** `OMRG_CONFIG_DIR` is set and `OMRS_CONFIG_DIR` is not
- **WHEN** a process resolves the config folder
- **THEN** the process SHALL NOT use `OMRG_CONFIG_DIR`

#### Scenario: The old console command is absent

- **WHEN** a user installs the distribution
- **THEN** the distribution SHALL install no `omrg` console command

### Requirement: A dataset written before the rename stays usable

A LanceDB collection written before the rename SHALL open with its vectors, metadata and lineage unchanged. Its stored dataset epoch sits under the old key, so the store SHALL treat it as a table with no epoch: the existing unmarked-table path. The first write after the rename SHALL give it an epoch under `omrs_dataset_epoch`.

#### Scenario: An existing dataset is read after the rename

- **GIVEN** a LanceDB collection written before the rename
- **WHEN** the renamed release opens it
- **THEN** its vectors, metadata and lineage SHALL be readable unchanged
- **AND** no re-ingest SHALL be required

#### Scenario: A new dataset uses the new key

- **WHEN** the renamed release creates a new LanceDB collection
- **THEN** the collection SHALL store its dataset epoch under `omrs_dataset_epoch`

### Requirement: Live files do not use the old identity

A guard test SHALL fail when a live file contains the old identity. Live files are the source, tests, scripts, web sources and live documentation. The guard SHALL exempt: ADRs, TDRs, archived OpenSpec changes, run experiment records (numbered `experiments/` folders and OpenSpec changes of run experiments), `CHANGELOG.md`, the change that performs the rename, and the specs that require the old names to be absent. Each exemption SHALL be a named entry in the guard with a reason. Unrun experiments SHALL use the new name.

#### Scenario: A stray old name fails the guard

- **WHEN** a live source file contains the string `omrg`
- **AND** the file is not on the exemption list
- **THEN** the guard test SHALL fail and name the file and line

#### Scenario: Historical records are exempt

- **WHEN** an ADR or an archived OpenSpec change contains `omrg`
- **THEN** the guard test SHALL pass for that file
