# src/omrg/transports (MCP, CLI and HTTP API)

Thin wrappers that put `core/` behind a protocol.

## What belongs here

- `mcp/`: the MCP server, one module per tool.
- `cli/`: the command line, one module per command group.
- `api/`: the local HTTP API for `omrg web`. Route groups live in `api/routes/`.

## What it must not contain

- Business logic. Validate input, delegate to `core/` or the Engine, and format output.
- `core/` never imports this package.

## Rules

1. MCP: never raise from a tool handler. Return `{"status": "error", "message": ...}` (helpers in `mcp/errors.py`).
2. MCP: put `ToolAnnotations` (`readOnlyHint`, `destructiveHint`) on every tool.
3. CLI: print with `Console(stderr=True)`. Stdout is the MCP protocol channel.
4. API: keep `api/openapi.yaml` in step with the routes. The OpenAPI conformance tests compare the two.
5. API: `api/__init__.py` imports nothing, so the `web` extra stays optional.

## Links

- [Root AGENTS.md](../../../AGENTS.md)
- [MCP tools guide](../../../docs/guides/mcp-tools.md)
