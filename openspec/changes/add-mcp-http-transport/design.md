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
    paths: PathPolicy      # allow-all on stdio; root grants on HTTP
    admit: Admit           # no-op on stdio; runtime admission on HTTP
```

Each handler takes `ctx: Context` and reads `ctx.request_context.lifespan_context`. Handlers call Engine methods (`search`, `answer`, `ingest`, `list_collections`, `resolve_settings`, `profile_resolver`, `store`) instead of core functions with process defaults. Operations the Engine does not expose today (document listing, deletion by path or metadata, profile change) take `engine.store` and `engine.profile_resolver` as explicit arguments, as `transports/api/engine_access.py` already does. The reranker comes from the Engine's composition, not a module global, so `_get_reranker` and `_get_profile_resolver` are deleted.

- **Stdio lifespan**: `compose.build_engine()` inside the lifespan, `PathPolicy.allow_all()`, and a no-op admission. The Engine closes when the lifespan exits. `main()` no longer calls `ensure_runtime_setup()`. Startup stays fail-fast: a build error inside the lifespan prints the existing redacted message and exits with code 1.
- **HTTP lifespan**: yields `runtime.engine`, `PathPolicy.from_grants(runtime.grants)` and `runtime.admission`. It does not close the Engine; the web lifespan owns it.

The answer tool keeps MRTR and sampling. Its server-side LLM still comes from `compose.build_answer_llm()`, which already takes no process default.

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
