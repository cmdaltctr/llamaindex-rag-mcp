# Design: Unify profiles and pipelines

## Context

See `proposal.md` for the reason. This section lists only the facts in the code that shape the approach. Paths use the folder layout of `organise-backend-folders`, which lands first: HTTP route modules live in `transports/api/routes/`.

- **Requests never run graphs today.** Chat calls `engine.answer` (`transports/api/routes/documents.py:182-206`). Knowledge Base search calls `engine.search` (`routes/documents.py:131-162`). MCP uses `engine.search` (`transports/mcp/search.py:94`, `answer_mrtr.py:194`), `engine.answer` (`answer.py:243`) and `engine.ingest` (`ingest.py:41`). The `ingestPath` job calls `engine.ingest` (`routes/jobs.py:146-157`), which calls `ingest_path_async` (`engine.py:140-164`).
- **Graphs can run in a request.** `await engine.run_pipeline(definition, inputs=...)` returns a `PipelineResult` (`engine.py:323-351`). `compose_experiments.py:355` already does this. Studio runs go through `RunService` instead (one consumer, bounded queue, `core/workspace/service.py`).
- **All graph runs on one Engine are serialised.** `EnginePipelines.run` holds one `asyncio.Lock` per Engine (`compose_pipelines.py:316,440`). Built-in `Engine.search` takes no lock, so built-in searches already run at the same time in the thread pool.
- **The profile tag is a collection metadata key.** `routes/admin.py:200-240` previews, issues a confirmation token, then calls `apply_profile_change`, which writes `{"profile": name}` (`core/profiles/contract.py:226`). `ProfileResolver.resolve` reads the tag and loads the YAML bundle, cached per name (`core/profiles/resolver.py:249-280`, `402-425`).
- **Pipelines are stored in the workspace SQLite database.** Tables `pipelines`, `pipeline_revisions` (immutable through triggers) and `runs` (foreign keys to both) are in `integrations/workspace_sqlite/schema.py:26-68`. There is no rename or delete. Workspace job pipelines are marked by the layout key `omrg_task` (`TASK_LAYOUT_KEY`, `transports/api/runs_wiring.py:55`; test `WorkspaceRuns.is_task_pipeline`, `:327-329`). `_task_revision` creates them with the title "Workspace job: <kind>" and saves the revision document `{"task": kind}`, which is not a graph (`:331-348`).
- **Standard graphs already match the Engine.** `pipeline_templates.py:39,185-218` publishes `ingestion`, `search`, `answer`. Parity tests prove equal results: search (`tests/unit/test_pipeline_templates.py:110`), answer and ingestion (`tests/unit/test_pipeline_templates_parity.py:85,120`). The search output `results` is a `ContextBundle` whose `public_rows()` is the `search()` row shape (`core/retrieval/graph_adapters_values.py:142-158`). The answer output `answer` is the `answer()` result dict. Each ingestion unit outputs a `make_file_detail` dict, the same helper `ingest_path_async` uses (`core/ingestion/graph_adapters.py:328-402`).
- **Lever order is node params, then graph overrides, then environment, then profile** (`core/pipelines/admission.py:115-182`). `graph.profile` may name only `documents` or `codebase` (`core/pipelines/validation.py:26,106`).
- **The draft check returns no effective values.** `validatePipeline` without `inputs` returns order, versions and collections only (`transports/api/routes/graphs.py:256-261`). Effective controls are built only during admission (`core/pipelines/admission.py:141-192`), which needs run inputs. Preflight keeps the validated parameters of every valid node, also when other nodes have issues (`core/pipelines/validation.py:291-325`). The draft path already resolves profiles to report profile issues (`compose_pipelines.py:353-354`).
- **Only the web server opens the workspace database.** `omrg web` takes `--workspace`, default `~/.omrg/workspace` (`transports/cli/web.py:64-66,250`). The file is `workspace.db` in that folder (`WorkspaceLayout.records`, `core/workspace/cleanup.py:59-60`). `read_saved_web_port` already reads it without creating or migrating it (`integrations/workspace_sqlite/settings.py:141-152`). The stdio MCP server builds its Engine at `transports/mcp/__init__.py:121`. Every other CLI subcommand runs `compose.ensure_runtime_setup()` first (`transports/cli/__init__.py:202-205`). The CLI `search`, `answer` and `ingest` commands, the login watcher catch-up and the watcher call core functions directly, not the Engine (`transports/cli/search.py:58`, `transports/cli/install_login_watcher.py:201-215`, `daemon/watcher.py:65,287-297`).
- **Size ceilings are close.** `engine.py` has 498 lines and `integrations/workspace_sqlite/repository.py` has 498 lines. `compose_pipelines.py` has 461 lines, `compose.py` 428 and `core/pipelines/admission.py` 256. The limit is 500 (`tests/test_file_size_ceiling.py`).
- **Import contracts** (`pyproject.toml`): `core.*` must not import top-level modules (`core-never-imports-top-level-modules`) or `integrations` business code; `integrations` must not import `core` (`integrations-are-leaves`); `core.workspace` must not import `sqlite3` or domains.
- **MCP search pre-fills defaults.** `transports/mcp/search.py:76-89` fills `top_k`, `similarity_threshold` and `hybrid` from the resolved profile before it calls `engine.search`.

