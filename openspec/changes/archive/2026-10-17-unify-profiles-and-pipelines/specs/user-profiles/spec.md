# Spec Delta

## Purpose

Let users make their own profiles in the web workspace. A user profile owns three pipelines (Ingest, Search, Answer) that decide how a collection that uses it is indexed, searched and answered.

## ADDED Requirements

### Requirement: The profile list shows built-in and user profiles

`GET /v1/profiles` SHALL return every built-in profile and every user profile that is not deleted. Each item SHALL carry `profile_id`, `kind` (`builtin` or `user`), `title`, `description`, `base_profile`, `slots` (`ingest`, `search`, `answer` pipeline ids, all `null` for a built-in), `ready`, `not_ready_reasons` and `used_by` (the names of collections whose stored profile tag is this id).

#### Scenario: Fresh workspace

- **WHEN** a workspace with no user profiles requests the profile list
- **THEN** the list MUST hold `documents` and `codebase` with `kind: builtin`, `ready: true` and `slots` whose three values are `null`

#### Scenario: A user profile is in use

- **WHEN** collection `notes` is tagged with user profile `my-notes`
- **THEN** the `my-notes` item MUST show `kind: user`, its three pipeline ids, and `used_by: ["notes"]`

### Requirement: Reading a built-in profile returns its standard graphs

`GET /v1/profiles/{profile_id}` SHALL return the same fields as a list item. For a built-in profile it SHALL also return `standard_graphs` with the keys `ingest`, `search` and `answer`. Each value SHALL be the graph document that `POST /v1/profiles` with that built-in as `source` copies into the matching pipeline. The graphs SHALL be shaped by that built-in's own settings, not only by the host settings. For a user profile `standard_graphs` SHALL be `null`. List items SHALL NOT carry `standard_graphs`.

#### Scenario: Read codebase

- **WHEN** a client reads `GET /v1/profiles/codebase` on a host whose default profile turns hybrid retrieval off
- **THEN** `standard_graphs.search` and `standard_graphs.answer` MUST include the sparse retrieval and fusion steps
- **AND** each of the three graphs MUST name `codebase` as its operational profile and name no collection

#### Scenario: Same graphs as a duplicate

- **WHEN** a client reads `GET /v1/profiles/documents` and then duplicates `documents`
- **THEN** each graph in `standard_graphs` MUST equal revision 1 of the matching pipeline of the duplicate

#### Scenario: Read a user profile

- **WHEN** a client reads `GET /v1/profiles/my-notes`
- **THEN** `standard_graphs` MUST be `null`

#### Scenario: List has no graphs

- **WHEN** a client requests `GET /v1/profiles`
- **THEN** no item MUST carry `standard_graphs`

### Requirement: A user profile has a fixed id and three pipelines

A user profile SHALL have an id, a title, a description, a base profile (`documents` or `codebase`) and exactly three pipelines: Ingest, Search and Answer. The server SHALL make the id from the title as a lower-case slug. The id SHALL NOT be `documents`, `codebase` or `hybrid`, SHALL NOT repeat any earlier id, and SHALL never change. The base profile SHALL never change.

#### Scenario: Id made from the title

- **WHEN** a user creates a profile titled "My Notes" and no profile has the id `my-notes`
- **THEN** the new profile MUST have the id `my-notes`

#### Scenario: Id already taken

- **WHEN** a user creates a second profile titled "My Notes"
- **THEN** the new profile MUST get a different id, such as `my-notes-2`

#### Scenario: Reserved title

- **WHEN** a user creates a profile titled "Documents"
- **THEN** the new profile id MUST NOT be `documents`

### Requirement: Duplicating a built-in profile copies the standard pipelines

`POST /v1/profiles` with `source` set to a built-in id SHALL create a user profile whose base profile is that built-in. Its three pipelines SHALL be the standard ingestion, search and answer graphs, shaped by that built-in's settings, each saved as revision 1. Each graph SHALL name the base profile as its operational profile and SHALL name no collection.

#### Scenario: Duplicate codebase

- **WHEN** a user duplicates `codebase`
- **THEN** the new profile MUST have base profile `codebase`
- **AND** its Search and Answer graphs MUST include the sparse retrieval and fusion steps, because `codebase` turns hybrid retrieval on

#### Scenario: Same results as the built-in

- **WHEN** a collection on `documents` is moved to a fresh duplicate of `documents`
- **THEN** a search with the same query MUST return the same rows, scores and score kinds as before

### Requirement: Duplicating a user profile copies its current revisions

`POST /v1/profiles` with `source` set to a user profile id SHALL create a new user profile with the same base profile. Each new pipeline SHALL start from the source pipeline's current saved revision and layout. Later edits to either profile SHALL NOT change the other.

#### Scenario: Independent copy

