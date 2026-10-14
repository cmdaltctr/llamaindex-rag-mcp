# Design

## Context

Observed in the code on `integration/core-web` (7257c78):

- `transports/mcp/__init__.py` creates a module-level `mcp = MCPServer("omrg", lifespan=_noop_lifespan)`. The tool modules register on it with `@mcp.tool` when they are imported. `main()` calls `compose.ensure_runtime_setup()` and then `mcp.run(transport="stdio")`.
- The handlers call core functions that read process defaults. For example, `search.py` calls `core.retrieval.search(...)` with `_get_reranker()` and `_get_profile_resolver()`, which are module globals. `answer.py` builds its LLM through `compose.build_answer_llm()`.
- `omrg web` (`transports/cli/web.py`) binds a loopback socket before startup. `--port` defaults to `0`, which picks a free port. The lifespan (`transports/api/lifespan.py`) builds one Engine and installs nothing as a process default. Engine work passes through `runtime.admission`.
- `transports/api/security.py` keeps bearer credentials in memory (`BEARER_SCOPES = {graph, read, run}`). The browser session holds those plus `files`, `plugins`, `credentials` and `manage`. `GuardMiddleware` checks `Host` on every request and checks `Origin` and fetch metadata on `/v1` paths.
- `integrations/workspace_sqlite/schema.py` runs ordered migrations keyed on `PRAGMA user_version`.
- `mcp` 2.0.0 is installed. `MCPServer.streamable_http_app()` and `session_manager` exist. `StreamableHTTPSessionManager.run()` enters the server lifespan once and can run once per instance. `TransportSecuritySettings` provides DNS-rebinding checks with allowed hosts and origins.

## Goals and Non-Goals

Goals: one running server answers the browser and MCP clients from one Engine; the client configuration stays valid across restarts; MCP over HTTP is no weaker than the REST API on the same server.

Non-goals: remote access, OAuth, several tokens or per-tool scopes, and any Settings UI (that is `redesign-web-workspace` task 7.6).

## Decisions

### D1. A server factory replaces the module-level server

`transports/mcp/server.py` exposes `create_mcp_server(lifespan) -> MCPServer`. It constructs the server and calls `register_tools(server)`. Each tool module exposes its handler as a plain async function and registers it from `register_tools` with `server.tool(description=..., annotations=...)`. Import has no side effect. The package root keeps re-exporting the handlers, so `from omrg.transports.mcp import search_documents` still works. The module-level `mcp` object is removed; no alias is kept.

Rejected: keeping the module-level server and setting a module global to point at the Engine. That is a process default under another name, and stdio and HTTP could not differ in their path policy.

### D2. The lifespan yields an `McpContext`; handlers read it

```python
@dataclass(frozen=True)
class McpContext:
    engine: Engine
    paths: PathPolicy  # allow-all on stdio; root grants on HTTP
    admit: Admit  # no-op on stdio; runtime.admission.enter on HTTP
```

Each handler takes `ctx: Context` and reads `ctx.request_context.lifespan_context`. Each HTTP tool call runs inside `admit()`. `_get_reranker`, `_get_profile_resolver` and every read of `get_default_effective_settings()` or `vectordb.get_default_store()` in `transports/mcp/` are deleted. Each tool maps to the Engine like this; every core function named here already accepts `store=`:

| Tool | Engine use |
|---|---|
| `search_documents` | `engine.resolve_settings(collection)` for profile defaults, then `engine.search(...)` |
| `answer_documents` | `engine.answer(...)`, see D8 |
| `ingest_documents` | `paths.check(path)`, then `engine.ingest(path, collection_name=...)` |
| `get_codebase_map` | `paths.check(path)`, then `codebase_map.get_codebase_map_text(path=..., refresh=..., settings=engine.resolve_settings(None), store=engine.store)` |
| `list_indexed_documents` | `list_documents(collection, store=engine.store)` |
| `list_collections` | `engine.list_collections()` is names only, so call `core.retrieval.list_collections(store=engine.store)` to keep the counts |
| `delete_documents` | `preview_delete`, `remove_document`, `remove_by_metadata`, `remove_collection` with `store=engine.store` |
| `change_collection_profile` | `generate_safety_contract(..., resolver=engine.profile_resolver, store=engine.store)` and `apply_profile_change(..., store=engine.store)` |

Deletion and profile change keep their MCP confirmation model (`dry_run`, `confirm`, `destructiveHint`) over both transports. The web API's confirmation tokens do not apply to `/mcp`. Deleting by path removes index rows and reads no file, so the root grants do not apply to it.