## Goals / Non-Goals

**Goals:**

- One server-side concept, the profile, that every request path follows.
- User profiles work in every process that can read the workspace database: the web server, the stdio MCP server, the CLI and the watcher.
- No change in speed or results for built-in profiles.
- Read-only graphs on one Engine run at the same time.
- A stable API for `studio-profiles-gallery` (contract in the brief, kept exactly; fields only added).
- Studio step cards can show effective values without run inputs.

**Non-Goals:**

- Web screens (`studio-profiles-gallery`), canvas cards (`clarify-canvas-steps`), the PDF reader step setting (`add-pdf-reader-step-setting`) and the embedding model per profile (`add-profile-embedding-model`).
- Creating, editing or binding user profiles outside the web server and its MCP endpoint (D11).
- Automatic re-ingestion after an Ingest change (D5).
- Client-side sampling for user-profile answers (D17).

## Decisions

The brief's decisions D1 to D12 are recorded first, each with the alternative. D13 onwards are decisions this design adds.

### D1 Profile shape and storage

A user profile is a row in the workspace database: `profile_id` (slug, immutable), `title`, `description`, `base_profile` (`documents` or `codebase`), three slot pipeline ids, `created_at`, `updated_at`, `archived_at`. Schema version 3 adds:

```sql
CREATE TABLE profiles (
    profile_id TEXT PRIMARY KEY
        CHECK (profile_id NOT IN ('documents', 'codebase', 'hybrid')),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    base_profile TEXT NOT NULL CHECK (base_profile IN ('documents', 'codebase')),
    ingest_pipeline_id TEXT NOT NULL UNIQUE REFERENCES pipelines(pipeline_id),
    search_pipeline_id TEXT NOT NULL UNIQUE REFERENCES pipelines(pipeline_id),
    answer_pipeline_id TEXT NOT NULL UNIQUE REFERENCES pipelines(pipeline_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);
-- Triggers: profile_id, base_profile and the three slot ids never change;
-- a pipeline id may appear in one slot of one profile only.
```

The id comes from the title: lower case, non-alphanumeric runs become `-`, at most 64 characters, pattern `^[a-z0-9][a-z0-9-]{0,63}$`. A taken or reserved id gets `-2`, `-3` and so on. A title with no Latin letters or digits gets `profile`, then the suffix rule. Deleted ids stay in the table, so no id is ever reused.

The record type `ProfileRecord` goes in `core/workspace/records.py`. A `ProfileRepository` protocol goes in `core/workspace/repository.py`. The SQLite code goes in a new `integrations/workspace_sqlite/profiles.py`, because `repository.py` is at 498 lines. The shared "insert pipeline" and "insert revision" SQL moves from `repository.py` into a helper module both classes use, so profile creation can write the profile, its three pipelines and their revisions in one transaction.

- Alternative: a `profile_slots` table (profile, slot, pipeline). Rejected: three fixed slots fit three columns, and D1 names them on the row.
- Alternative: user profiles as YAML files. Rejected: profiles must hold graphs and revisions, which already live in SQLite.

### D2 Built-ins keep the direct path; user profiles run graphs in the request