- **WHEN** a user duplicates `my-notes` and then saves a new Search revision in the copy
- **THEN** the Search pipeline of `my-notes` MUST keep its earlier current revision

### Requirement: An empty profile starts with empty pipelines

`POST /v1/profiles` with `source: null` SHALL create a user profile with base profile `documents` and three pipelines that have no saved revision. The profile SHALL be not ready until each pipeline passes the readiness check.

#### Scenario: Empty profile is not ready

- **WHEN** a user creates an empty profile
- **THEN** the response MUST show `ready: false`
- **AND** `not_ready_reasons` MUST name each of the three pipelines as having no saved graph

### Requirement: Users can rename and describe their own profiles

`PATCH /v1/profiles/{profile_id}` SHALL change only the title and the description of a user profile. The id SHALL stay the same. A title SHALL hold 1 to 80 characters after trimming and no control characters. The server SHALL refuse a change to a built-in profile with status 403.

#### Scenario: Rename keeps the id

- **WHEN** a user renames `my-notes` to "Meeting notes"
- **THEN** the profile id MUST stay `my-notes`
- **AND** collections tagged `my-notes` MUST keep working

#### Scenario: Rename a built-in

- **WHEN** a client sends a rename for `documents`
- **THEN** the server MUST answer 403 and change nothing

### Requirement: Deleting a profile is a soft delete and is refused while in use

`DELETE /v1/profiles/{profile_id}` SHALL mark a user profile as deleted and keep its pipelines, revisions and runs. The server SHALL refuse the delete with status 409 and the `used_by` list while any collection uses the profile. It SHALL refuse to delete a built-in with status 403. A deleted profile id SHALL NOT be given to a new profile.

#### Scenario: Delete an unused profile

- **WHEN** a user deletes `my-notes` and no collection uses it
- **THEN** the profile list MUST NOT show `my-notes`
- **AND** its revisions and run records MUST stay in the workspace database

#### Scenario: Delete a profile in use

- **WHEN** a user deletes `my-notes` while collection `notes` uses it
- **THEN** the server MUST answer 409 with `used_by: ["notes"]`
- **AND** the profile MUST stay unchanged

### Requirement: Readiness checks each pipeline against its purpose

A user profile SHALL be ready only when each pipeline has a saved revision, passes the draft graph check, and matches its purpose contract. Ingest: input `path`, output `summary`, exactly one enabled write step. Search: input `query`, output `results`, no enabled write step. Answer: input `query`, output `answer`, no enabled write step. Each failure SHALL add one plain-English line to `not_ready_reasons`. The line SHALL name the pipeline, and the step when one step causes it, and SHALL say what to fix. An issue code SHALL NOT be the whole line.

#### Scenario: Search pipeline lacks its output

- **WHEN** the Search pipeline of a profile has no graph output named `results`
- **THEN** the profile MUST show `ready: false`
- **AND** one reason MUST say that the Search pipeline needs an output named `results`

#### Scenario: Write step in the Answer pipeline

- **WHEN** the Answer pipeline contains an enabled step that writes to a collection
- **THEN** the profile MUST show `ready: false` with a reason naming that step

#### Scenario: Two write steps in the Ingest pipeline

- **WHEN** the Ingest pipeline contains two enabled steps that write to a collection
- **THEN** the profile MUST show `ready: false`
- **AND** one reason MUST say that the Ingest pipeline needs exactly one write step

### Requirement: Only a ready profile can be bound to a collection

`changeCollectionProfile` SHALL accept a built-in id or the id of a ready user profile. For a user profile it SHALL also check each pipeline against the target collection, including the embedding model check, before it issues a confirmation token. The tag SHALL be the profile id. A failed check SHALL give status 400 with the reasons.

#### Scenario: Bind a ready profile

- **WHEN** a user previews and confirms `my-notes` for collection `notes`
- **THEN** the collection's stored profile tag MUST become `my-notes`
- **AND** no chunk or vector MUST change

#### Scenario: Bind a profile that is not ready

- **WHEN** a user previews an empty profile for collection `notes`
- **THEN** the server MUST answer 400 with the not-ready reasons and issue no confirmation token

#### Scenario: Profile changes between preview and confirm

- **WHEN** a user saves a new Search revision of `my-notes` after the preview and before the confirmation
- **THEN** the confirmation MUST be refused with status 409 and a request for a new preview

### Requirement: Search on a user-profile collection runs its Search pipeline

A search on a collection that uses a user profile SHALL run that profile's current Search revision within the request, with the query as the `query` input and the collection as the graph collection. It SHALL return the same row shape as a built-in search. A request value the caller sets (top-k, threshold, rerank, metadata filter, expand window) SHALL replace the matching step setting.

#### Scenario: Search follows the saved graph

