# ADR-036: Transport Separation (MCP / CLI / API)

**Date:** 2026-08-04
**Status:** Accepted
**Phase:** 5 — Transports Reorganisation
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

Phases 1–4 modularised the core (metadata, chunking, retrieval, vectordb,
profiles). The outermost layer still betrayed the flat layout: `server.py`
and the 1235-line `cli.py` sat at the top level, `watcher.py` was a daemon
masquerading as a module, and external-tool wrappers were split between
`readers/` and loose top-level files (`azure_reader.py`, Magika inside
`codebase_map.py`).

The refactor proposal (§5.2, §8) called for a clean separation between
transports (delivery mechanisms) and core (business logic), with a
versioned OpenAPI 3.1 contract published before any HTTP runtime code.

## Decision

**Separate transports from core, consolidate integrations, and publish
the REST contract.**

### 1. Transports layer (`transports/`)

| Transport | Location          | Role                                                   |
| --------- | ----------------- | ------------------------------------------------------ |
| MCP       | `transports/mcp/` | MCP server over stdio, split by tool (was `server.py`) |
| CLI       | `transports/cli/` | CLI split by command group (was 1235-line `cli.py`)    |
| API       | `transports/api/` | OpenAPI 3.1 contract only — no runtime code            |

Every transport validates input, delegates to `core/`, and formats output.
No transport contains business logic. The `core/` layer never imports
from `transports/`.

### 2. Daemon layer (`daemon/`)

`watcher.py` → `daemon/watcher.py`. Long-running background processes
live here, distinct from request-response transports.

### 3. Integrations layer (`integrations/`)

All external-tool wrappers consolidated under `integrations/`:

- `integrations/pdf/` — PDF reader factory + backends (was `readers/`)
- `integrations/azure.py` — Azure Document Intelligence (was `azure_reader.py`)
- `integrations/magika.py` — Magika file-type detection (extracted from `codebase_map.py`)

### 4. Uniform MCP error contract (L5 fix)

Every MCP tool handler in `transports/mcp/` catches its failures and returns
an error payload carrying `{"status": "error", "message": "..."}`, and never
raises from a tool handler (AGENTS.md gotcha #1). The payload is carried in
the handler's own declared return type, not coerced into a single shape:

- `ingest_documents`, `delete_documents`, and `change_collection_profile`
  return `dict` — the error mapping is returned directly.
- `list_indexed_documents`, `list_collections`, and `search_documents`
  return `list[dict]` — the error is a single-element list containing the
  error mapping.
- `get_codebase_map` returns `str` — the error is the JSON encoding of the
  error mapping.

What is uniform is that a failure is caught, reported with that status and
message, and never raised — not the outer container. The
`ingest_documents` handler — previously the only one without try/except —
was wrapped during the move.

### 5. FastMCP forward-compatibility

The `FastMCP` constructor preserves the `lifespan=` slot (passed a no-op
context manager today). Tool handler signatures do not preclude adding
`ctx: Context` in future. Lifespan/context adoption itself is out of scope.

### 6. Contract-first REST commitment

`transports/api/openapi.yaml` ships before any HTTP code. The REST surface
is reviewed as a document, mapped to existing core operations, and validated
in CI. MCP does not generate REST routes from tool signatures.

### 7. Backward-compatibility shims (superseded)

> **Superseded by ADR-037 (v2.0.0).** The shims below were removed in
> v2.0.0. This section is retained as a historical record of the
> deprecation window only; it does not describe the current code.

Deprecated re-export shims preserved old import paths during the
deprecation window:

- `rag_mcp.server` → `rag_mcp.transports.mcp`
- `rag_mcp.cli` → `rag_mcp.transports.cli`
- `rag_mcp.watcher` → `rag_mcp.daemon.watcher`
- `rag_mcp.azure_reader` → `rag_mcp.integrations.azure`
- `rag_mcp.readers` → `rag_mcp.integrations.pdf`

All shims emitted `DeprecationWarning`. Removal was scheduled for v2.0.0
and completed in ADR-037.

## Consequences

### Positive

- **Transport/core boundary enforced.** `core/` never imports from
  `transports/`. Import-linter contracts (Phase 2) already cover this.
- **CLI navigability.** The 1235-line `cli.py` is split into focused
  modules (~50–150 lines each) by command group.
- **Extensibility visible.** `integrations/pdf/` makes the strategy-folder
  pattern from ADR-020 immediately visible in the tree.
- **REST commitment published.** The OpenAPI 3.1 contract is reviewed,
  CI-validated, and ready for a follow-up implementation change.
- **MCP error contract uniform.** Every handler catches failures and
  returns an error payload in its own declared return type — no silent
  exceptions propagate to the MCP runtime.

### Negative

- **More files to navigate.** The tree is deeper. Mitigated by clear
  naming and the module list in AGENTS.md.
- **Shim maintenance burden** (resolved). Six deprecated shims were carried
  until v2.0.0, then removed in ADR-037. Each was <30 lines and re-exported
  only.
- **OpenAPI contract drift risk.** The contract may drift from typed core
  models before the REST implementation lands. Mitigated by CI validation
  and a documented rule that the follow-up change reconciles first.

## Alternatives Considered

| Option                   | Rejected Because                                                                                                                                                              |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Keep flat layout         | The 1235-line `cli.py` and split external wrappers hurt navigability and extensibility.                                                                                       |
| Implement REST now       | The proposal (Decision 6) commits to contract-first; reviewing the OpenAPI document before writing HTTP code catches design issues earlier.                                   |
| Remove shims immediately | Breaking `from rag_mcp.server import ...` consumers (including tests) in the same change as the move is reckless. The deprecation window (v2.0.0) is the established pattern. |

## References

- Refactor proposal: `docs/brainstorm/refactor-proposal/PROPOSAL.md` §5.2, §8
- Architecture diagrams: `docs/brainstorm/refactor-proposal/architecture-diagrams.md`
- OpenSpec change: `openspec/changes/phase-5-refactor-transports-reorganisation/`
- ADR-020: LiteParse PDF Reader (amended for `integrations/pdf/` location)
- ADR-024: Dual Deployment (lazy Azure SDK import preserved)
- ADR-031: Three-Layer Architecture (Config, Core, DI; Phase 2)

---

## Amendment (2026-08-05, ADR-037)

**Two corrections.**

1. **§1 stated that "import-linter contracts (Phase 2) already cover this".**
   They covered four packages. `core.vectordb`, `core.profiles`,
   `core.providers`, `daemon` and `integrations` were uncovered — no
   violation existed, but nothing would have caught one. ADR-037 extends the
   contracts and adds `tests/test_contract_coverage.py`, which fails when a
   package is added without a governing contract.

2. **§3 described Magika as "extracted from `codebase_map.py`".** The
   extraction left a back-import: `integrations/magika.py` imported
   `codebase_map` to keep a test monkeypatch target working, forming a cycle
   and making `integrations/` depend on use-case logic. ADR-037 deletes the
   back-import and inverts the delegation.

The 15 deprecated shims this ADR scheduled for removal at v2.0.0 are removed
in ADR-037, along with `readers/`.
