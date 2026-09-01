## MODIFIED Requirements

### Requirement: File event filtering

The watcher SHALL respond to `on_created`, `on_modified`, `on_deleted`, AND `on_moved` file system events for files with supported extensions (as defined by the resolved ingestible extension set). The watcher SHALL ignore hidden files (names starting with `.`), temporary files (`~$*`, `*.tmp`, `*.part`), and `.git` directories.

`on_moved` was previously unhandled, so a rename inside the watch tree fired
neither a delete nor an ingest, leaving the old path indexed and the new path
absent.

#### Scenario: Ignores unsupported file types
- **WHEN** an unsupported file (e.g. `.png`, `.mp4`, `.DS_Store`) is created in the watched directory
- **THEN** the watcher SHALL NOT attempt to ingest it

#### Scenario: Ignores hidden and temp files
- **WHEN** a hidden file (e.g. `.gitkeep`) or a temporary file (e.g. `~$doc.docx`) is created or modified
- **THEN** the watcher SHALL NOT attempt to ingest it

#### Scenario: Move events are handled
- **WHEN** a supported file is renamed or moved within the watched tree
- **THEN** the watcher SHALL remove the chunks indexed under its previous path
- **AND** SHALL ingest it under its new path

## ADDED Requirements

### Requirement: A moved source leaves no orphaned chunks

Handling a move SHALL leave the index consistent with the filesystem: the
source's content SHALL be indexed exactly once, under its current path.

#### Scenario: No duplicate content after a move

- **GIVEN** a watched file indexed at path A
- **WHEN** it is moved to path B inside the watch tree
- **AND** the watcher has processed the event
- **THEN** the collection SHALL contain chunks for B
- **AND** SHALL contain no chunks for A

#### Scenario: Move out of the watch tree removes chunks

- **GIVEN** a watched file indexed at path A
- **WHEN** it is moved to a destination outside the watch tree
- **THEN** the chunks for A SHALL be removed
- **AND** no ingest SHALL be attempted for the destination

#### Scenario: Move into the watch tree ingests

- **GIVEN** a supported file outside the watch tree
- **WHEN** it is moved to a path inside the watch tree
- **THEN** it SHALL be ingested under its new path

#### Scenario: Move of an unindexed file is a no-op

- **GIVEN** a supported file inside the watch tree that was never ingested
- **WHEN** it is moved
- **THEN** the removal step SHALL report zero chunks removed
- **AND** SHALL NOT raise
