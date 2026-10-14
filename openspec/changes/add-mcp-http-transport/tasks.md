# Tasks

Rules for every task: write the test first and confirm it fails against the old code; keep every file under 500 lines; MCP handlers never raise (gotcha #1) and keep `ToolAnnotations` (gotcha #7); CLI output goes to stderr (gotcha #5).

## 1. MCP server factory and lifespan context

- [ ] 1.1 Add `transports/mcp/context.py` with the frozen `McpContext` (engine, path policy, admission) and `PathPolicy` (`allow_all()`, `from_grants(grants)`) per design D2; unit-test that `from_grants` refuses a path outside the roots and a symlink that resolves outside them.
- [ ] 1.2 Add `transports/mcp/server.py` with `create_mcp_server(lifespan)` and `register_tools(server)`; convert every tool module to a plain handler registered from `register_tools`, each taking `ctx: Context`; remove the module-level `mcp`, `_get_reranker` and `_get_profile_resolver`; keep the package-root handler re-exports.
- [ ] 1.3 Rewrite each handler to use the Engine from `McpContext`: `search_documents` and `answer_documents` call Engine methods; `ingest_documents` checks the path policy, then calls `engine.ingest`; `get_codebase_map` checks the path policy; listing, deletion and profile change pass `engine.store` and `engine.profile_resolver` explicitly. Keep every error dict and annotation unchanged.
- [ ] 1.4 Rewrite `main()` with a stdio lifespan that builds the Engine through `compose.build_engine()`, yields `McpContext(engine, PathPolicy.allow_all(), no-op admission)` and closes the Engine on exit; remove the `ensure_runtime_setup()` call; keep the fail-fast redacted startup error and exit code 1.
- [ ] 1.5 Move the MCP tool tests to a test lifespan with a fake Engine; add a test that the stdio server searches with the process-default store unset and fails if a handler reads it; add a test that the tool list (names, descriptions, annotations) is unchanged from before the refactor.

## 2. Workspace storage

- [ ] 2.1 Add a workspace database migration creating `workspace_settings(key, value)` and `mcp_tokens(token_id, token_hash, created_at)`; test the migration from the current version and that it only adds tables.
- [ ] 2.2 Add the typed settings repository (`mcp_http_enabled`, `web_port`) per design D6; test unknown-key refusal and that invalid stored values read as unset.
- [ ] 2.3 Add the token repository: create-or-replace in one transaction, revoke, and verify with a constant-time hash compare; tokens are `omrg_mcp_` plus `secrets.token_urlsafe(32)`, stored as SHA-256 only; test that the stored row never contains the token and that rotation invalidates the old token.

## 3. Port selection

- [ ] 3.1 Change `omrg web` port resolution to `--port`, then the saved `web_port`, then 8765, with `--port 0` still choosing a free port (design D5); test each source and their order.
- [ ] 3.2 On a taken port, exit with code 1 and a stderr message naming the port, `--port <n>` and the Settings option; test it with a socket already bound to the port.
- [ ] 3.3 Add `GET /v1/settings/web-port` (read) and `PUT /v1/settings/web-port` (`manage`, 1024 to 65535 or `null`); test validation, bearer refusal, and that the bound port does not change.

## 4. HTTP transport

- [ ] 4.1 In `create_app`, build the HTTP MCP server with a lifespan yielding `McpContext(runtime.engine, PathPolicy.from_grants(runtime.grants), runtime.admission)`, mount `streamable_http_app` at `/mcp` with stateful sessions and `TransportSecuritySettings` limited to the bound host and port; enter `session_manager.run()` in the web lifespan after the Engine is built and leave it before the Engine closes.
- [ ] 4.2 Add the pure ASGI `McpGate` (off returns 404, foreign `Origin` returns 403, bad or missing bearer returns 401, in that order) per design D3; keep `GuardMiddleware`'s Host check for `/mcp`; test each refusal, that an absent `Origin` passes, and that no tool runs on a refused request.
- [ ] 4.3 Add `GET /v1/mcp`, `PUT /v1/mcp`, `POST /v1/mcp/token` and `DELETE /v1/mcp/token` per design D7; `PUT` writes the database, then updates the gate's in-memory flag; test off by default, enable surviving a restart, turning off ending an open session, the token shown only once, bearer refusal of `PUT` and the token routes, and the MCP token being refused on every `/v1` route.
- [ ] 4.4 Add the `omrg_mcp_` pattern to `RedactingFilter`; test that a logged token is removed.
- [ ] 4.5 End-to-end test with the SDK's streamable HTTP client against a test app: initialise, list tools, ingest a file inside an approved root, search it over `/mcp`, refuse a path outside the roots, and confirm a document ingested through `/v1` is found over `/mcp` without a restart.
- [ ] 4.6 Test shutdown order: a tool call running during shutdown finishes or is cancelled before the Engine closes.

## 5. Contract and documentation

- [ ] 5.1 Update the OpenAPI contract artifacts for the six new operations.
- [ ] 5.2 Update `docs/guides/mcp-tools.md` with the HTTP client configuration (URL, bearer header) beside the stdio one, and `docs/guides/cli-reference.md` with the port order and the taken-port message.
- [ ] 5.3 Record the decision to serve MCP from the web server with a lifespan-provided Engine as an ADR (`s-adr`).

## 6. Verification

- [ ] 6.1 Run `uv run pytest -m "not slow"`, the import-contract checks and `./scripts/local_ci.sh`; record exact results.
- [ ] 6.2 Run `openspec validate add-mcp-http-transport --strict` and resolve every finding.
- [ ] 6.3 Connect one real MCP client (Claude Code) over HTTP to a local `omrg web`, run a search, rotate the token, and confirm the old token is refused.