- **WHEN** the Search pipeline of `my-notes` has its rerank step turned off and a user searches collection `notes`
- **THEN** the results MUST come from that graph with no reranking
- **AND** each row MUST have the fields a built-in search row has

#### Scenario: Request top-k wins

- **WHEN** the Search pipeline sets top-k to 20 and the request sets `top_k: 5`
- **THEN** the search MUST return at most five rows

#### Scenario: Hybrid flag on a user profile

- **WHEN** a search request on a user-profile collection sets `hybrid`
- **THEN** the Search pipeline's own steps MUST decide whether sparse retrieval runs

### Requirement: Answers on a user-profile collection run its Answer pipeline

An answer on a collection that uses a user profile SHALL run that profile's current Answer revision within the request. It SHALL return the same result shape as a built-in answer, including status, citations, evidence and verification. The server answer model SHALL write the answer, because MCP client sampling and pre-fetched rows cannot pass into a pipeline run. A direct Engine call that supplies a client completion or pre-fetched rows for a user-profile collection SHALL fail with a plain message that says so.

#### Scenario: Chat follows the profile

- **WHEN** a user asks a question in Chat about collection `notes` that uses `my-notes`
- **THEN** the answer MUST come from the Answer pipeline of `my-notes`
- **AND** the Chat view MUST show its citations and verification status as for a built-in profile

#### Scenario: Client completion requested

- **WHEN** an MCP client that offers sampling asks for an answer from a user-profile collection
- **THEN** the server MUST answer with its own answer model and MUST NOT send sampling requests to the client

#### Scenario: Pre-fetched rows on a user profile

- **WHEN** a library caller passes pre-fetched rows to `Engine.answer` for a user-profile collection
- **THEN** the call MUST fail with a message that says the Answer pipeline does its own retrieval and uses the server model

### Requirement: User profiles work in every process that reads the workspace

The stdio MCP server, the CLI and the watcher SHALL resolve user profiles from the default workspace database (`~/.omrg/workspace/workspace.db`, the default folder of `omrg web`) when that file exists. They SHALL open it read-only and SHALL NOT create, migrate or write it. A search, answer or ingestion on a collection that uses a user profile SHALL then run that profile's pipelines, as in the web server. When the file does not exist, they SHALL refuse a collection that uses a user profile with an error that names the profile, names the path that was read, and tells the user to start `omrg web` once with the default workspace or to change the collection's profile to `documents` or `codebase`. Binding a user profile to a collection SHALL stay in the web server and its MCP endpoint.

#### Scenario: Stdio MCP search on a user profile

- **WHEN** the default workspace holds user profile `my-notes`, collection `notes` uses it, and an agent calls `search_documents` on the stdio MCP server
- **THEN** the results MUST come from the Search pipeline of `my-notes`
- **AND** the workspace database MUST stay unchanged

#### Scenario: CLI search on a user profile

- **WHEN** the default workspace holds user profile `my-notes`, collection `notes` uses it, and the user runs `omrg search` on `notes`
- **THEN** the results MUST come from the Search pipeline of `my-notes`

#### Scenario: Watcher ingests into a user profile

- **WHEN** the watcher sees a new file for collection `notes`, which uses `my-notes`
- **THEN** the file MUST be ingested through the Ingest pipeline of `my-notes`

#### Scenario: No workspace database

- **WHEN** the default workspace database does not exist and the CLI, the watcher or the stdio MCP server handles collection `notes`, which is tagged `my-notes`
- **THEN** it MUST fail with an error that names `my-notes` and the path `~/.omrg/workspace/workspace.db`
- **AND** the error MUST tell the user to start `omrg web` once or to change the collection to `documents` or `codebase`

#### Scenario: Older workspace schema

- **WHEN** the default workspace database exists with a schema version older than 3
- **THEN** the process MUST treat it as a workspace with no user profiles
- **AND** it MUST NOT migrate the file

#### Scenario: Bind from the CLI

- **WHEN** a user runs `omrg set-profile` with the user profile id `my-notes`
- **THEN** the CLI MUST refuse with a message that tells the user to bind user profiles in Knowledge Base or through the MCP endpoint of `omrg web`
- **AND** the collection's profile tag MUST stay unchanged

### Requirement: Ingestion into a user-profile collection runs its Ingest pipeline

Ingestion into a collection that uses a user profile SHALL run that profile's current Ingest revision with the path as the `path` input. It SHALL return the same summary fields as built-in ingestion. A source indexed by a different Ingest graph SHALL be processed again on its next ingestion. Saving an Ingest revision SHALL NOT start ingestion.

#### Scenario: Ingest graph changed

- **WHEN** a user saves a new Ingest revision with a different chunk size and then ingests the same folder again
- **THEN** each source in that folder MUST be processed again
- **AND** saving the revision alone MUST NOT change any vector

### Requirement: Built-in profiles keep the direct path

