## ADDED Requirements

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

No identifier SHALL be created under an `omrg` name. No compatibility alias SHALL be installed.

#### Scenario: A new install creates only omrs identifiers

- **GIVEN** a machine with no previous install
- **WHEN** a user runs the web server, saves a setting, stores a key in the keychain and installs the login item
- **THEN** every folder, file, keychain entry and launchd label created SHALL use the `omrs` names in the table

#### Scenario: The old environment prefix is not read

- **GIVEN** `OMRG_CONFIG_DIR` is set and `OMRS_CONFIG_DIR` is not
- **WHEN** a process resolves the config folder
- **THEN** the process SHALL NOT use `OMRG_CONFIG_DIR`
- **AND** the process SHALL follow the legacy-install-migration requirement for a detected old variable

#### Scenario: The old console command is absent

- **WHEN** a user installs the distribution
- **THEN** the distribution SHALL install no `omrg` console command

### Requirement: Stored-data identifiers keep their original names

An identifier written inside existing stored data SHALL keep its original name so that stored data stays readable. The LanceDB table metadata key `omrg_dataset_epoch` SHALL stay unchanged. The workspace pipeline layout key `omrg_task`, stored in `workspace.db`, SHALL stay unchanged. The code SHALL define each such identifier once, with a comment that states why it keeps the old name.

#### Scenario: An existing dataset is read after the rename

- **GIVEN** a LanceDB collection written before the rename
- **WHEN** the renamed release opens it
- **THEN** its vectors, metadata and lineage SHALL be readable unchanged
- **AND** the BM25 cache validity token SHALL be computed from the same `omrg_dataset_epoch` key
- **AND** no re-ingest SHALL be required

#### Scenario: An existing workspace job pipeline is still recognised

- **GIVEN** a `workspace.db` written before the rename, with a pipeline whose layout carries `omrg_task`
- **WHEN** the renamed release lists the workspace job pipelines
- **THEN** that pipeline SHALL be recognised as a job pipeline

#### Scenario: A new dataset uses the original key

- **WHEN** the renamed release creates a new LanceDB collection
- **THEN** the collection SHALL store its dataset epoch under `omrg_dataset_epoch`

### Requirement: Live files do not use the old identity

A guard test SHALL fail when a live file contains the old identity. Live files are the source, tests, scripts, web sources and live documentation. The guard SHALL exempt: the `omrg_dataset_epoch` and `omrg_task` constants, the migration code and its tests, ADRs, TDRs, archived OpenSpec changes, the `openspec/` tree, experiment reports and `CHANGELOG.md`. Each exemption SHALL be a named entry in the guard with a reason. Live specs and active changes SHALL use the new name, except where a requirement describes the old identity (the migration requirements, the absence of the old commands and the old environment variable). A review step, not the guard, checks the `openspec/` tree.

#### Scenario: A stray old name fails the guard

- **WHEN** a live source file contains the string `omrg`
- **AND** the file is not on the exemption list
- **THEN** the guard test SHALL fail and name the file and line

#### Scenario: Historical records are exempt

- **WHEN** an ADR or an archived OpenSpec change contains `omrg`
- **THEN** the guard test SHALL pass for that file