Handler error text is redacted with `engine.redact(text)`, see D9. `compose.redaction_values()` stays only in stdio `main()`, for startup failures before an Engine exists.

- **Stdio**: `main()` builds the Engine with `compose.build_engine()` before `server.run(transport="stdio")`, so a startup error still prints the existing redacted message and exits with code 1 before the transport starts. The stdio lifespan yields `McpContext(engine, PathPolicy.allow_all(), no-op admission)` and closes the Engine when it exits. `main()` no longer calls `ensure_runtime_setup()`, and the CLI callback no longer runs `_initialise_runtime()` before bare `omrg`, so stdio builds exactly one Engine.
- **HTTP**: the lifespan yields `McpContext(runtime.engine, PathPolicy.from_grants(runtime.grants), runtime.admission.enter)`. It does not close the Engine; the web lifespan owns it.

### D3. Mounting and the gate

`create_app` builds a second MCP server with the HTTP lifespan and calls `streamable_http_app(streamable_http_path="/", stateless_http=False, transport_security=TransportSecuritySettings(allowed_hosts=[f"{host}:{port}"], allowed_origins=[f"http://{host}:{port}"]))`, then mounts it at `/mcp`. Starlette does not run a mounted app's lifespan, so the web lifespan enters `mcp_server.session_manager.run()` after the Engine is built and leaves it before `shutdown_runtime` closes the Engine.

A pure ASGI `McpGate` sits in front of the mount. In order, it:

1. returns 404 when `mcp_http_enabled` is false (read from an in-memory copy that `PUT /v1/mcp` updates after the database write);
2. refuses a foreign `Origin` with 403 (an absent `Origin` passes);
3. checks `Authorization: Bearer` against the stored hash with a constant-time compare and returns 401 on failure.

Only then does the SDK see the request. Because the gate checks every request, turning MCP off ends existing sessions at their next request. The session manager runs for the whole launch, because it can run only once per instance.

`GuardMiddleware` keeps its Host check for `/mcp`. Its `/v1`-only Origin and fetch-metadata rules do not apply, because MCP clients send no browser headers; the gate's Origin rule covers browsers.

### D4. The MCP token is separate from the REST credentials

New table `mcp_tokens(token_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, created_at TEXT NOT NULL)` holds at most one row. The token is `secrets.token_urlsafe(32)` with an `omrg_mcp_` prefix so log redaction can match it. Only its SHA-256 hash is stored. A random 256-bit token needs no slow hash. The `mcp` scope is never added to `BEARER_SCOPES` or `SESSION_SCOPES`, so `require_scope` refuses the token on every `/v1` route and the browser session cannot call `/mcp`.

- `POST /v1/mcp/token` (`credentials` scope, session only): replaces the row in one transaction and returns `{ token, created_at }` once.
- `DELETE /v1/mcp/token` (`credentials` scope): deletes the row.
- `RedactingFilter` gains the `omrg_mcp_` pattern.

### D5. Port selection

`web.py` resolves the port as: `--port` if given, else the saved `web_port` if valid, else 8765. `--port` changes its default from `0` to "not given"; `0` still means a free port. On `OSError` with `EADDRINUSE`, the command prints "Port 8765 is in use. Start with --port <n>, then save it in Settings > MCP." and exits with code 1. The saved port is read from the workspace database before the bind; the workspace lock probe already runs at that point.

`GET /v1/settings/web-port` returns `{ saved, bound }`. `PUT /v1/settings/web-port` (`manage` scope) validates 1024 to 65535 or `null` and does not rebind.

### D6. Workspace settings table

Migration `workspace_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)`. A small repository exposes typed `get_mcp_http_enabled() -> bool` and `get_web_port() -> int | None`, plus setters. Unknown keys are refused. A stored value that fails parsing reads as unset. Provider settings stay in `.env` (that is `add-runtime-settings`).

### D7. API surface

| Method and path | Scope | Purpose |
|---|---|---|
| `GET /v1/mcp` | read | `{ enabled, url, token: { exists, created_at } }` |
| `PUT /v1/mcp` | manage | `{ enabled }`, returns the stored state |
| `POST /v1/mcp/token` | credentials | create or rotate, returns the token once |
| `DELETE /v1/mcp/token` | credentials | revoke |
| `GET /v1/settings/web-port` | read | `{ saved, bound }` |
| `PUT /v1/settings/web-port` | manage | save or clear the port |
| `/mcp` | MCP token | streamable HTTP MCP |

`manage` and `credentials` are session-only scopes, so bearer credentials cannot change MCP or the port.