`Engine.search`, `Engine.answer` and `Engine.ingest` ask the resolver for the collection's binding. A built-in binding (or no tag) runs today's code unchanged. A user binding runs the slot's current revision through `Engine.run_pipeline` in the request. It never enters `RunService` and writes no run record. The dispatch code lives in a new `engine_profiles.py`; `engine.py` gets one short branch per method (see D13 for the size budget).

- Alternative: run every request through graphs, built-ins included. Rejected: built-ins would pay graph admission cost on every query (see the latency task), and the parity tests show no result gain.
- Alternative: submit to `RunService`. Rejected: one consumer and a bounded queue shared with ingest jobs would make Chat wait behind ingestion.

### D3 Only writing graphs take the Engine lock

`EnginePipelines.run` takes `self._lock` only when the admitted snapshot holds an enabled node whose effect is `EffectClass.SOURCE_COMMIT`. Read-only runs skip the lock. The process-wide ingestion `write_lock` (`core/ingestion/_state.py:18`) and the per-run `RunLimits` (`core/pipelines/runner.py:43`) stay. The `active_runs` counter becomes safe across threads (a `threading.Lock` around the increment and decrement), because user-profile searches run in worker threads (D15). The lock stays an `asyncio.Lock`: only writing graphs use it, and those run on the server's event loop.

Two-run overlap is proved by a test with a catalogue holding a fake read-only operation that waits on a shared barrier; the test fails today because the second run blocks on the lock.

- Alternative: one lock per collection. Rejected: more state for no proven need; writers are rare.
- Alternative: keep one lock. Rejected: Chat on a user profile would queue behind every other query and every ingestion.

### D4 Collections follow the current revision; saves report the impact

A collection tagged with a user profile always runs the current revision of each slot. `savePipelineRevision` adds `affected_collections` when the pipeline is a slot of a profile in use. The web reads `used_by` from `GET /v1/profiles` to warn before the save. See D19 for the refusal of a breaking save.

- Alternative: pin a revision per collection. Rejected: the user asked for one simple rule, and saving is already an explicit action.

### D5 Ingest changes apply on the next ingestion

No automatic re-ingestion. The graph ingestion fingerprint already includes operations, versions, parameters and connections (`openspec/specs/pipeline-graphs/spec.md`, requirement "Graph ingestion retains source and write safeguards"), so a changed Ingest graph makes each source reprocess on its next ingestion.

- Alternative: re-ingest on save. Rejected: slow, surprising, and it needs approved roots the save request does not have.

### D6 Rename changes the title only

`PATCH /v1/profiles/{id}` changes `title` and `description`. The id never changes, because collections store it. Slot pipeline titles stay "Ingest", "Search" and "Answer".

- Alternative: allow an id change with a re-tag of collections. Rejected: the re-tag would touch every bound collection's metadata and break MCP clients that store the id.

### D7 Soft delete, refused while in use

`DELETE` sets `archived_at`. Revisions are immutable through triggers and runs hold foreign keys, so a hard delete would need a cascade through history. The delete is refused with 409 and `used_by` while a collection uses the profile. Built-ins are refused with 403. Slot pipelines of a deleted profile refuse new revisions and layout saves with 409.

A process lock in the profile service covers "check `used_by`, then archive" and "check the profile, then tag the collection", so a delete and a bind cannot cross. A collection that still names a deleted profile (for example, tagged by another process) fails with the D11-style message "profile was deleted; choose another".

- Alternative: hard delete with cascade. Rejected: it destroys run history the user may need.

### D8 Slot graphs name their base profile

Every slot graph sets `graph.profile` to the profile's `base_profile`. Admission then loads the base bundle (`admission.py:115-140`) and never loops back to the user profile. This is why `validation.py:26,106` (`OPERATIONAL_GRAPH_PROFILES`) stays built-in only. Saving a slot revision whose `graph.profile` differs from the base is refused with 400 and a plain message.

- Alternative: let `graph.profile` name a user profile. Rejected: resolution would recurse, and the user profile has no lever values of its own.

### D9 Readiness and the binding check

Readiness (shown in the list, no collection involved):

| Slot | Graph input | Graph output | Write steps |
| --- | --- | --- | --- |
| Ingest | `path` (kind `sources`) | `summary` (kind `commit_summary`) | exactly one enabled `SOURCE_COMMIT` step |
| Search | `query` (kind `query`) | `results` (kind `context`) | none enabled |
| Answer | `query` (kind `query`) | `answer` (kind `answer`) | none enabled |

