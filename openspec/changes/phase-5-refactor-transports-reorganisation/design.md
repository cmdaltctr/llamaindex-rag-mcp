## Context

Phase 5, the final phase of the refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §5.2 transports/integrations, §8). Phases 1–4 modularised the core; Phase 5 organises the perimeter. It also publishes the OpenAPI 3.1 contract (Decision 6: the REST API is a firm commitment delivered as contract-first, implementation later) and carries the M8 documentation sweep — without it, agents would enforce the old invariants against the new tree.

## Goals / Non-Goals

**Goals:**

- `transports/` (mcp.py, cli/ split, api/ contract), `daemon/`, and `integrations/` in their final shape.
- Uniform MCP error-dict contract (L5).
- FastMCP lifespan/context forward-compatibility preserved structurally.
- Valid OpenAPI 3.1 contract with zero runtime HTTP code.
- AGENTS.md, architecture guide, and graphify graph matching the final tree.

**Non-Goals:**

- No REST/HTTP implementation (separate follow-up change against `openapi.yaml`).
- No FastMCP lifespan/context adoption (only structural readiness).
- No behaviour change to CLI commands, MCP tools, watcher, or PDF factory.
- No removal of any compat shim (all shims die in v2.0.0).

## Decisions

### D1: `readers/` merges into `integrations/pdf/`

The reader/integration distinction was blurry — pypdf and pypdfium are library adapters just as Magika is (Decision 5). Azure sits at `integrations/azure.py`, not inside `pdf/`, because it is a cloud intelligence service; the factory still dispatches to it. ADR-020 is amended for location only. A deprecated `readers/` shim preserves the old import path.

### D2: CLI split by command group, not by verb

`transports/cli/` splits into `ingest.py`, `search.py`, `list.py`, `watch.py` (~200–300 lines each). Alternative considered: one module per subcommand — rejected; too granular, shared helpers would need a fifth module anyway.

### D3: Contract-first REST commitment

`openapi.yaml` ships before any HTTP code so the REST surface is reviewed as a document, mapped to existing core operations (§5.2 table), and validated in CI. MCP and REST share the core operation contract but MCP does not generate REST routes from tool signatures — the OpenAPI document is the HTTP shape's source of truth.

### D4: M8 ships with the move, not after it

AGENTS.md and the architecture guide are updated in this same change. The refactor rewrites every invariant AGENTS.md enforces; a stale AGENTS.md after merge means every agent session enforces the old structure against the new code.

### D5: L5 fixed during the move

The `ingest_documents` handler gains failure handling while the file is already being touched, making the error-dict invariant uniform rather than mostly-true.

## Risks / Trade-offs

- CLI split breaks entry-point wiring → the `pyproject.toml` entry point and every subcommand are smoke-tested; the split is mechanical (functions move, argparse/click structure unchanged).
- `readers/` shim masks a missed call site → grep gate: zero `rag_mcp.readers` imports in `src/` outside the shim itself.
- OpenAPI contract drifts from core models before the REST implementation lands → CI validation plus a documented rule that the follow-up change reconciles the contract with the typed core models first.
- Magika extraction subtly changes detection → existing codebase-map tests are the regression net, unmodified.

## Migration Plan

1. Move `server.py` → `transports/mcp.py`; fix L5; smoke-test server start.
2. Split `cli.py` → `transports/cli/`; smoke-test every subcommand.
3. Move `watcher.py` → `daemon/`; move `readers/` → `integrations/pdf/` with shim; move Azure; extract Magika.
4. Write `transports/api/README.md` + `openapi.yaml`; add CI validation.
5. M8 sweep: AGENTS.md, architecture guide, `graphify update .`.
6. Rollback: branch revert.

## Open Questions

- OpenAPI validation tool for CI (e.g. `vacuum`, `openapi-spec-validator`) — chosen at task time; must run offline and be added as a dev dependency only.