### D8. `Engine.answer` accepts a client completion and resolved rows

The MCP answer tool builds its own server model and verifier today (`compose.build_answer_llm()` and `compose.build_verify_llm()` in `transports/mcp/answer.py`), duplicating `Engine.answer`, because `Engine.answer` cannot take a client-supplied model or rows already retrieved. The Engine gains two keyword-only arguments:

```python
@dataclass(frozen=True)
class ClientCompletion:
    complete: CompletionSeam
    source: Literal["client_mrtr", "client_legacy"]
    max_rounds: int

async def answer(self, question, *, ..., client_completion: ClientCompletion | None = None,
                 rows: list[dict] | ResolvedRetrieval | None = None) -> dict
```

- With `client_completion`, the Engine uses `complete` instead of the server model, reports `source` as the completion source, and caps the answer block with `effective.answer.model_copy(update={"max_rounds": max_rounds})`. Without it, behaviour is unchanged.
- The round cap stays in the MCP transport: the handler sets `max_rounds = min(block.max_rounds, _MAX_MRTR_ROUNDS)`, because only the transport knows its MRTR chain depth. Client round counts therefore stay as they are today.
- Claim verification stays Engine-owned and server-side in every case; a client completion never replaces the verifier.
- With `rows`, the Engine skips retrieval and answers from them. `ResolvedRetrieval` already exists in `core/answer/pipeline.py`, and core already accepts `rows=`.
- `engine.py` is at 496 lines, so the answer composition (server-model seam, verifier build, client-completion selection, round cap) moves to a new `omrg/engine_answer.py`; `Engine.answer` delegates to it. `ClientCompletion` lives there and is re-exported from `omrg.engine`.
- The answer block for the handler comes from `engine.resolve_settings(collection).answer`, which already carries the resolver's `verify_*` overlay, so the handler's `verify_*` merge is deleted. No `Engine.settings` property is added.
- `transports/mcp/answer.py` deletes its `build_answer_llm`, `build_verify_llm` and server-seam paths with no alias. `answer_mrtr.py` retrieves through `engine.search()` and reads settings through `engine.resolve_settings()`.

### D9. The Engine owns credential redaction

`redact_engine_error(exc, effective)` reads the Chroma Cloud key, tenant and database from `EffectiveSettings`, which has none of them, so it never removed Chroma Cloud values. The MCP handlers stayed safe only because they read `compose.redaction_values()` from the environment, which D2 removes. The REST API's `redact()` removes OMRG tokens but receives no provider values, so job and graph error bodies (`routes_jobs.py`, `routes_graphs.py`) can carry them.

- New frozen `RedactionSecrets(chroma_cloud_api_key, chroma_cloud_tenant, chroma_cloud_database, openrouter_api_key)` in `core/vectordb/identity.py`, beside `redact_cloud_secrets` and `redact_secret`, with `redact(text) -> str` applying both (full value and prefixes of six or more characters, as today).
- `Engine.__init__` gains `redaction: RedactionSecrets = RedactionSecrets()`. `compose.build_engine()` fills it from the resolved `Settings`. The empty default is correct: an Engine built without configured secrets has nothing to remove.
- Public `Engine.redact(text) -> str`. `engine_answer.py` uses it; `redact_engine_error` is deleted with no alias.
- MCP handlers (`_error_detail`, `_error_message`, `_log_tool_error`) take the Engine's redactor from `McpContext`.
- REST error bodies: `errors.error_response`, `routes_jobs` and `routes_graphs` apply `runtime.engine.redact` before the existing `redact()`.
- Credentials stay out of `EffectiveSettings`, so `settings-models-are-pure-data` holds.

## Risks and Trade-offs

- Changing every handler signature is the largest part of the work. The MCP tool tests must move from patching module globals to building a test lifespan with a fake Engine. Accepted, because the globals are what block sharing the Engine.
- The default port 8765 can be taken. The error names the fix, and Settings saves a port for later launches.
- MCP over HTTP runs only while `omrg web` runs. A client configured for HTTP fails when the server is down. Stdio remains for clients that should start OMRG themselves.
- One token for every client means rotating it updates every client. Accepted for a single-user local tool.
- A long tool call holds admission open, so shutdown waits for it, as REST engine work already does.

## Migration Plan

The workspace database gains one migration. MCP over HTTP starts off. Users who relied on a random port pass `--port 0`. Rollback: revert the change; the extra tables are ignored by older code because migrations only add tables.

## Open Questions

None blocking. `redesign-web-workspace` must update its dev proxy default to `http://127.0.0.1:8765` and point task 7.6 at the endpoints in D7.
