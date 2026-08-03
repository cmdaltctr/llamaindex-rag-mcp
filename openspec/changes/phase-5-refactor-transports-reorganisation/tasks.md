## 1. Preparation

- [ ] 1.1 Create branch `git switch -c feat/phase-5-refactor-transports-reorganisation` (requires Phases 1–4 merged)
- [ ] 1.2 Baseline: `uv run pytest -m "not slow" --cov=rag_mcp` — record pass/coverage as the phase gate

## 2. MCP transport

- [ ] 2.1 Move `server.py` → `transports/mcp.py`; update the `pyproject.toml` entry point and all internal imports
- [ ] 2.2 Fix L5: wrap `ingest_documents` so it returns an error dict on failure; audit every other tool handler for the same contract (none raise)
- [ ] 2.3 Preserve FastMCP forward-compatibility: constructor keeps the `lifespan=` slot (passed `None` today); tool handler signatures do not preclude a future `ctx: Context` parameter (code-inspection check)
- [ ] 2.4 Smoke test: `uv run rag-mcp` (no args) starts the MCP server identically; all tool signatures unchanged

## 3. CLI transport split

- [ ] 3.1 Create `transports/cli/` package; move ingest subcommands to `ingest.py`, search to `search.py`, list to `list.py`, watch to `watch.py`
- [ ] 3.2 Keep shared CLI helpers in `transports/cli/__init__.py` (or a `_common.py` if needed); each module ≤ ~300 lines
- [ ] 3.3 Smoke test every `rag-mcp` subcommand against the pre-refactor CLI behaviour
- [ ] 3.4 Verify CLI output still goes to stderr (gotcha #5 — stdout is the MCP protocol channel)

## 4. Daemon and integrations

- [ ] 4.1 Move `watcher.py` → `daemon/watcher.py`; verify watch behaviour (debouncing, hashing, triggering) unchanged
- [ ] 4.2 Move `readers/` → `integrations/pdf/` with renames (`pypdf_reader.py`→`pypdf.py`, `pypdfium_reader.py`→`pypdfium.py`, `liteparse_reader.py`→`liteparse.py`); create a deprecated `readers/` re-export shim
- [ ] 4.3 Grep gate: zero `rag_mcp.readers` imports in `src/` outside the shim
- [ ] 4.4 Move `azure_reader.py` → `integrations/azure.py`; preserve the lazy Azure SDK import (ADR-024 — no top-level import); verify the PDF factory still dispatches to it
- [ ] 4.5 Extract Magika detection from `codebase_map.py` → `integrations/magika.py`; codebase-map tests pass unmodified
- [ ] 4.6 Amend ADR-020 for the new `integrations/pdf/` location

## 5. REST contract (no runtime code)

- [ ] 5.1 Write `transports/api/README.md` — design, the core-operation mapping table, and the implementation boundary (contract first, HTTP later)
- [ ] 5.2 Write `transports/api/openapi.yaml` (OpenAPI 3.1) covering: `POST /v1/ingestions`, `POST /v1/collections/{collection}/search`, `GET /v1/collections/{collection}/documents`, `GET /v1/collections`, `DELETE /v1/collections/{collection}/documents`, `POST /v1/codebase-maps`, `PATCH /v1/collections/{collection}/profile`
- [ ] 5.3 Every operation has explicit success and error schemas; error envelope matches the MCP error-dict shape; destructive operations (delete, profile change) carry the preview/confirm contract
- [ ] 5.4 Declare at least one `securitySchemes` entry under `components`; every operation references a security requirement or explicitly marks itself unauthenticated
- [ ] 5.5 Document long-running operations (`POST /v1/ingestions`, `POST /v1/codebase-maps`): declare synchronous or asynchronous; if asynchronous, declare `202 Accepted` with a job-resource schema (job ID + status) and a polling endpoint
- [ ] 5.6 Add an OpenAPI validation step to CI (offline validator, dev dependency only)
- [ ] 5.7 Verify `transports/api/` contains no `.py` files

## 6. M8 documentation sweep and acceptance

- [ ] 6.1 Update `AGENTS.md`: architecture invariants #1–#6, gotchas, and the module list rewritten for the final tree (config resolver, `compose.py`, `core/`, `transports/`, `integrations/`, `daemon/`)
- [ ] 6.2 Update `docs/guides/architecture.md` to the final tree
- [ ] 6.3 Write ADR 031 (Transport Separation: MCP / CLI / API)
- [ ] 6.4 Run `uv run pytest -m "not slow" --cov=rag_mcp` — green, coverage thresholds hold
- [ ] 6.5 Verify `from rag_mcp.readers import ...` still resolves via shim with `DeprecationWarning`
- [ ] 6.6 Run `graphify update .` to refresh the knowledge graph
- [ ] 6.7 Run `openspec validate phase-5-refactor-transports-reorganisation --strict`
- [ ] 6.8 Commit (`refactor:`) and open PR with `gh pr create --base main`
- [ ] 6.9 Record the committed follow-up: REST transport implementation change against `openapi.yaml` (new OpenSpec proposal, not started here)
