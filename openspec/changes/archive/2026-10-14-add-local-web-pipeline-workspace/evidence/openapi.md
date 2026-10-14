# OpenAPI contract and runtime conformance (task 6.7)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted working tree.
Design D8. Specs `transport-separation` (Versioned OpenAPI 3.1 contract for the REST runtime) and `local-web-workspace`.

## Files

| File | Change |
|---|---|
| `src/omrg/transports/api/openapi.yaml` | Rewritten for the runtime. Version `2.0.0`. 38 operations. |
| `src/omrg/transports/api/README.md` | Replaced the "contract first, no runtime" text. Describes `omrg web`, access, scopes, errors, destructive actions, jobs and graph runs, SSE replay, checks and guides. |
| `tests/unit/test_web_openapi_conformance.py` | New. Static runtime-versus-contract checks (21 tests). |
| `tests/unit/test_web_openapi_conformance_support.py` | New. Route inspection, scope reading, `ContractChecker`, `FAMILIES`. No tests. |
| `tests/unit/test_web_openapi_conformance_documents.py` | New. Response flows: foundation, jobs, documents, destructive actions, 503. |
| `tests/unit/test_web_openapi_conformance_runs.py` | New. Response flows: graphs, runs, events (JSON and SSE), cancel, retry, 429, cleanup, restart. |
| `tests/unit/test_web_documents_support.py` | `assert_conforms` now fails on an undeclared status and always runs plain `oneOf` validation. `PENDING_CONTRACT_KEYS` entries are empty. |

No route module changed. The runtime agreed with the reviewed contract where the contract was right. Every difference was a contract defect.

## Contract changes

- **Version.** `info.version` `1.0.0` to `2.0.0`. The security schemes and a field name changed, so the change is breaking. The description no longer says that no runtime exists.
- **Server.** `http://127.0.0.1:{port}/v1`.
- **Security.** The JWT `bearerAuth` scheme is gone. New schemes: `sessionCookie` (`apiKey`, cookie `omrg_session_<port>`, HttpOnly, SameSite=Strict) and `bearerToken` (`http` bearer, format `omrg_bt_<id>.<secret>`). There is no global `security`. Each operation states `security` and `x-omrg-scopes`:
  - public: `security: []`, `x-omrg-scopes: []` (`getHealth`, `createSession` only);
  - session only: `[{sessionCookie: [scope]}]`;
  - otherwise: `[{sessionCookie: [scope]}, {bearerToken: [scope]}]`.
  The top-level `x-omrg-scope-catalogue` lists the seven scopes and marks `files`, `plugins`, `credentials` and `manage` as session only.
- **Error envelope.** `Error` keeps `status`, `message` and `error_type` (same enum). It adds optional `issues` (`ValidationIssue`: `code`, `message`, `node_id`, `port`, `edge`, `lever`) for 422. `additionalProperties: false`.
- **Shared responses.** `BadRequest` (400), `BootstrapRejected` (401 without challenge), `Unauthorized` (401 with `WWW-Authenticate`), `Forbidden` (403), `NotFound`, `Conflict` (409), `PayloadTooLarge` (413), `UnsupportedMediaType` (415), `ValidationFailed` (422), `PreconditionRequired` (428), `TooManyRequests` (429), `InternalError` (500), `NotImplemented` (501), `ServiceUnavailable` (503).
- **Reported defects fixed (http-documents.md):**
  1. `ProfilePreview.required` = `[status, contract, confirm_required]`; `ProfileChangeResult.required` = `[status, collection, profile, chunk_count_unchanged]`. `status` enums `[preview]` and `[ok]` make the `oneOf` branches exclusive.
  2. `contract.target_profile` renamed to `new_profile`. All six contract keys are required.
  3. `confirmation_token` on `DeleteRequest` and `ProfileChangeRequest`; `dry_run` and `confirmation` on `DeleteResult`; `confirmation` on `ProfilePreview`; new `Confirmation` schema (`token`, `expires_at`, `expires_in`, `validity` `durable|process_local`, `warning` nullable).
  4. 409 and 428 on both destructive operations. 403, 404, 429, 501 and 503 where the runtime returns them.
  5. New `getChunk` with `window` 0..5 (default 1) and `ChunkInspection`/`ChunkView`.
