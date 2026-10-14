# HTTP document endpoints and destructive actions (tasks 6.4, 6.5)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted working tree.
Design D7, D8. Specs `local-web-workspace` and `transport-separation`.

## Files

New runtime modules in `src/omrg/transports/api/`:

| File | Lines | Job |
|---|---|---|
| `engine_access.py` | 111 | Runtime and scope dependencies, `admitted()`, `require_session(scope)`, `engine_store()`, `engine_resolver()`. |
| `routes_documents.py` | 172 | Collections, sources, search, answer. |
| `routes_jobs.py` | 239 | Ingestion and codebase-map jobs, job polling, `JobBook`. |
| `routes_inspect.py` | 103 | Stored-chunk inspection with neighbours. |
| `confirmations.py` | 204 | `observe()`, `ConfirmationBook`, `PROCESS_LOCAL_WARNING`. |
| `routes_admin.py` | 223 | Preview-bound deletion and profile change. |

Changed: `app.py` (registration of the four routers in `API_ROUTERS` only).

Tests: `tests/unit/test_web_documents.py`, `tests/unit/test_web_documents_jobs.py`, `tests/unit/test_web_destructive.py` (66 tests), helper `tests/unit/test_web_documents_support.py`.

## Routes

Paths are relative to `/v1`. "Session" means the browser session cookie. Bearer credentials never pass a session-only route.

| Method | Path | Scope | Operation id | In `openapi.yaml` |
|---|---|---|---|---|
| GET | `/collections` | `read` | `listCollections` | yes |
| GET | `/collections/{collection}/documents` | `read` | `listDocuments` | yes |
| POST | `/collections/{collection}/search` | `read` | `searchCollection` | yes |
| POST | `/collections/{collection}/answer` | `read` | `answerCollection` | yes |
| POST | `/ingestions` | `files` (session only) | `ingestPath` | yes |
| POST | `/codebase-maps` | `files` (session only) | `generateCodebaseMap` | yes |
| GET | `/jobs/{jobId}` | `read` | `getJobStatus` | yes |
| GET | `/collections/{collection}/chunks/{chunk_id}` | `read` | `getChunk` | **new** |
| DELETE | `/collections/{collection}/documents` | `run` + session only | `deleteDocuments` | yes, extended |
| PATCH | `/collections/{collection}/profile` | `run` + session only | `changeCollectionProfile` | yes, extended |

## Behaviour

### Documents (6.4)

- Listing calls the existing core `list_collections(store)` and `list_documents(collection, store)` with the Engine's store. Orphan status stays tri-state and machine-local. A relative stored path gives `null`.
- Search calls `Engine.search` in the thread pool. Omitted `top_k`, `similarity_threshold`, `rerank`, `hybrid` and `metadata_filter` go to the Engine as `None`, so the collection profile supplies them. Diagnostics-only keys appear only with `diagnostics: true`.
- Answer calls `Engine.answer`. Retrieval and generation failures stay inside the answer result (`failure_stage`). An unexpected Engine exception gives the MCP error shape (`status: error`, `failure_stage: null`, `completion_source: none`).
- Request bodies forbid unknown keys. Bounds follow the contract (`top_k >= 1`, threshold 0 to 1, answer `top_k <= 100`, `expand_window <= 10`, query up to 4096 characters). Violations give 400 with `error_type: validation`.
- A `ValueError` from the Engine (for example an invalid profile tag) gives 400 `validation`. Other search failures give 500 with the exception type only; `error_type` is `retrieval` with a metadata filter, else `internal`.
- Ingestion and codebase maps return 202 and a `Job`. The path must be absolute and inside an approved root (`RootGrants.check`); otherwise 403 before any work. Uploaded files are ingested by their managed-root path (`GET /v1/roots` managed path, then `<upload id>/<name>`). No new request field is needed.
- The codebase-map job passes `Engine.resolve_settings()` and the Engine's store to `get_codebase_map_text` explicitly. It never resolves process defaults.
- Chunk inspection reads the stored chunk by `chunk_id` with `iter_filtered_documents` and gets neighbours with the existing `lineage.neighbours`. `window` is 0 to 5 (default 1). It never opens the original file, so a source outside the roots stays inspectable. Text is a JSON string with `text_format: "plain"`. API responses keep `nosniff` and the restrictive CSP. Internal row ids are not returned.

