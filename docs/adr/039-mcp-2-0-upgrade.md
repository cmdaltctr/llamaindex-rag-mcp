# ADR-039: MCP Python SDK 2.0 Upgrade

**Date:** 2026-08-12
**Status:** Accepted
**Scopes:** ADR-036 (Phase 5 transport separation — the `transports/mcp/` thin-wrapper invariant is preserved; only the SDK class name and field casing change)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The v3 minor-upgrade window (ADR-037 / commit 715fa7b) deliberately capped
`mcp[cli]<2` and `huggingface-hub<1` because both 2.0/1.0 releases rewrote
public APIs. The `chore/deps-major-upgrade` branch is the cycle that lifts
those caps. This ADR covers the **mcp 2.0** lift only; huggingface-hub 1.0
is a separate change.

mcp 2.0 (released 2026-07-28) is a breaking release. The official migration
guide lives at <https://py.sdk.modelcontextprotocol.io/v2/migration>. The
headline changes that touch this project:

1. **`FastMCP` → `MCPServer`** — the high-level server class was renamed
   and moved from `mcp.server.fastmcp` to `mcp.server.mcpserver`
   (re-exported as `mcp.server.MCPServer`). `FastMCPError` →
   `MCPServerError`.
2. **camelCase → snake_case on protocol types** — `ToolAnnotations` fields
   (`readOnlyHint`→`read_only_hint`, `destructiveHint`→`destructive_hint`)
   and `CallToolResult` fields (`isError`→`is_error`,
   `structuredContent`→`structured_content`). Pydantic aliases keep the
   old camelCase _constructors_ working at runtime, but attribute
   _access_ on returned objects is snake_case only.
3. **`create_connected_server_and_client_session` removed** from
   `mcp.shared.memory`. Replaced by the high-level `mcp.client.Client`,
   which accepts an `MCPServer` instance directly and handles the
   in-memory transport + session setup.
4. **`httpx`/`httpx-sse` → `httpx2`** — mcp no longer installs `httpx`.
   This project keeps `httpx>=0.27.0` as a **direct** dependency for the
   Ollama/OpenRouter/llama.cpp metadata clients, so those lazy imports
   are unaffected. No `httpx-sse` or `McpError`/`MCPError` usage exists
   in the codebase.
5. **`mcp.types` → `mcp-types` package** — wire types moved to a
   standalone distribution, but `from mcp.types import ...` still works
   (re-exported). No source change needed.
6. **Sync handlers functions now run on a worker thread** via
   `anyio.to_thread.run_sync()`. Five of our seven tool handlers are
   `def` (not `async def`): `list_indexed_documents`,
   `list_collections`, `delete_documents`, `get_codebase_map`,
   `change_collection_profile`. They gain concurrency for free; none
   rely on event-loop affinity, thread-locals, or
   `asyncio.get_running_loop()`, so this is a pure improvement.

## Decision

Lift the `mcp[cli]<2` cap and migrate to the v2 API surface. The change
is mechanical and confined to one transport module plus two test files.

### Source changes (`src/rag_mcp/transports/mcp/`)

- `from mcp.server.fastmcp import FastMCP` →
  `from mcp.server.mcpserver import MCPServer`
- `FastMCP("rag-mcp", ...)` → `MCPServer("rag-mcp", ...)`
- `_noop_lifespan(server: FastMCP)` → `_noop_lifespan(server: MCPServer)`
- All `ToolAnnotations(readOnlyHint=...)` / `destructiveHint=...` →
  snake_case `read_only_hint` / `destructive_hint` (7 call sites). The
  camelCase aliases still work via pydantic, but snake_case is the
  canonical v2 form and avoids relying on deprecated aliases.

The `@mcp.tool(description=..., annotations=...)` decorator signature is
unchanged. `mcp.run(transport="stdio")` is unchanged. The
`lifespan=`/`log_level=` constructor kwargs are unchanged. The
"transport is a thin wrapper" invariant (ADR-036) holds — no business
logic moved into or out of the transport.

### Test changes

- `tests/conftest.py`: `from mcp.shared.memory import
create_connected_server_and_client_session` → `from mcp.client import
Client`. The `connected_client` async context manager becomes
  `async with Client(mcp_server) as client: yield client` — a near
  drop-in. `Client` negotiates the 2026-07-28 protocol era by default;
  none of our tests drive server-initiated `ctx.elicit()`,
  `create_message()`, or `list_roots()`, so no `mode="legacy"` pin is
  needed.
- `tests/test_mcp_tools.py` and `tests/test_retrieval.py`: both define a
  `_extract_result` helper that read `result.structuredContent` and
  `result.isError` (camelCase). Updated to `result.structured_content`
  and `result.is_error`. One assertion
  (`test_search_without_query_returns_error`) used `result.isError` →
  `result.is_error`.

### What did NOT change

- `pyproject.toml` keeps `httpx>=0.27.0` as a direct dep (used by
  `core/metadata/{ollama,openrouter,llamacpp}.py`). mcp 2.0 no longer
  pulls `httpx` transitively, but the direct dep covers it.
- No `httpx` → `httpx2` port is required in our code: we never hand an
  `http_client=` or `auth=` object to the SDK, and our own `httpx`
  calls are independent of mcp's transport.
- `mcp[cli]` extra retained — the `mcp dev` / `mcp install` commands
  still work (now pinning the spawned env to the installed SDK version,
  which is the desired behaviour).

## Alternatives considered

- **Keep the `<2` cap indefinitely.** Rejected — the cap exists for the
  minor-upgrade window only (ADR-037); aging out of mcp fixes is the
  exact trap the major-upgrade cycle exists to escape.
- **Pin `mcp>=1,<2` and add a compatibility shim.** Rejected — the v1
  helpers (`create_connected_server_and_client_session`) are gone, not
  deprecated, so a shim would have to reimplement the v1 in-memory
  transport against a rewritten v2 internals. Not worth it for a
  mechanical rename.

## Consequences

- **Positive:** on the modern protocol era; sync tool handlers no longer
  block the event loop; `httpx2`/`truststore` bring system-store TLS
  validation.
- **Neutral:** `mcp-types` is a new transitive dep; `httpx-sse` removed,
  `httpx2`/`httpcore2` added (net dependency count roughly flat).
- **Watch:** if a future test needs server-initiated sampling, elicitation,
  or roots via the in-memory `Client`, pin `Client(server, mode="legacy",
...callbacks...)` or port the handler to a resolver dependency — the
  modern era raises `NoBackChannelError` for server-initiated requests.
- **Watch:** `filterwarnings = ["error"]` (if ever enabled) would turn
  `mcp.MCPDeprecationWarning` from deprecated SDK methods into exceptions
  inside tool handlers, surfacing as `CallToolResult(is_error=True)`.
  None of our handlers call deprecated methods today.

## Verification

- `uv lock --upgrade` → `mcp 1.29.0 → 2.0.0`, adds `httpcore2`,
  `httpx2`, `mcp-types`, `truststore`; removes `httpx-sse`.
- `uv sync` clean.
- `uv run pytest -m "not slow"`: **1201 passed, 3 skipped, 14
  deselected** (full fast suite green after the migration edits).
- `uv run mcp version` → `MCP version 2.0.0`.
