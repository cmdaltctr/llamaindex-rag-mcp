# workspace-projects delta

## Purpose

Home as the project list and the per-project library where sources are managed and searched: uploads, folder ingest, profile, deletion and metadata-filtered search. A project is a collection.

## ADDED Requirements

### Requirement: Home lists the workspace projects

The workspace SHALL show a Home view listing every collection as a project card with its name, profile label, document count and chunk count, obtained from `listCollections`. When no collection exists, the view SHALL show an empty state whose single action starts an ingest into a named collection.

#### Scenario: Collections exist

- **WHEN** the engine reports two collections
- **THEN** Home MUST show one card per collection with its name, profile label, document count and chunk count

#### Scenario: No collections

- **WHEN** the engine reports no collections
- **THEN** Home MUST show an empty state naming the cause and offering one ingest action

### Requirement: Opening a project shows its Knowledge Base

Selecting a project card SHALL open `#/knowledge-base/<collection>`, the Knowledge Base scoped to that collection, showing its source table with orphan status, the upload panel, the folder ingest panel, profile information and search. Opening `#/knowledge-base` without a collection SHALL open the last-used collection when the server still lists it, and otherwise SHALL show a project picker.

#### Scenario: Open a project with sources

- **WHEN** the user opens a project that has three sources
- **THEN** the Knowledge Base MUST list the three sources with their machine-local orphan status and the collection's profile label

#### Scenario: Reload keeps the active project

- **WHEN** the user reloads the page at `#/knowledge-base/papers`
- **THEN** the Knowledge Base for `papers` MUST be shown

#### Scenario: Last-used collection was deleted

- **WHEN** the user opens `#/knowledge-base` and the last-used collection no longer exists
- **THEN** the project picker MUST be shown and the stale default MUST be dropped

### Requirement: Files upload into the active project

The Knowledge Base view SHALL upload selected files through the managed upload endpoint and start an ingest job into the active project's collection, enforcing the server-side per-file limit, and SHALL surface each job's status.

#### Scenario: Upload starts a job

- **WHEN** the user uploads an accepted file into the active project
- **THEN** the upload MUST complete, an ingest job MUST be submitted for the managed path, and its status MUST be shown in the view

#### Scenario: A finished job shows what it indexed

- **WHEN** an ingest job the server marks completed carries a result in which every file failed to index
- **THEN** the view MUST NOT show it as completed, MUST show that nothing was indexed with the number of files that failed and a fixed hint for the failing stage, and MUST NOT show file paths or exception text

#### Scenario: A job with some failed files

- **WHEN** an ingest job completes and at least one file, but not every file, failed to index
- **THEN** the view MUST show it as completed with errors and the number of files that failed

#### Scenario: Oversized file is refused before upload

- **WHEN** the user selects a file larger than the configured per-file limit
- **THEN** the client MUST refuse the file locally with a friendly message and MUST NOT send it

### Requirement: Folder ingest offers approved roots only

Folder ingest SHALL offer only roots approved at server start, SHALL submit `ingestPath` for the chosen root path into the active project's collection, and SHALL explain the `--root` flag when no root is approved.

#### Scenario: Ingest from an approved root

- **WHEN** one root is approved and the user starts a folder ingest
- **THEN** a job MUST be submitted and listed with its status

#### Scenario: No approved root

- **WHEN** no root is approved
- **THEN** the panel MUST state that no folder is approved and name the `--root` server flag

### Requirement: The Knowledge Base searches the active project

The Knowledge Base view SHALL offer metadata-filtered search over the active project's collection, through the same search operation and profile resolution as other clients. Results SHALL list ranked chunks with their source and score, and each score SHALL keep its score-kind label. Opening a result SHALL show the chunk in the chunk viewer.

#### Scenario: Filtered search

- **WHEN** the user searches the active project with a metadata filter
- **THEN** the view MUST list only matching chunks in rank order, each with its source, score and score kind

#### Scenario: Open a result

- **WHEN** the user opens a search result
- **THEN** the chunk viewer MUST show that chunk's text and source