Port names come from `pipeline_templates.py:102-110,128-129` and `core/ingestion/graph_adapters_catalogue.py:311-318`. Each slot must also have a saved revision and pass the draft check `Engine.validate_pipeline(document)` with no issues, except `embedding_identity_mismatch`, which depends on the collection.

The binding check (in `changeCollectionProfile` preview and confirm) repeats readiness and then runs `Engine.validate_pipeline(document, collection=target)` for each slot, so the embedding identity of the target collection is checked.

The write-step rules are stricter than the brief, which checked ports only. "No write step" in Search and Answer keeps every request graph read-only, which D3 needs. "Exactly one write step" in Ingest makes an Ingest pipeline commit its sources once.

Readiness reasons and refusal messages are plain English. Each one names the pipeline or the step and says what to fix, for example "The Search pipeline needs an output named `results`." An issue code never stands alone in a message.

- Alternative: check only port names, as the brief did. Rejected: a graph with a missing capability would pass and fail on the first Chat question, and a Search graph with a write step would take the Engine lock.
- Alternative: show issue codes as reasons. Rejected: the gallery and the Knowledge Base show these lines to users who do not know the codes.

### D10 Upgrade turns saved pipelines into profiles

Schema migration 3 only creates the table (SQL in `SCHEMA_MIGRATIONS`, which backs up the file first, `schema.py:188-237`). The data step runs in composition at web start, after the Engine exists, because it needs the standard templates (`pipeline_templates.py`), and `integrations` must not import them. The step is idempotent. It handles each pipeline that belongs to no profile, with these rules:

| Item | Rule |
| --- | --- |
| Skip | A workspace job pipeline: its layout holds the key `omrg_task`. This is the same test as `WorkspaceRuns.is_task_pipeline`. `TASK_LAYOUT_KEY` moves from `transports/api/runs_wiring.py:55` to `core/workspace/records.py`, so composition can read it; `runs_wiring.py` and `routes/graphs.py` import it from there. |
| Title | `layout.title` when it is a string that is not empty after trimming, else `pipeline.title`. The canvas wrote titles only to `layout.title` (rename bug in `studio-profiles-gallery`), so this keeps the name the user typed. |
| Base profile | The current revision's `graph.profile` when it is `documents` or `codebase`, else `documents`. Studio presets set `graph.profile` (`web/src/studio/drafts.ts:44`), so a `codebase` preset keeps its behaviour. |
| Slot | The slot whose contract the current revision matches first (Ingest, Search, Answer). The pipeline itself becomes that slot, so its revisions and runs stay linked. A pipeline with no saved revision, or a graph that matches no contract, goes in the Search slot, and the profile is not ready. |
| Other slots | The standard graphs for the base profile (`profile_templates`, D21). |
| `graph.profile` | When the current revision's `graph.profile` is not the base (for example `null`), the step saves one new revision with `graph.profile` set to the base. D8 then holds, and the next save from Studio is not refused. Earlier revisions and their runs stay unchanged. |

- Alternative: a pure SQL migration. Rejected: slug rules and template graphs need Python.
- Alternative: base `documents` for every migrated profile, as the brief said. Rejected: with D8, a migrated `codebase` preset would run with `documents` settings and give other results.
- Alternative: title from `pipeline.title` only. Rejected: titles typed on the canvas live only in `layout.title`, so the user would lose them.
- Alternative: identify job pipelines by the title prefix "Workspace job:". Rejected: a user can type that title; the layout key is reserved (`routes/graphs.py:116-117`).
- Alternative: leave `graph.profile` as it is. Rejected: D8 would refuse the first save of that pipeline with 400.

### D11 Every process reads user profiles from the workspace database

A `ProfileCatalogue` protocol goes in `core/profiles/catalogue.py`: `get_profile(profile_id)` returns a plain mapping or `None`, and `slot_document(profile_id, slot)` returns the current revision document or `None`. `compose.build_profile_resolver(..., catalogue=None)` passes it to `ProfileResolver`. `compose.build_engine(..., catalogue=None)` passes it to the Engine. Experiment contexts pass none.

A new `compose_profiles.workspace_profile_catalogue(root=None)` builds the catalogue for processes other than the web server:

