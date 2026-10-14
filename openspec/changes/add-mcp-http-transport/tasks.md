# Tasks

Rules for every task: write the test first and confirm it fails against the old code; keep every file under 500 lines; MCP handlers never raise (gotcha #1) and keep `ToolAnnotations` (gotcha #7); CLI output goes to stderr (gotcha #5).

## 1. MCP server factory and lifespan context

- [x] 1.1 Add `transports/mcp/context.py` with the frozen `McpContext` (engine, path policy, admission) and `PathPolicy` (`allow_all()`, `from_grants(grants)`) per design D2; unit-test that `from_grants` refuses a path outside the roots and a symlink that resolves outside them.
- [x] 1.2 Add `omrg/engine_answer.py` with `ClientCompletion(complete, source, max_rounds)` and the answer composition moved out of `engine.py` (server-model seam, verifier build, client-completion selection, round cap) per design D8; `Engine.answer` gains keyword-only `client_completion` and `rows` and delegates; re-export `ClientCompletion` from `omrg.engine`. Test first: a client completion reports its source and still runs server-side verification; `max_rounds` caps synthesis rounds; `rows` causes no second retrieval; no `client_completion` keeps today's result byte for byte.
- [x] 1.3 Add `transports/mcp/server.py` with `create_mcp_server(lifespan)` and `register_tools(server)`; convert every tool module, including `answer_mrtr.py`, to plain handlers registered from `register_tools`, each taking `ctx: Context`; remove the module-level `mcp`, `_get_reranker` and `_get_profile_resolver`; keep the package-root handler re-exports.
- [x] 1.4 Rewrite each handler on `McpContext` per the table in design D2. The answer tool picks its source with `select_completion_source`, builds `ClientCompletion` with `max_rounds = min(block.max_rounds, _MAX_MRTR_ROUNDS)` for client rounds and calls `engine.answer`; delete its `build_answer_llm`, `build_verify_llm`, server-seam and `verify_*` merge code with no alias. `answer_mrtr.py` retrieves through `engine.search()` and reads settings through `engine.resolve_settings()`. Redact handler errors with `redact_engine_error`. Keep every error dict, description and annotation unchanged.
- [x] 1.5 Rewrite `main()`: build the Engine with `compose.build_engine()` before `server.run(transport="stdio")`, keeping the redacted startup error and exit code 1; the stdio lifespan yields `McpContext(engine, PathPolicy.allow_all(), no-op admission)` and closes the Engine on exit; remove the `ensure_runtime_setup()` call. In `transports/cli/__init__.py` `callback`, skip `_initialise_runtime()` when no subcommand is given (as it already does for `web`), so bare `omrg` builds one Engine, not two; change `test_no_argument_start_still_runs_mcp_server` to assert `ensure_runtime_setup` is not called and the MCP Engine is built once.
- [x] 1.6 Move the MCP tool tests to a test lifespan with a fake or test Engine instead of patching module globals; add a test that the stdio server searches with the process-default store unset and fails if any handler reads it; add a snapshot test that tool names, descriptions and annotations equal the pre-refactor list; confirm the MRTR and legacy-sampling tests pass with the same source labels and round counts; repoint every `omrg.transports.mcp.mcp.run` patch (`tests/test_cli.py`, `tests/unit/test_web_launch.py`, `tests/unit/test_verification_gaps_transport.py`) and the `conftest.py` server fixture to the factory, with no alias left in `src`.

- [x] 1.7 Add `RedactionSecrets` and `Engine.redact` per design D9; `compose.build_engine()` fills it from `Settings`; delete `redact_engine_error`; point `engine_answer.py` and the MCP handler error helpers at it. Keep `test_ingest_error_envelope_redacts_cloud_key` (full and prefix forms) and `test_ingest_error_envelope_redacts_tenant_and_database` with their intent, building the Engine with cloud credentials instead of patching `get_settings()`. Add a failing-first test that an `Engine.answer` verifier error containing the Chroma Cloud tenant is redacted.
- [x] 1.8 Apply `runtime.engine.redact` to REST error bodies (`errors.error_response`, `routes_jobs`, `routes_graphs`); add failing-first tests that a job failure and a graph validation failure whose exception text holds the OpenRouter key or the Chroma Cloud tenant return a body without it.

## 2. Workspace storage

- [x] 2.1 Add a workspace database migration creating `workspace_settings(key, value)` and `mcp_tokens(token_id, token_hash, created_at)`; test the migration from the current version and that it only adds tables.
- [x] 2.2 Add the typed settings repository (`mcp_http_enabled`, `web_port`) per design D6; test unknown-key refusal and that invalid stored values read as unset.
- [x] 2.3 Add the token repository: create-or-replace in one transaction, revoke, and verify with a constant-time hash compare; tokens are `omrg_mcp_` plus `secrets.token_urlsafe(32)`, stored as SHA-256 only; test that the stored row never contains the token and that rotation invalidates the old token.

## 3. Port selection

- [x] 3.1 Change `omrg web` port resolution to `--port`, then the saved `web_port`, then 8765, with `--port 0` still choosing a free port (design D5); test each source and their order.
- [x] 3.2 On a taken port, exit with code 1 and a stderr message naming the port, `--port <n>` and the Settings option; test it with a socket already bound to the port.
- [x] 3.3 Add `GET /v1/settings/web-port` (read) and `PUT /v1/settings/web-port` (`manage`, 1024 to 65535 or `null`); test validation, bearer refusal, and that the bound port does not change.

## 4. HTTP transport

- [x] 4.1 In `create_app`, build the HTTP MCP server with a lifespan yielding `McpContext(runtime.engine, PathPolicy.from_grants(runtime.grants), runtime.admission)`, mount `streamable_http_app` at `/mcp` with stateful sessions and `TransportSecuritySettings` limited to the bound host and port; enter `session_manager.run()` in the web lifespan after the Engine is built and leave it before the Engine closes.
- [x] 4.2 Add the pure ASGI `McpGate` (off returns 404, foreign `Origin` returns 403, bad or missing bearer returns 401, in that order) per design D3; keep `GuardMiddleware`'s Host check for `/mcp`; test each refusal, that an absent `Origin` passes, and that no tool runs on a refused request.
- [x] 4.3 Add `GET /v1/mcp`, `PUT /v1/mcp`, `POST /v1/mcp/token` and `DELETE /v1/mcp/token` per design D7; `PUT` writes the database, then updates the gate's in-memory flag; test off by default, enable surviving a restart, turning off ending an open session, the token shown only once, bearer refusal of `PUT` and the token routes, and the MCP token being refused on every `/v1` route.
- [x] 4.4 Add the `omrg_mcp_` pattern to `RedactingFilter`; test that a logged token is removed.
- [x] 4.5 End-to-end test with the SDK's streamable HTTP client against a test app: initialise, list tools, ingest a file inside an approved root, search it over `/mcp`, refuse a path outside the roots, and confirm a document ingested through `/v1` is found over `/mcp` without a restart.
- [x] 4.6 Test shutdown order: a tool call running during shutdown finishes or is cancelled before the Engine closes.

## 5. Contract and documentation

- [x] 5.1 Update the OpenAPI contract artifacts for the six new operations.
- [x] 5.2 Update `docs/guides/mcp-tools.md` with the HTTP client configuration (URL, bearer header) beside the stdio one, and `docs/guides/cli-reference.md` with the port order and the taken-port message.
- [x] 5.3 Record the decision to serve MCP from the web server with a lifespan-provided Engine as an ADR (`s-adr`).

## 6. Verification

- [x] 6.1 Run `uv run pytest -m "not slow"`, the import-contract checks and `./scripts/local_ci.sh`; record exact results.
- [x] 6.2 Run `openspec validate add-mcp-http-transport --strict` and resolve every finding.
- [ ] 6.3 Connect one real MCP client (Claude Code) over HTTP to a local `omrg web`, run a search, rotate the token, and confirm the old token is refused.