### Destructive actions (6.5)

- A preview (`dry_run: true`, or `confirm: false` for a profile) mutates nothing. It returns the existing core preview (`preview_delete` or `generate_safety_contract`) plus `confirmation`: `token`, `expires_at`, `expires_in`, `validity` and `warning`.
- The token is single use. It binds the action, the collection, the canonical selector and the observed validity token. It expires after 300 seconds.
- Validity token: `store.get_data_version(collection)` when not `None` (`validity: durable`). Otherwise `local:<generation>:<row count>` (`validity: process_local`) with `PROCESS_LOCAL_WARNING`. The profile action also binds the current profile tag, because a metadata update does not change the generation counter.
- Confirmation: same selector plus `confirmation_token`. No token gives 428. Unknown, used, expired, altered or stale tokens give 409 with an instruction to preview again. Every rejection spends the token. The data stays unchanged.
- A valid confirmation calls the existing writers (`remove_document`, `remove_by_metadata`, `remove_collection`) or `apply_profile_change` with the Engine's store. A mode table selects the writer; there is no `if/elif` chain.
- After a confirmed profile change, `Engine.resolve_settings(collection)` follows the new profile. The chunk count stays the same.

## Test-first record

Environment: WT `.venv`, `PYTHONPATH=src`, `PDF_READER=pypdf`, `-p no:cacheprovider`.

1. Before implementation, `test_web_destructive.py`: **1 error during collection** (`No module named 'omrg.transports.api.confirmations'`).
2. Before implementation, `test_web_documents.py` and `test_web_documents_jobs.py`: **33 failed, 1 passed**. The passing test is the cross-origin check that the existing middleware already enforces.
3. First implementation run: failures from `require_session` (postponed annotation hid the local dependency, so FastAPI read `principal` as a query value), from test seeds that did not use the ingestion identity rule, and from the `oneOf` contract defect below. Fixed the dependency with a default value, fixed the seeder to use `build_source_id(canonical_source_path(path))`, and added a `variant` option to the schema check.
4. Final: **66 passed**.

## Mutation checks

Script: `scratchpad/h64/mutate.py`. Each check edits one line, runs the three new test files, then restores the line.

| Id | Change | Result |
|---|---|---|
| M1 | Stale validity token accepted | 4 failed |
| M2 | Altered selector accepted | 8 failed |
| M3 | Expiry ignored | 2 failed |
| M4 | Weaker guarantee not disclosed | 1 failed |
| M5 | Confirmation skips the token check | 16 failed |
| M6 | Profile tag not bound | 1 failed |
| M7 | Bearer may run destructive actions | 2 failed |
| M8 | Ingestion skips root grants | 5 failed |
| M9 | Search sends a fixed `top_k` | 1 failed |
| M10 | Neighbours dropped | 1 failed |
| M11 | Search runs on the event loop | 1 failed |
| M12 | Preview also deletes | 16 failed |

## Related suites and static checks

- Command: the three new files plus `tests/unit/test_web_launch.py tests/unit/test_web_security.py tests/unit/test_web_files.py tests/test_file_size_ceiling.py tests/test_pipeline_import_boundaries.py tests/test_openapi_conformance.py tests/test_no_global_settings_reads.py tests/test_contract_coverage.py`. Result: **291 passed**. This includes `test_every_protected_route_declares_a_scope` over the new routes.
- `lint-imports`: **15 kept, 0 broken**.
- `ruff format` and `ruff check` on all new and changed files: clean.
- Branch coverage (new tests only): `routes_documents.py` 99%, `routes_admin.py` 95%, `confirmations.py` 94%, `routes_inspect.py` 93%, `routes_jobs.py` 93%, `engine_access.py` 86%.