- The folder is `root`, else `default_workspace()` (`~/.omrg/workspace`). `default_workspace()` moves from `transports/cli/web.py:64-66` to `core/workspace/cleanup.py` beside `WorkspaceLayout`, so `omrg web` and composition use one default. The file is `WorkspaceLayout(root).records`.
- When the file exists, the catalogue opens it with a read-only SQLite connection (`file:<path>?mode=ro` URI). It never creates, migrates or writes the file, as `read_saved_web_port` already does. A schema older than version 3 means no user profiles yet. A newer schema, or a file that is not an OMRG workspace, gives an error that names the path.
- When the file does not exist, the function returns `None`.

| Process | Where the catalogue is passed | Catalogue |
| --- | --- | --- |
| `omrg web` and its MCP endpoint | `transports/api/lifespan.py` | read-write, over the server's `--workspace` folder |
| stdio MCP server | `transports/mcp/__init__.py:121` | `workspace_profile_catalogue()` |
| CLI subcommands, including `search`, `answer`, `ingest`, `watch` and `install-login-watcher` | `compose.ensure_runtime_setup()` | `workspace_profile_catalogue()` |

The CLI commands, the login watcher catch-up and the watcher call core functions directly today. They now ask the resolver for the binding first. A built-in binding keeps today's direct call. A user binding runs through `Engine.search`, `Engine.answer` or `Engine.ingest` on the Engine that `ensure_runtime_setup()` builds. A new `compose.runtime_engine()` returns that Engine. The stdio MCP server already calls Engine methods.

Without a catalogue, a tag that is not built-in fails with: "Collection 'notes' uses the profile 'my-notes', which is not a built-in profile. User profiles live in the web workspace, and no workspace database was found at ~/.omrg/workspace/workspace.db. Start `omrg web` once with the default workspace, or change the collection's profile to 'documents' or 'codebase'."

Binding stays in the web server. `change_collection_profile` accepts a user id only on the MCP endpoint of `omrg web`. `omrg set-profile` and the stdio `change_collection_profile` accept built-ins only. With a user id they answer: "Bind user profiles in Knowledge Base > Profile, or through the MCP endpoint of `omrg web`." The D7 process lock that keeps a delete and a bind apart works inside one process only, so a bind must run where deletes run.

