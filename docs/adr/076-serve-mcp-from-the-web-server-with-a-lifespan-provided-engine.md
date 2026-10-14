# ADR-076: Serve MCP from the Web Server with a Lifespan-Provided Engine

- **Date:** 2026-10-14
- **Status:** Proposed (becomes Accepted after the real-client check, task 6.3)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-031](031-three-layer-config-compose-di.md) (config, compose, DI), [ADR-036](036-phase-5-refactor-transport-separation.md) (transport separation), [ADR-037](037-architecture-v2-conformance.md) (settings injected, never global), [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) (local web runtime)
- **Change:** `openspec/changes/add-mcp-http-transport/` (design D1 to D9)

## Context

MCP ran only on stdio. Each MCP client started its own `omrg` process, which built a second Engine beside the one that `omrg web` owns. The Settings view of the web workspace needs a switch for MCP that the web server itself serves, so one running server answers the browser and MCP clients from one Engine.

Three things blocked this:

1. MCP tool handlers read process-wide defaults (store, settings, reranker, profile resolver) that `compose.ensure_runtime_setup()` installs. The web server installs none (ADR-037), so the handlers could not reach its Engine.
2. `omrg web` chose a random port at each launch, so a client configuration broke at each restart.
3. Web credentials lived in memory and ended at restart.

A review of the first plan found a fourth problem. `redact_engine_error` read the Chroma Cloud key, tenant and database from `EffectiveSettings`, which holds none of them. MCP handlers stayed safe only because they read the values from the environment, and REST error bodies removed OMRG tokens only.

## Decision

1. **A server factory replaces the module-level server.** `create_mcp_server(lifespan)` builds a server and registers every tool. There is no module-level `mcp` object and no alias.
2. **The lifespan yields an `McpContext`** (Engine, path policy, admission hook). Handlers read it from the request context. Stdio builds its Engine through `compose.build_engine()` and closes it on exit. HTTP uses the web runtime's Engine and does not close it.
3. **MCP is served at `/mcp`** by the SDK's streamable HTTP session manager inside `omrg web`. A pure ASGI gate runs three checks in order: the switch is on (else 404), the `Origin` is not foreign (else 403), the bearer token matches (else 401).
4. **The switch is off until a browser session turns it on.** It is stored in the workspace database.
5. **One durable token** with the prefix `omrg_mcp_`. Only its SHA-256 hash is stored. The value is shown once. The token works on `/mcp` only. Every `/v1` route refuses it.
6. **File paths over HTTP stay inside the `--root` directories**, with the same symlink-safe check as the web API. Stdio is unchanged.
7. **`Engine.answer` accepts a `ClientCompletion` and resolved `rows`.** A client completion replaces only the answer model. Verification stays server-side.
8. **The Engine owns credential redaction** (`RedactionSecrets`, `Engine.redact`). MCP handlers and REST error bodies use it.
9. **`omrg web` listens on 8765 by default.** The order is `--port`, then the saved port, then 8765. `--port 0` still picks a free port.

## Consequences

### Positive

- One Engine and one index answer the browser and MCP clients. A document ingested through the web API is found over MCP without a restart.
- Handlers read no process default, so stdio and HTTP differ only in their path policy and admission hook.
- Chroma Cloud values no longer reach MCP or REST error text.
- The port and the token survive restarts, so a client configuration stays valid.

### Negative

- **Breaking:** code that registered tools on `omrg.transports.mcp.mcp`, or called `_get_reranker` or `_get_profile_resolver`, must use the factory.
- **Breaking:** `omrg web` no longer picks a random port by default. Pass `--port 0` for the old behaviour.
- MCP over HTTP runs only while `omrg web` runs.
- One token for all clients. Rotation updates every client.
- All MCP sessions share one lifespan context, so the answer tool's per-request cache is keyed by that context, not by client. Two clients that ask the same question of the same collection at the same time can share retrieved rows. The deployment has one user and one token.
- A tool call that runs longer than the 5-second graceful-shutdown limit is cancelled at Ctrl+C. Its worker thread can finish after the Engine closes.
- With no answer model configured, `answer_documents` now reports `completion_source: "server"` where it reported `"none"`.

### Neutral

- No new dependency. The installed `mcp` 2.0.0 provides the session manager and DNS-rebinding checks.
- OAuth, remote access and several tokens remain out of scope.

## Alternatives Considered

| Option | Rejected Because |
|--------|------------------|
| Keep the module-level server and point a module global at the Engine | It is a process default under another name. Stdio and HTTP could not differ in their path policy. |
| A separate MCP process that calls the REST API | A second process and a second credential set. No gain over serving from the same Engine. |
| Reuse the `/v1` bearer credentials for MCP | Those credentials end at restart and carry notebook scopes. A leaked MCP token would reach the REST API. |
| Put the Chroma Cloud values on `EffectiveSettings` | It breaks the pure-data settings contract and copies credentials into every settings overlay. |
| Keep a random default port | A client configuration breaks at each restart. |
| Stateless HTTP sessions | Sampling and multi-round answers need a session. |

## References

- Design and specs: `openspec/changes/add-mcp-http-transport/`
- `src/omrg/transports/mcp/` (server, context, handlers), `src/omrg/transports/api/mcp_http.py` (gate), `src/omrg/transports/api/routes_mcp.py` (state, token, port)
- `src/omrg/engine.py`, `src/omrg/engine_answer.py`, `src/omrg/core/vectordb/identity.py` (`RedactionSecrets`)
- [MCP tools reference](../guides/mcp-tools.md), [Web workspace](../guides/web-workspace.md)
