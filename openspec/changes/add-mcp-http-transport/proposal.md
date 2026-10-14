# Proposal

## Why

MCP runs only on stdio today: each MCP client starts its own `omrg` process, which builds a second Engine beside the one `omrg web` owns. The redesigned Settings view (`redesign-web-workspace` task 7.6) needs an on/off switch for MCP served by the web server itself, so one running server answers both the browser and MCP clients from one Engine.

Three things block that today. `omrg web` picks a random port on each launch, so a client configuration breaks on restart. Bearer credentials live in memory and vanish on restart. The MCP tool handlers read process-wide defaults installed by `compose.ensure_runtime_setup()`, while the web server deliberately installs none, so the handlers cannot reach the web server's Engine.

## What Changes

- **MCP over streamable HTTP at `/mcp`** on the `omrg web` server, using the MCP SDK's session manager, sharing the web runtime's one Engine. It is off until the user turns it on.
- **MCP tools take their Engine from the server lifespan.** A factory builds the MCP server and registers the tools on it. Stdio builds its own Engine in the lifespan and closes it on exit; the web server passes its runtime Engine. The handlers no longer read process defaults. **BREAKING** for code that imports the module-level `mcp` object to register tools; the handler re-exports stay.
- **File paths over HTTP follow the web server's root grants.** `ingest_documents` and `get_codebase_map` refuse paths outside the `--root` directories with the standard MCP error dict. Stdio keeps today's behaviour.
- **A durable MCP token.** One token with a new `mcp` scope, stored only as a hash in the workspace database and shown once when created. Settings can create, rotate and revoke it. Clients send it as `Authorization: Bearer`.
- **A stable port.** `omrg web` listens on `127.0.0.1:8765` by default. `--port` overrides it for one launch, a port saved from Settings overrides the default for later launches, and `--port 0` keeps a random port. **BREAKING**: the default port changes from random to 8765.
- **Workspace settings storage.** A key-value table in the workspace database holds `mcp_http_enabled` and `web_port`. Changing either goes through new `/v1/mcp` and `/v1/settings/web-port` endpoints that only the browser session can call.

## Capabilities

### New Capabilities

- `mcp-http-transport`: MCP over streamable HTTP on the web server, its on/off state, token authentication, host and origin checks, root-limited file paths, and the shared Engine.

### Modified Capabilities

- `transport-separation`: "FastMCP lifespan and context forward-compatibility" becomes a requirement that the lifespan provides the Engine and the handlers read it from the request context.
- `engine-scoped-composition`: "The server startup path is one caller of the engine" no longer names the MCP server as a process-default user; the CLI and watcher keep `ensure_runtime_setup()`.
- `local-web-workspace`: adds a stable default port with a saved override, and the durable `mcp` credential beside the in-memory notebook credentials.

## Impact

- **Backend**: `transports/mcp/` (server factory, tool registration, lifespan context, path policy hook); `transports/api/` (mount, gate, `/v1/mcp` and `/v1/settings/web-port` routes, `mcp` scope, token verification); `transports/cli/web.py` (default port and saved port); `integrations/workspace_sqlite/` (migration for `workspace_settings` and `mcp_tokens`); OpenAPI contract.
- **Frontend**: none in this change. `redesign-web-workspace` task 7.6 builds the Settings controls on these endpoints, and its dev proxy default moves to `http://127.0.0.1:8765`.
- **Dependencies**: none new. The installed `mcp` 2.0.0 provides the streamable HTTP session manager and DNS-rebinding protection.
- **Docs**: `docs/guides/mcp-tools.md` and `docs/guides/cli-reference.md` gain the HTTP client configuration and the port rules.
- **Out of scope**: remote (non-loopback) access, OAuth, more than one MCP token, and the Settings UI.
