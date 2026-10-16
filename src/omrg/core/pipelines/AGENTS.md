# src/omrg/core/pipelines (graph runner)

The pipeline graph model, its validator and its runner.

## What belongs here

- The operation catalogue (`catalogue.py`), adapters (`adapters.py`) and host-owned levers (`levers.py`).

## What it must not import

- `omrg.core.ingestion`, `omrg.core.retrieval`, `omrg.core.answer`, `omrg.core.providers` or `omrg.transports`.
- `subprocess`, `sqlite3`, `fastapi`, `starlette`, `uvicorn` or `marimo`.
- Contract `pipeline-runner-independent-of-domains` enforces both lists.

## Rules

1. Adapters receive every resource and setting through `NodeContext` (`adapters.py`). Never read a process default.
2. A new operation is one adapter in its domain package plus one `catalogue.register()` line. Never branch on operation names.
3. Validate the whole graph before any side effect.
4. A graph cannot override host-owned settings (`levers.py`).

## Links

- [Root AGENTS.md](../../../../AGENTS.md)
- [Architecture guide](../../../../docs/guides/architecture.md)
