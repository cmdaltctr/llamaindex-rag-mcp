# Pre-change baseline

Recorded on branch `refactor/complete-architecture-v2-conformance` off `main`
at commit `113bac9` (2026-08-05), before any conformance work began.

## Coverage (`uv run pytest -m "not slow" --cov=rag_mcp`)

- **TOTAL**: 4114 statements, 506 missed, **88%** overall
- **925 passed, 8 deselected, 29 warnings** in ~96s

### Per-tier highlights (current paths, pre-relocation)

| Tier | Module | Stmts | Miss | Cover |
| --- | --- | --- | --- | --- |
| Core+MCP | `core/ingestion/*` | — | — | 93–100% |
| Core+MCP | `core/retrieval/*` | — | — | 94–100% |
| Core+MCP | `core/metadata/*` | — | — | 49–100% (`extractor.py` 49%) |
| Core+MCP | `core/vectordb/chroma.py` | 150 | 7 | 95% |
| Core+MCP | `transports/mcp.py` | 129 | 29 | 78% |
| Orchestration | `daemon/watcher.py` | 243 | 29 | 88% |
| Orchestration | `transports/cli/*` | — | — | 18–100% (`profile.py` 18%) |
| Top-level (to be relocated) | `code_graph.py` | 258 | 51 | 80% |
| Top-level (to be relocated) | `doc_graph.py` | 247 | 27 | 89% |

> Full per-module table is in the `--cov-report=term` output above; this
> captures the tiers the group 12 diff will attribute against.

## `uv run lint-imports`

```
Analyzed 93 files, 177 dependencies.
Contracts: 3 kept, 0 broken.
  - settings-models-are-pure-data KEPT
  - providers-constructed-only-in-compose KEPT
  - core-business-avoids-providers-transports KEPT
```

## Files over 400 lines under `src/rag_mcp/`

| Lines | File |
| --- | --- |
| 690 | `src/rag_mcp/code_graph.py` |
| 663 | `src/rag_mcp/codebase_map.py` |
| 576 | `src/rag_mcp/config/__init__.py` |
| 562 | `src/rag_mcp/doc_graph.py` |
| 550 | `src/rag_mcp/daemon/watcher.py` |
| 420 | `src/rag_mcp/transports/mcp.py` |

Five of these exceed the 500-line ceiling (all except `transports/mcp.py` at 420).

## Test suite size

- **933 tests collected** (`uv run pytest --collect-only -q`)
- **38 test files** under `tests/`
- **925 passed, 8 deselected** (slow marker)

## Tests patching `rag_mcp.config.settings`

- **15 test files** reference `rag_mcp.config.settings` / `config.settings` /
  patch a settings attribute — the group 11 migration scope.