- Alternative: user profiles in the web server only (the brief's D11). Rejected: the user wants MCP search and answer to follow the profile, and the stdio server is the usual MCP set-up.
- Alternative: a `--workspace` option on every CLI command and on the stdio server. Deferred: the default folder covers the usual case, and the refusal names the path it read.
- Alternative: build a second Engine in each CLI command for a user binding. Rejected: it opens a second store client on the same path in one process.
- Alternative: let the CLI and the stdio server bind user profiles. Rejected: a delete in the web server and a bind in another process could cross (D7).

### D12 Empty profile

Base `documents`, three pipelines with no revision, not ready until each slot passes D9.

- Alternative: an empty profile with an empty graph revision saved. Rejected: an empty graph fails the draft check anyway, and "no saved graph" is a clearer reason.

### D13 Where the code lives

| New or changed module | Job |
| --- | --- |
| `core/profiles/catalogue.py` (new) | `ProfileCatalogue` protocol, `ProfileBinding`, slot contracts as plain data |
| `core/profiles/resolver.py` | `binding(collection)`; user tags through the catalogue; D11 message |
| `core/profiles/contract.py` | user profiles in the safety contract and in `apply_profile_change` |
| `core/workspace/{records,repository,cleanup}.py` | `ProfileRecord`, `ProfileRepository` protocol, `TASK_LAYOUT_KEY` (D10), `default_workspace()` (D11) |
| `core/pipelines/admission.py` | draft controls helper shared with admission (D24) |
| `integrations/workspace_sqlite/{schema,profiles}.py` | migration 3, SQLite profile store, catalogue reads, read-only open (D11) |
| `compose_profiles.py` (new) | `ProfileService`: list, create, duplicate, rename, delete, readiness, `used_by`, upgrade step, built-in titles, `standard_graphs`; `workspace_profile_catalogue()` |
| `compose.py` | `ensure_runtime_setup()` passes the catalogue; `runtime_engine()` |
| `engine_profiles.py` (new) | request values to node params, sync runner, result mapping |
| `compose_pipelines.py` | D3 lock rule; `profile_templates(engine, base_profile)`; draft controls in `validate` |
| `transports/api/routes/profiles.py` (new) | `/v1/profiles` routes |
| `transports/api/routes/graphs.py` | slot save rules (D19, D20); draft `nodes` (D24) |
| `transports/cli/{search,answer,ingest,install_login_watcher,profile}.py`, `daemon/watcher.py`, `transports/mcp/__init__.py` | D11 callers |

`engine.py` must stay under 500 lines. The three dispatch branches add about 12 lines, so the resource release body of `close()` (`engine.py:383-426`) moves into a new helper module `engine_lifecycle.py`. `omrg.compose_profiles`, `omrg.engine_profiles` and `omrg.engine_lifecycle` join the forbidden list of `core-never-imports-top-level-modules`.

### D14 Request values on the graph path

A value the caller sets replaces the matching step setting. `engine_profiles.apply_request` copies the slot document, sets `graph.collection` to the request collection, and writes each non-`None` value as a node param on every node whose operation declares that param: `top_k`, `similarity_threshold`, `rerank`, `fetch_k`, `metadata_filter` on `retrieve.prepare_query`; `expand_window` on `context.assemble`; `include_diagnostics` on `answer.synthesise`; `chunk_size` and `chunk_overlap` on the nodes whose `lever_params` map to `chunking.chunk_size` and `chunking.chunk_overlap`. `hybrid` and `technical_fraction` have no step setting; the graph's wiring decides, as the pipeline-graphs spec already says for profile hybrid. With `include_diagnostics`, the result lists the request values that had no effect.

MCP `search_documents` stops pre-filling `top_k`, `similarity_threshold` and `hybrid` (`search.py:84-89`) and passes the caller's values through. `Engine.search` already resolves `None` from the profile, so built-in results do not change; the existing MCP search tests prove this. Without the fix, the base profile's defaults would overwrite every user graph's settings.

- Alternative: request values as graph overrides. Rejected: node params win over graph overrides, so a request could not lower a step's own `top_k`.

### D15 `Engine.search` stays synchronous

`Engine.search` is synchronous and transports call it in a worker thread (`routes/documents.py:145`, `mcp/search.py:94`). For a user profile it runs the graph with `asyncio.run` on a private event loop in the calling thread. When that thread already runs an event loop (a notebook), it runs the private loop in a short-lived helper thread and waits. Graph adapters move blocking work off the loop with `asyncio.to_thread` (`core/retrieval/graph_adapters.py:140,222`), so a private loop works. Read-only graphs never touch the Engine `asyncio.Lock` (D3), so no lock crosses event loops.

- Alternative: add `Engine.search_async`. Rejected for now: every transport would change, and the public `search()` contract stays the same with this design.

### D16 Results keep today's shapes

| Operation | Graph output | Mapped result |
| --- | --- | --- |
| search | `results` (`ContextBundle`) | `public_rows()`; with diagnostics, the full rows |
| answer | `answer` (answer dict) | returned as it is |
| ingest | one `summary` per unit | `status`, `collection`, `files_indexed`, `files_skipped_unchanged`, `chunks_created`, `chunks_removed`, `file_details`, `metadata_degraded`, `total_seconds`; `timings` sums per-file timings; `peak_rss_bytes` is `null` |

A graph validation failure raises `PipelineValidationError` (a `ValueError`), which the web routes already turn into 400. A failed run raises a `ProfileRunError(RuntimeError)` that names the failing step; the routes already turn other exceptions into 500 (search) or the answer failure shape (answer). For ingestion, `progress_callback(phase, current, total)` is called once per finished unit.

### D17 User-profile answers use the server model

`Engine.answer` refuses `client_completion` and `rows` for a user profile with a `ValueError` that says the profile's Answer pipeline does its own retrieval and uses the server model. MCP `answer_documents` and its MRTR resolvers check the binding first and choose the server source for a user profile, so no sampling request goes to the client. The reason: MCP client sampling and pre-fetched rows cannot pass into a pipeline run, because the runner takes no per-run resource override and `answer.max_rounds` is not a graph lever.

- Alternative: pass the client completion into the run as the `answer_llm` resource, with a per-run round cap. Deferred: it needs a per-run resource override in the runner. A later change can add it.

### D18 `used_by` comes from the store

`used_by` lists collections whose stored `profile` tag equals the id, read with one `get_collection_metadata` per collection from the Engine's store. Untagged collections that inherit `RAG_PROFILE` are not listed.

### D19 Saves and confirmations protect bound collections

`savePipelineRevision` on a slot of a profile in use runs the D9 readiness check on the new graph. On failure it answers 409 with the reasons and saves nothing. The profile-change confirmation state (`routes/admin.py:181-187`) adds the profile's `archived_at` and its three current revision ids, so a delete or a slot save between preview and confirm makes the token stale (409).

- Alternative: allow the save and fail at request time, as the brief's D4 allowed. Rejected: Chat would break for every bound collection with no warning.

### D20 `createPipeline` is withdrawn

`POST /v1/pipelines` answers 410 Gone: "Create a profile instead: POST /v1/profiles." The OpenAPI operation stays with only the 410 response and `deprecated: true`, so old clients get a clear answer. `GET /v1/pipelines/{id}` adds `profile_slot: {profile_id, slot} | null`.

### D21 Server-side duplicates inherit levers

`profile_templates(engine, base_profile)` shapes the templates with the base profile's `retrieval.hybrid_enabled` and the Engine's reranker capability, as `pipeline_templates()` does today (`compose_pipelines.py:198-222`), and sets `graph.profile` to the base. It writes no explicit node params. The web preset today writes `enabled` on the rerank node (`web/src/studio/drafts.ts:43-50`). Inheriting means a duplicate of `documents` behaves the same as `documents`, including environment overrides. The web preset code is removed by `studio-profiles-gallery`.

### D22 Built-in-only checks: change or keep

| Location | Decision |
| --- | --- |
| `routes/admin.py:63` (`Literal["documents","codebase"]`) | Change to a string with the id pattern |
| `core/profiles/contract.py:74` (old settings for built-ins only) | Change: a user tag loads its base settings through the catalogue |
| `core/profiles/contract.py:212` (apply accepts built-ins only) | Change: also accept a ready user profile from the catalogue |
| `core/profiles/resolver.py:48` (`OPERATIONAL_PROFILES`) | Keep as the built-in set; user ids come from the catalogue |
| `core/profiles/resolver.py:395` (`_validate_profile`) | Change: accept catalogue ids; list ready user profiles; D11 message |
| `core/pipelines/validation.py:26,106` | Keep: `graph.profile` stays built-in (D8) |
| `config/sources.py:132` (`hybrid` default profile) | Keep: the server default stays built-in |
| `compose_answer.py:133` (startup check of bundle verify providers) | Keep: user profiles add no bundle values |
| `transports/api/openapi.yaml:3990` (enum) | Change to the id pattern |
| `transports/mcp/profile.py:38,67` | Change: accept ids the Engine's catalogue knows on the web server; refuse a user id with the D11 binding message on the stdio server |
| `transports/cli/profile.py:62` | Change: refuse a user id with the D11 binding message; built-ins only |
| `web/src/api/documents.ts:203`, `web/src/studio/drafts.ts:9`, `web/src/studio/PipelineBar.tsx` | Out of scope: `studio-profiles-gallery` |

### D23 Reading a built-in returns its standard graphs

`GET /v1/profiles/{profile_id}` of a built-in adds `standard_graphs: {ingest, search, answer}`. Each value is the graph document that `POST /v1/profiles` with that built-in as `source` copies into a duplicate, from `profile_templates(engine, profile_id)` (D21). The graphs follow the built-in's own settings, not only the host settings, so `codebase` shows its sparse retrieval and fusion steps whatever the host default is. For a user profile the field is `null`. List items of `GET /v1/profiles` do not carry it. `studio-profiles-gallery` reads it to open a built-in read-only.

- Alternative: give each built-in three read-only slot pipelines. Rejected: built-ins have no workspace rows (`slots` are `null`), and rows would need a migration and a refresh after every upgrade.
- Alternative: let the web read `GET /v1/pipeline-templates`. Rejected: those graphs follow the host settings, not the built-in (`compose_pipelines.py:198-222`).
- Alternative: carry `standard_graphs` on list items too. Rejected: the gallery needs no graphs, and each list call would carry six graph documents.

### D24 The draft check returns effective values

`validatePipeline` without `inputs` adds `nodes: [{node_id, controls}]`, with the same `controls` shape as the admission check. A new helper in `core/pipelines/admission.py` builds them from the preflight report. It resolves collections as admission does: the node's collection parameter, else `graph.collection`, else the request `collection`, else the host default collection. It loads `graph.profile` when it names a built-in, else the collection's profile, and applies graph overrides and node parameters. The controls loop in `_Admission.node_snapshot` moves into this helper, and admission calls it too, so draft and admitted values cannot drift.

A draft with issues still answers 422. The error body adds `nodes` with the controls of each node whose parameters passed validation and whose collection profile resolved, because a half-built graph is the normal state while the user edits. A node whose profile does not resolve gets no controls; the existing profile issue says why. No node runs, and no model call or store write happens.

This change owns the requirement because it already changes `routes/graphs.py` and adds requirements to `pipeline-graphs`. `clarify-canvas-steps` stays web only and reads the field.

- Alternative: return values only for a valid draft. Rejected: cards would show no values until the graph is complete.
- Alternative: an ADDED requirement in `clarify-canvas-steps`. Rejected: that change is web only, and the endpoint is backend work with backend tests.
- Alternative: compute values in the web from the catalogue. Rejected: the web cannot see profile or environment values.

### D25 Release and order

This change lands after `organise-backend-folders`, so its paths name `transports/api/routes/`. It ships in the same release as `studio-profiles-gallery`: `createPipeline` answers 410, and the old Studio gallery depends on it. Do not cut a release between the two merges.

### Latency check

A `slow`-marked test runs the 15 recorded retrieval cases of `tests/unit/test_pipeline_templates.py` through a built-in collection (`Engine.search`) and through a duplicate user profile (graph path), 20 times each. It asserts equal rows and prints the median and 95th-percentile time per query for each path and the difference. The numbers go into ADR-080 and `docs/guides/pipelines.md`. The test asserts no time limit, so a busy machine cannot fail it. If the median overhead is above 50 ms, the follow-up is a cache of parsed definitions keyed by revision id.

## Risks / Trade-offs

- [Graph admission on every user-profile request adds latency] → Measure (latency task); cache parsed definitions by revision id if the median overhead is above 50 ms.
- [`GET /v1/profiles` runs three draft checks per profile and reads every collection's metadata] → Fine for a local workspace with tens of profiles; cache readiness by the three current revision ids if a test shows the list above 200 ms.
- [Read-only graphs now overlap, so model calls from several runs can overlap] → Built-in searches already overlap in the thread pool today; the reranker cache and embedder are already used this way.
- [Private event loops in worker threads] → Covered by tests that call user-profile search from a worker thread and from a thread with a running loop.
- [`createPipeline` 410 breaks the current Studio "New pipeline" card until `studio-profiles-gallery` lands] → Ship both changes in one release (D25).
- [The CLI, the stdio MCP server and the watcher read the workspace database while the web server writes it] → They open it read-only and never migrate it. SQLite makes a reader wait for a writer up to the connection timeout.
- [A web server started with `--workspace` in another folder is not found by other processes] → The refusal names the path it read (D11).
- [The draft check now resolves profiles and builds controls on each call] → It does the admission work without run inputs and makes no model call. Studio calls it with a delay after edits (`clarify-canvas-steps`).
- [Upgrade step runs at each web start] → It touches only pipelines in no profile, so a second start does nothing; a test proves it.

## Migration Plan

1. Before apply: `organise-backend-folders` has landed.
2. Deploy: the first `omrg web` start migrates the workspace database to version 3. `migrate()` backs up the file first (`schema.py:218`) and rolls back on failure.
3. After the Engine is built, the upgrade step turns each saved Studio pipeline into a user profile (D10). No collection tag changes.
4. Rollback: stop the server and restore the `workspace.db.v2-to-v3.<time>.bak` file. Collections stay valid, because no collection was tagged with a user profile during the upgrade. A collection tagged with a user profile after the upgrade must be set back to `documents` or `codebase` before rollback.

## Open Questions

None. The questions of the earlier draft are decisions now: D9 (stricter readiness and plain messages), D10 (base profile, title, job pipelines), D11 (every process reads the workspace), D17 (server model for user-profile answers) and D19 (refuse breaking saves).
