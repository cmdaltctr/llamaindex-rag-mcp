## Purpose

Define machine-local visibility for indexed source paths that no longer exist,
without changing source identity or deleting stored chunks.

## Requirements

### Requirement: Document listings expose tri-state orphan status

Every listed document row SHALL include an `orphaned` field. The field SHALL be
`true` when the row has a usable absolute source path that does not exist on the
current machine. It SHALL be `false` when that absolute path exists. It SHALL be
`null` when the row has no usable absolute path.

The `null` state MUST cover legacy rows with basename-only `file_name` values,
rows whose display source is `"unknown"`, and any path syntax that is not
absolute on the current machine. The system MUST NOT infer a filesystem state
from `source_id` or another metadata field.

#### Scenario: Absolute source path is missing

- **GIVEN** a listed row carries an absolute source path
- **AND** that path does not exist on the current machine
- **WHEN** documents are listed
- **THEN** the row MUST contain `"orphaned": true`

#### Scenario: Absolute source path exists

- **GIVEN** a listed row carries an absolute source path
- **AND** that path exists on the current machine
- **WHEN** documents are listed
- **THEN** the row MUST contain `"orphaned": false`

#### Scenario: Legacy row has only a basename

- **GIVEN** a legacy row has no `file_path`
- **AND** its display source falls back to a basename-only `file_name`
- **WHEN** documents are listed
- **THEN** the row MUST contain `"orphaned": null`

#### Scenario: Row has no source metadata

- **GIVEN** a row has neither `file_path` nor `file_name`
- **WHEN** documents are listed with the display source `"unknown"`
- **THEN** the row MUST contain `"orphaned": null`

### Requirement: Existence checks are restricted to absolute paths

The system MUST run a filesystem existence check only when the listed source is
an absolute path on the current machine. It MUST NOT check a relative path,
basename, empty value, or `"unknown"` against the process working directory.

#### Scenario: Basename matches a file in the process working directory

- **GIVEN** a legacy row displays the basename `paper.pdf`
- **AND** a file named `paper.pdf` exists in the process working directory
- **WHEN** documents are listed
- **THEN** the row MUST contain `"orphaned": null`
- **AND** the system MUST NOT test that basename for filesystem existence

#### Scenario: Foreign path syntax is not absolute locally

- **GIVEN** an index contains a source path from another operating system
- **AND** the current machine does not recognise that syntax as absolute
- **WHEN** documents are listed
- **THEN** the row MUST contain `"orphaned": null`
- **AND** the system MUST NOT test that value against the local working directory

### Requirement: Listing transports preserve orphan status

The human-readable CLI list output SHALL include a visible `Orphaned` column.
The CLI JSON output SHALL preserve `orphaned` as `true`, `false`, or `null`
without conversion. The MCP document-listing tool SHALL return the same field
as an additive key on each successful row.

Adding the field SHALL NOT remove or rename the existing `source`, `source_id`,
or `chunks` keys.

#### Scenario: Human CLI output shows orphan status

- **WHEN** a user runs the human-readable document list command
- **THEN** the table MUST include an `Orphaned` column
- **AND** every row MUST visibly distinguish missing, present, and unknown states

#### Scenario: CLI JSON output preserves tri-state values

- **GIVEN** a document listing contains missing, present, and unknown rows
- **WHEN** a user requests JSON output
- **THEN** the rows MUST carry `true`, `false`, and `null` respectively
- **AND** the existing row keys MUST remain present

#### Scenario: MCP listing passes through the additive field

- **WHEN** a caller invokes the MCP document-listing tool
- **THEN** every successful row MUST include the core `orphaned` value unchanged
- **AND** existing MCP clients that ignore additive keys MUST remain compatible

### Requirement: Orphan status means missing on this machine

The core listing API docstring and CLI help text MUST state that `orphaned`
means “missing on this machine”. User documentation for CLI and MCP listing MUST
state the same limit. The system MUST NOT present the field as proof that the
source is globally missing, because an index can contain canonical absolute
paths created on another machine.

#### Scenario: Index was created on another machine

- **GIVEN** a stored absolute path does not exist on the machine reading the index
- **WHEN** the listing reports `"orphaned": true`
- **THEN** the documented meaning MUST be “missing on this machine”
- **AND** the documentation MUST NOT claim that the original source no longer exists anywhere

#### Scenario: User inspects CLI help

- **WHEN** a user requests help for the document list command
- **THEN** the help text MUST explain the machine-local meaning of orphan status

### Requirement: Orphan visibility never mutates indexed data

Computing or displaying `orphaned` SHALL be read-only. The system MUST NOT
delete chunks, change the path-derived `source_id` formula, move source files,
collect garbage, or start move watching as part of document listing. Cleanup
SHALL remain an explicit operator action through existing preview and deletion
commands.

#### Scenario: Missing source is listed

- **GIVEN** indexed chunks refer to a missing absolute source path
- **WHEN** documents are listed
- **THEN** the row MUST report `"orphaned": true`
- **AND** all indexed chunks MUST remain unchanged

#### Scenario: Operator chooses manual cleanup

- **GIVEN** a row reports `"orphaned": true`
- **WHEN** the operator decides to remove it
- **THEN** cleanup MUST use the existing explicit preview or deletion command
- **AND** listing alone MUST NOT perform cleanup

#### Scenario: Source identity remains path-derived

- **WHEN** orphan visibility is added
- **THEN** the existing canonical-path `source_id` formula MUST remain unchanged
- **AND** moving or renaming a file MUST continue to create a different logical source
