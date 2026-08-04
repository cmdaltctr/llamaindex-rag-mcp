## Why

With the core modularised (Phases 1–4), the outermost layer still betrays the flat layout: `server.py` and the 1235-line `cli.py` sit at the top level, `watcher.py` is a daemon masquerading as a module, and external-tool wrappers are split between `readers/` and loose top-level files (`azure_reader.py`, Magika inside `codebase_map.py`). This is Phase 5, the final phase of the refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §8): move every transport into `transports/`, consolidate every external wrapper into `integrations/`, give the daemon a home, and publish the versioned OpenAPI 3.1 contract for the committed future REST transport — without writing any HTTP runtime code. It also carries the documentation sweep (M8): the refactor rewrites every invariant AGENTS.md enforces, so the agent-facing contract must be updated in the same change or agents will enforce the old structure against the new code.

## What Changes

- `server.py` → `transports/mcp.py`, preserving FastMCP compatibility: the `FastMCP` constructor keeps the `lifespan=` slot (passed `None` today) and tool handler signatures do not preclude a future `ctx: Context` parameter (§5.2 compatibility note).
- **L5 fix:** the `ingest_documents` handler (currently no `try/except`, `server.py:45-47`) is wrapped so EVERY MCP tool handler returns an error dict on failure — the "never raise from MCP tool handlers" invariant (gotcha #1) enforced uniformly.
- `cli.py` (1235 lines) → `transports/cli/` split by command group: `ingest.py`, `search.py`, `list.py`, `watch.py` (~200–300 lines each).
- `watcher.py` → `daemon/watcher.py`.
- `readers/` → `integrations/pdf/` with renames (`pypdf_reader.py`→`pypdf.py`, `pypdfium_reader.py`→`pypdfium.py`, `liteparse_reader.py`→`liteparse.py`); ADR-020 amended for the new location. Old `from rag_mcp.readers import ...` resolves via a deprecated re-export shim.
- `azure_reader.py` → `integrations/azure.py` (cloud intelligence service, sits at `integrations/` root; the PDF factory still dispatches to it).
- Magika file-type detection extracted from `codebase_map.py` → `integrations/magika.py`.
- Create `transports/api/README.md` (design + implementation boundary) and `transports/api/openapi.yaml` — a versioned OpenAPI 3.1 contract mapping REST endpoints to existing core operations (`POST /v1/ingestions`, `POST /v1/collections/{collection}/search`, `GET /v1/collections`, `PATCH /v1/collections/{collection}/profile`, etc.), with explicit success and error schemas, authentication scheme declarations, long-running-operation semantics for ingestion and codebase-map generation, and the destructive-operation preview/confirm contract. **No runtime HTTP code** — the REST implementation is a separate follow-up OpenSpec change (Decision 6).
- **M8 documentation sweep:** update `AGENTS.md` (architecture invariants #1–#6, gotchas, module list) and `docs/guides/architecture.md` to the final tree; re-run `graphify update .`.
- New ADR 031: Transport Separation (MCP / CLI / API).

## Capabilities

### New Capabilities

- `transport-separation`: Thin transports over the shared core — the `transports/` and `daemon/` layout, the uniform MCP error contract, FastMCP lifespan/context forward-compatibility, the `integrations/` consolidation of external wrappers, and the versioned OpenAPI 3.1 contract for the future REST transport.

### Modified Capabilities

- `pdf-reader`: the reader factory and backends move physically from `readers/` to `integrations/pdf/` (ADR-020 amendment); factory dispatch behaviour and the `auto` fallback are unchanged.

## Impact

- **Code**: `server.py`, `cli.py`, `watcher.py`, `readers/`, `azure_reader.py` relocated; Magika extracted from `codebase_map.py`; new `transports/api/` contract files.
- **Interfaces**: CLI commands and MCP tool signatures unchanged; `from rag_mcp.readers import ...` still resolves via deprecated shim.
- **Docs**: `AGENTS.md`, `docs/guides/architecture.md`, graphify graph updated to the final tree (M8); ADR-020 amended; new ADR 031.
- **Dependencies**: none added.
- **Follow-up committed**: REST transport implementation as a separate OpenSpec change against the published `openapi.yaml`.
- **Risk**: Low — mostly file moves and import updates, plus a contract document.