A search, answer or ingestion on a collection that uses a built-in profile, or no profile, SHALL use the standard Engine operations and SHALL NOT run a saved pipeline.

#### Scenario: Built-in search unchanged

- **WHEN** a collection on `documents` is searched after this change
- **THEN** the search MUST run through the standard Engine search and run no graph
- **AND** the rows and scores MUST be the same as before this change

### Requirement: Saving a slot revision reports and protects the collections that use it

Saving a revision of a pipeline that belongs to a profile in use SHALL return `affected_collections`. When the new graph would make that profile not ready, the server SHALL refuse the save with status 409 and the reasons. A profile in no use SHALL accept any valid graph, and SHALL show `ready: false` when that graph fails the readiness check.

#### Scenario: Save a Search change on a profile in use

- **WHEN** a user saves a new Search revision of `my-notes` while `notes` and `papers` use it
- **THEN** the response MUST hold `affected_collections: ["notes", "papers"]`

#### Scenario: Save would break a profile in use

- **WHEN** a user saves a Search revision with no `results` output for a profile that `notes` uses
- **THEN** the server MUST refuse the save with status 409
- **AND** the earlier current revision MUST stay current

### Requirement: Saved Studio pipelines become user profiles on upgrade

On the first start after upgrade, each saved Studio pipeline that belongs to no profile SHALL become a user profile. A workspace job pipeline, whose layout holds the key `omrg_task`, SHALL be skipped. The profile title SHALL be the pipeline's `layout.title` when it is not empty after trimming, else the pipeline title. The base profile SHALL be the `graph.profile` of the current revision when it is `documents` or `codebase`, else `documents`. The pipeline SHALL fill the slot whose contract its current revision matches first (Ingest, Search, Answer). The other slots SHALL get the standard graphs of the base profile. A pipeline with no saved revision, or a graph that matches no contract, SHALL go in the Search slot, and the profile SHALL be not ready. When the current revision names another operational profile than the base, the upgrade SHALL save one new revision that names the base profile, and SHALL keep the earlier revisions and their runs.

#### Scenario: A saved search pipeline

- **WHEN** the workspace holds a saved pipeline "Docs search" whose graph has input `query` and output `results`
- **THEN** after upgrade a user profile titled "Docs search" MUST exist with that pipeline as its Search pipeline
- **AND** its run records MUST still point at that pipeline

#### Scenario: Canvas title wins

- **WHEN** a saved pipeline has the title "New pipeline" and the layout title "Papers search"
- **THEN** after upgrade its user profile MUST be titled "Papers search"

#### Scenario: Codebase preset keeps its base

- **WHEN** a saved pipeline's current graph names the operational profile `codebase`
- **THEN** after upgrade its user profile MUST have base profile `codebase`
- **AND** its other two pipelines MUST hold the standard `codebase` graphs

#### Scenario: Graph with no operational profile

- **WHEN** a saved Search pipeline's current graph names no operational profile
- **THEN** after upgrade its user profile MUST have base profile `documents`
- **AND** the Search pipeline MUST have one new current revision that names `documents`, with the earlier revision kept

#### Scenario: Workspace job pipeline

- **WHEN** the workspace holds the pipeline "Workspace job: ingest" whose layout holds `omrg_task`
- **THEN** after upgrade no user profile MUST exist for it
- **AND** its runs MUST stay unchanged

#### Scenario: A graph that matches no contract

- **WHEN** a saved pipeline has no graph inputs
- **THEN** after upgrade its profile MUST show `ready: false` with a reason for the Search pipeline

#### Scenario: Upgrade runs once

- **WHEN** the server starts a second time after upgrade
- **THEN** no new profile MUST appear

### Requirement: Standalone pipelines are no longer created

`POST /v1/pipelines` SHALL answer 410 Gone with a message that tells the client to create a profile. Profile slot pipelines SHALL stay readable and editable through the other `/v1/pipelines` operations. `GET /v1/pipelines/{pipeline_id}` SHALL show the owning profile id and slot.

#### Scenario: Old client creates a pipeline

- **WHEN** a client sends `POST /v1/pipelines`
- **THEN** the server MUST answer 410 and create nothing

#### Scenario: Open a slot pipeline

- **WHEN** a client reads the Search pipeline of `my-notes`
- **THEN** the response MUST carry `profile_slot: {"profile_id": "my-notes", "slot": "search"}`

### Requirement: MCP clients can list profiles

The MCP server SHALL offer a read-only `list_profiles` tool. It SHALL return the same items as `GET /v1/profiles` when the server has a workspace catalogue, and the built-in profiles only when it has none. The stdio MCP server SHALL use the default workspace database when it exists.

#### Scenario: Agent picks a profile

- **WHEN** an agent calls `list_profiles` on the web server's MCP endpoint
- **THEN** the result MUST list built-in and user profiles with their ids and readiness
