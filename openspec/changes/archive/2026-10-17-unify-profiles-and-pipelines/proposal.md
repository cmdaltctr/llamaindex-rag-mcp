# Proposal: Unify profiles and pipelines

## Why

Today a collection follows one of two fixed YAML profiles (`documents`, `codebase`), and Studio pipelines are a separate thing that only Studio runs. Chat, Knowledge Base search, MCP tools and ingestion never use a saved pipeline (`transports/api/routes/documents.py:131-206`, `transports/mcp/search.py:94`, `transports/api/routes/jobs.py:146-157`). The user wants one concept, the **profile**, so that the web app can control how each collection reads, splits, embeds, searches and answers. This change gives the backend that concept. The Studio and Knowledge Base screens (`studio-profiles-gallery`) build on the API this change adds.

## What Changes

- Add **user profiles**, stored in the workspace database. A user profile has an immutable id, a title, a description, a base built-in profile and three pipelines, one per purpose: **Ingest**, **Search** and **Answer**.
- Built-in profiles (`documents`, `codebase`) stay read-only YAML. They keep today's direct Engine path with no change in speed or results.
- Add profile routes: `GET /v1/profiles`, `POST /v1/profiles` (duplicate a built-in, duplicate a user profile, or start empty), `GET`, `PATCH` and `DELETE /v1/profiles/{profile_id}`. Delete is a soft delete and is refused while a collection uses the profile.
- `GET /v1/profiles/{profile_id}` of a built-in returns `standard_graphs`: the Ingest, Search and Answer graphs that a duplicate of that built-in would get. Studio uses them to open a built-in read-only.
- A collection can use any profile that is ready. `changeCollectionProfile` accepts user profile ids and keeps its preview and confirmation token flow. The preview names the three pipelines and their saved revisions.
- When a collection uses a user profile, search, answer and ingest run that profile's pipelines in the request, through the Engine. They return today's result shapes. They create no run records. Answers use the server's answer model.
- User profiles work in every process that finds the workspace database: the web server and its MCP endpoint, the stdio MCP server, the CLI and the watcher. The stdio MCP server, the CLI and the watcher open the default workspace (`~/.omrg/workspace/workspace.db`) read-only. Binding a user profile to a collection stays in the web server.
- **BREAKING** (CLI, stdio MCP server, watcher): when no workspace database exists, a collection that uses a user profile fails with a message that names the profile, the path that was read and the fix.
- Read-only graph runs on one Engine run at the same time. Only graphs that write to a collection wait for each other.
- The draft check (`validatePipeline` without run inputs) returns the effective value of each step setting. Studio step cards can then show values without run inputs.
- `POST /v1/pipelines/{pipeline_id}/revisions` also returns `affected_collections` when the pipeline belongs to a profile in use. A save that would make an in-use profile not ready is refused.
- On first start after upgrade, each saved Studio pipeline becomes a user profile. Its title is the canvas title when one was typed. Its base profile is the graph's own profile when that is `documents` or `codebase`. Workspace job pipelines stay as they are.
- **BREAKING**: `POST /v1/pipelines` (`createPipeline`) is withdrawn and returns 410 Gone. Create a profile instead. `/v1/pipelines` stays as the storage layer for slot graphs.
- Add an MCP `list_profiles` tool. `change_collection_profile` accepts user profile ids on the web server's MCP endpoint.
- Record the decision in ADR-080 "Profiles own pipelines". Update the configuration, pipelines, MCP tools and CLI guides.

## Capabilities

### New Capabilities

- `user-profiles`: user profiles that own three pipelines; how they are created, renamed, deleted, checked for readiness, bound to collections, and run by search, answer and ingest requests in every process that can read the workspace.

### Modified Capabilities

- `profiles-dual-use-case`: a collection can name a user profile; every process resolves it from the workspace database; the invalid-tag error lists ready user profiles and explains the no-workspace case; the profile-change preview covers user profiles.
- `pipeline-graphs`: read-only graph runs on one Engine overlap; only writing graphs are serialised; the draft check returns effective values (ADDED requirements only).
- `pipeline-run-records`: profile requests from Chat, search, MCP and ingestion create no run records (ADDED requirement only).

## Impact

- Code: `src/omrg/engine.py`, new `src/omrg/engine_profiles.py`, new `src/omrg/engine_lifecycle.py`, `src/omrg/compose_pipelines.py`, new `src/omrg/compose_profiles.py`, `src/omrg/compose.py`, `src/omrg/compose_engine.py`, `src/omrg/core/profiles/{resolver,contract}.py`, new `src/omrg/core/profiles/catalogue.py`, `src/omrg/core/pipelines/admission.py`, `src/omrg/core/workspace/{records,repository,cleanup}.py`, `src/omrg/integrations/workspace_sqlite/{schema,repository}.py`, new `src/omrg/integrations/workspace_sqlite/profiles.py`, `src/omrg/transports/api/routes/{admin,graphs}.py`, `src/omrg/transports/api/{lifespan,app,runs_wiring}.py`, new `src/omrg/transports/api/routes/profiles.py`, `src/omrg/transports/mcp/{__init__,profile,search,answer,answer_mrtr,server}.py`, `src/omrg/transports/cli/{web,profile,search,answer,ingest,install_login_watcher}.py`, `src/omrg/daemon/watcher.py`.
- API: new `/v1/profiles` operations; `standard_graphs` on a built-in profile; `ProfileChangeRequest.profile` accepts any profile id; `validatePipeline` gains `nodes` with effective controls on the draft check; `savePipelineRevision` gains `affected_collections`; `getPipeline` gains `profile_slot`; `createPipeline` withdrawn. OpenAPI in `src/omrg/transports/api/openapi.yaml`.
- Data: workspace schema version 3 (new `profiles` table). The existing migration code backs up the database first. Other processes open the database read-only and never migrate it.
- Dependencies: none new.
- Order: this change lands after `organise-backend-folders`, which moves the route modules into `transports/api/routes/`.
- Release: this change and `studio-profiles-gallery` ship in the same release. `studio-profiles-gallery` uses this API and updates `workspace-studio`, which still describes `createPipeline`. Do not cut a release between the two merges.
- Other changes: `clarify-canvas-steps` reads the draft check values. `add-profile-embedding-model` builds on the profile record and catalogue.