- **New operations.** `getHealth`, `createSession`, `getSession`, `issueCredential`, `listCredentials`, `revokeCredential`, `listRoots`, `preflightUpload`, `uploadFile` (raw `application/octet-stream` body, `X-Upload-Name` header), `listPipelineOperations`, `createPipeline`, `listPipelines`, `getPipeline`, `savePipelineLayout`, `savePipelineRevision` (201 new, 200 dedupe), `listPipelineRevisions`, `getPipelineRevision`, `validatePipeline` (`oneOf` draft or admission view), `submitRun` (202), `listRuns`, `getRun`, `getRunResult`, `cancelRun`, `retryRun` (202), `listRunEvents`, `streamRunEvents` (`text/event-stream`, `x-omrg-sse-events` maps event names to `RunEventRecord`, `StreamEnd`, `StreamClosing`), `previewWorkspaceCleanup`, `applyWorkspaceCleanup`.
- **Request schemas follow the runtime models.** `additionalProperties: false` wherever the model forbids unknown keys. `SearchRequest.top_k` and `similarity_threshold` are now nullable (the runtime accepts `null`; they stay profile-resolved with no default). `IngestRequest` and `CodebaseMapRequest` state the absolute, approved-root path rule and their length limits.
- **Response schemas are closed.** Records and envelopes use `additionalProperties: false`, so a new runtime field fails the response flows. Free-form members (`metadata`, `settings`, `layout`, `document`, `summary`, graph parameters) stay open.
- `Job` requires all six keys (the runtime always sends them). `CollectionInfo` requires its three keys.
- Kept from the reviewed document: `SearchRequest` to `DocumentInfo` (search, result, answer and listing schemas) unchanged apart from the two nullable fixes and `additionalProperties: false` on the two request schemas. `getJobStatus` keeps the path name `{jobId}`.

## Conformance tests

`test_web_openapi_conformance.py` reads the runtime from a real `create_app()` application:

| Test | Checks |
|---|---|
| `test_contract_is_valid_openapi_31_and_versioned` | `openapi-spec-validator`, 3.1, major version >= 2, two security schemes |
| `test_every_runtime_route_is_declared` / `test_every_declared_operation_is_implemented` | Route and method parity both ways. A route with `include_in_schema=False` is internal and exempt. |
| `test_response_flows_cover_every_operation` | The `FAMILIES` sets of the flow tests cover every contract operation |
| `test_operation_ids_agree_where_the_runtime_names_them` | Runtime `operation_id` equals contract `operationId`; ids unique |
| `test_scope_catalogue_matches_the_access_policy` | Catalogue equals `SESSION_SCOPES`; session-only flag equals "not in `BEARER_SCOPES`" |
| `test_declared_scopes_match_route_dependencies` | `x-omrg-scopes` and `security` equal the scope and session-only flag that the route dependencies enforce |
| `test_public_operations_are_only_health_and_bootstrap` | Only two routes have no scope dependency |
| `test_access_and_failure_statuses_are_declared` | 400, 403, 500 everywhere; 401 for scoped routes; 503 for routes that need the runtime |
| `test_request_bodies_match_runtime_models` | Per field: presence both ways, required, default rule (concrete default equal, `None` default declares none, factory default equal), nullability, bounds, enum, unknown-key policy; recursive for nested models |
| `test_parameters_match_runtime` | Query names, required, defaults and bounds; path parameter count; runtime headers declared |
| 202 / protection / destructive / profile tests | Job and run 202 resources with ids, 429, read-scoped status/event routes, SSE media type, `manage` session-only operations with 409/428, exclusive profile branches |
| `test_unknown_api_path_never_serves_html` | With a built `index.html`, unknown `/v1` paths (GET, POST, wrong method) return the JSON envelope; a frontend path returns HTML |

The flow tests send real requests and pass each response to `ContractChecker.check()`. It finds the contract operation from the request, fails on an undeclared status or media type, checks declared headers, validates JSON with `jsonschema` Draft 2020-12, and validates each SSE frame. Job semantics covered: 202 with a UUID job id, polling from `queued`/`running` to `completed` and `failed`, 202 run with `queued`, cancel (`cancelled`, `cancelling`), retry (`origin: retry`, `source_run_id`), 429 on a full queue, and after a restart a graph run reads `interrupted` and a job reads `failed`, with nothing repeated until an explicit retry.