## Contract work for task 6.7

1. **Defect: `changeCollectionProfile` 200 `oneOf`.** `ProfilePreview` and `ProfileChangeResult` declare no required keys, so every object matches both branches and `oneOf` validation always fails. Add `required: [status, contract, confirm_required]` and `required: [status, collection, profile, chunk_count_unchanged]`.
2. **Drift: profile preview contract keys.** The schema declares `contract.target_profile`; core returns `new_profile`. Rename the schema field to `new_profile` (MCP and HTTP both return the core shape).
3. **New fields:** `DeleteRequest.confirmation_token`, `ProfileChangeRequest.confirmation_token`, `DeleteResult.dry_run`, `DeleteResult.confirmation`, `ProfilePreview.confirmation`, and a `Confirmation` schema (`token`, `expires_at`, `expires_in`, `validity` enum `durable|process_local`, `warning` string or null). The support module lists the pending keys in `PENDING_CONTRACT_KEYS`.
4. **Changed semantics:** `deleteDocuments` without `dry_run` needs `confirmation_token` (428 without it, 409 when stale). `changeCollectionProfile` with `confirm: true` needs `confirmation_token`. `IngestRequest.path` and `CodebaseMapRequest.path` must be absolute and inside an approved root.
5. **Status codes to declare:** 403 (scope, grants, session-only), 404 (`getJobStatus`, `getChunk`), 409 and 428 (destructive), 429 (job queue full), 501 (`getChunk` on a store without filtered reads), 503 (start or shutdown).
6. **New operation `getChunk`:** response keys `status`, `collection`, `text_format`, `chunk`, `previous`, `next`; each chunk view has `chunk_id`, `source_id`, `source_version`, `source_chunk_index`, `source_chunk_count`, `source`, `page_label`, `text`, `metadata`. Query `window` 0 to 5, default 1.
7. **Security:** replace the JWT `bearerAuth` with the session cookie and the `omrg_bt_` bearer, and state the scope per operation from the route table.

## Deviations and open points

1. **Engine accessors.** `Engine` has no public store or profile-resolver accessor. `engine_access.engine_store()` and `engine_resolver()` prefer `engine.store` and `engine.profile_resolver`, and fall back to `engine._store` and `engine._resolver()`. Action for the `engine.py` owner: add a read-only `Engine.store` and `Engine.profile_resolver` (and update the method-set pin in `tests/test_engine.py`). Then delete the fallback.
2. **Job service placeholder.** `RunService` runs graph revisions and is not composed for plain ingestion. `JobBook` (on `app.state.omrg_jobs`) runs one job at a time, keeps at most 16 open and 256 finished jobs in memory, and loses them on restart. A running job holds admission, so shutdown waits for it to finish; there is no cooperative cancellation. Task 6.6 should move ingestion and codebase maps onto the shared run service and keep the `Job` response shape.
3. **Destructive scope.** No session-only "manage" scope exists, so destructive routes use `require_session("run")`. Recommendation for the `security.py` owner: add a session-only `manage` scope to `SESSION_SCOPES` and switch these routes to it.
4. **Check-then-act window.** The validity token is observed, then the writer runs. A write by another process in that short window is not detected. The writers still take `write_lock` for the delete itself.
5. **Legacy rows.** Rows without `chunk_id` cannot be inspected by id.
6. **Error detail.** Search 500 and answer Engine failures return the exception type only. Ingestion job errors return the type and `redact()`ed text (first 300 characters); configured provider secrets are not in that redaction set.

## Not run

- Full test suite and `local_ci.sh` (not permitted for this agent).
- A real `compose.build_engine()` start and a real ingestion. Tests use a real LanceDB store, a mock embedder and a fake answer model.
- Chroma: the extra is not installed in the WT venv. `ProcessLocalStore` (LanceDB with no durable version) covers the process-local path.
