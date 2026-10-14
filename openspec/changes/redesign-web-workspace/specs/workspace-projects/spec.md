# workspace-projects delta

## Purpose

Home as the project list and the per-project library where sources are managed: uploads, folder ingest, profile and deletion. A project is a collection.

## ADDED Requirements

### Requirement: Home lists the workspace projects

The workspace SHALL show a Home view listing every collection as a project card with its name, profile label, document count and chunk count, obtained from `listCollections`. When no collection exists, the view SHALL show an empty state whose single action starts an ingest into a named collection.

#### Scenario: Collections exist

- **WHEN** the engine reports two collections
- **THEN** Home MUST show one card per collection with its name, profile label, document count and chunk count

#### Scenario: No collections

- **WHEN** the engine reports no collections
- **THEN** Home MUST show an empty state naming the cause and offering one ingest action

### Requirement: Opening a project shows its library

Selecting a project card SHALL open the project library scoped to that collection, showing its source table with orphan status, the upload panel, the folder ingest panel, and profile information. The active project SHALL persist across reloads through the URL and local storage.

#### Scenario: Open a project with sources

- **WHEN** the user opens a project that has three sources
- **THEN** the library MUST list the three sources with their machine-local orphan status and the collection's profile label

#### Scenario: Reload keeps the active project

- **WHEN** the user reloads the page while a project is open
- **THEN** the same project library MUST be restored from persisted state

### Requirement: Files upload into the active project

The Knowledge Base view SHALL upload selected files through the managed upload endpoint and start an ingest job into the active project's collection, enforcing the server-side per-file limit, and SHALL surface each job's status.

#### Scenario: Upload starts a job

- **WHEN** the user uploads an accepted file into the active project
- **THEN** the upload MUST complete, an ingest job MUST be submitted for the managed path, and its status MUST be shown in the view

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