## Test-first record

Environment: WT `.venv`, `PYTHONPATH=src`, `PDF_READER=pypdf`, `-p no:cacheprovider`.

1. New tests and the tightened helper against the original contract (`openapi.yaml` 1.0.0 put back temporarily): `pytest tests/unit/test_web_openapi_conformance*.py tests/unit/test_web_documents.py tests/unit/test_web_destructive.py tests/unit/test_web_documents_jobs.py`. Result: **33 failed, 62 passed**. FAIL expected.
2. First runs against the new contract found two contract errors. `POST /v1/session` returns 401 without `WWW-Authenticate` (new `BootstrapRejected` response). The static body test first crashed on pydantic `$defs` links (test fix).
3. Final: `pytest tests/unit/test_web_*.py tests/test_openapi_conformance.py tests/test_file_size_ceiling.py`: **253 passed**. Conformance files alone: **28 passed** in 1.6 s.

## Mutation checks

Script: `scratchpad/mutate_oas.py`. Each check changes one thing, runs the three conformance files, then restores the file.

| Id | Change | Result |
|---|---|---|
| M1 | Drop `GET /roots` from the contract | 4 failed (route parity, coverage, two flows) |
| M2 | Contract scope of `listRoots` `files` to `read` with bearer | 1 failed (scope drift) |
| M3 | Runtime: graph routes require `run` instead of `graph` | 1 failed (scope drift) |
| M4 | Contract default `origin` `submit` to `repeat` | 1 failed (body drift) |
| M5 | Runtime: new `SubmitBody.priority` field | 1 failed (body drift, field named) |
| M6 | Contract drops 428 from `deleteDocuments` | 2 failed |
| M7 | Contract `Job` drops `error` | 2 failed |
| M8 | Contract `Error` drops `issues` | 2 failed (422 flows) |
| M9 | Contract lets a bearer delete documents | 2 failed |
| M10 | Contract `listRuns.limit` default 100 to 50 | 1 failed (parameter drift) |
| M11 | Contract `RunEventRecord` drops `unit_id` | 1 failed (event flow) |

After the script, `routes_graphs.py`, `routes_runs.py` and `openapi.yaml` were checked as restored.

## Static checks

- `openapi-spec-validator` (the `local_ci.sh` command): valid.
- `ruff format` and `ruff check` on the new and changed tests: clean.
- `lint-imports`: **17 kept, 0 broken**.
- Largest new file: `test_web_openapi_conformance.py`, 432 lines.

## Deviations and open points

1. **Request validation stays 400.** The runtime maps framework validation (`RequestValidationError`) to 400 `validation`, as the reviewed contract did. Only core graph and cleanup-selector validation gives 422 with `issues`. The contract states both.
2. **`{jobId}` path name kept.** The runtime path parameter is `job_id`. Existing tests use the contract template `/jobs/{jobId}`, so the reviewed name stays. The parameter test compares path parameter counts, not names.
3. **Foundation routes have no runtime `operation_id`.** `routes.py` uses FastAPI default names, and the runtime serves no generated document (`openapi_url=None`). The contract names them (`getHealth` and so on). The id test checks only routes that set one. Optional: add `operation_id=` to the nine routes in `routes.py`.
4. **Vacuous scope test (action for the `test_web_security.py` owner).** With FastAPI 0.143, `app.routes` holds `_IncludedRouter` objects whose `path` is empty. `test_every_protected_route_declares_a_scope` therefore checks no route and always passes. Fix: iterate `fastapi.routing.iter_route_contexts(app.routes)` and read `context.original_route`, as `iter_api_routes()` in the support module does. The new scope tests already cover the same rule.
5. **`plugins` scope has no route yet.** It is in the scope catalogue only. The plugin routes (tasks 8.x) must add their operations, or the parity test fails.
6. **Five em dashes remain** inside the reviewed search and answer descriptions that were kept unchanged.
7. **Not exercised:** 501 from `getChunk` (needs a store without filtered reads) and 400 for credentials in run inputs. Both are declared.

## Not run

- Full test suite and `local_ci.sh` (not permitted for this agent).
- A real `compose.build_engine()` start and a real browser.
