## Why

`compose.py` calls `ensure_runtime_setup()` at module scope (its last line). After `silent-failure-audit-and-guards` §5 removed the try/except guards around `build_embed_model` and `build_vector_store`, a provider misconfiguration now raises during `import rag_mcp.compose` rather than at a controlled startup point. This is accepted for consistency with `VECTOR_STORE` (which already raised from the same import-time path), but it means:

- `rag-mcp --help` and other commands that never embed anything fail on a bad config.
- Pytest collection (not just execution) breaks for any module importing `compose`.
- Experiment runners that import `compose` at module scope fail before they can report which experiment they were running.
- The `VECTOR_STORE` unknown-value check (ADR-034) has the same shape and should move for the same reason.

Moving the call out of module scope gives true startup-time failure: the error surfaces when the server or CLI actually starts, not when Python resolves an import.

## What Changes

- Remove the module-scope `ensure_runtime_setup()` call from the bottom of `compose.py`.
- Call `ensure_runtime_setup()` explicitly at the start of each entry point: `transports/mcp.py` server startup, `transports/cli/` command dispatch, and experiment runners.
- Audit `transports/mcp.py` for other module-scope constructions that have the same import-time-failure shape.
- For consistency, move the `VECTOR_STORE` validation path to the same startup-time call (it currently raises from a model validator reached through the same import-time path).

## Impact

- **Code**: `src/rag_mcp/compose.py`, `src/rag_mcp/transports/mcp.py`, `src/rag_mcp/transports/cli/`, experiment runners.
- **Tests**: `tests/conftest.py` may need to call `ensure_runtime_setup()` explicitly instead of relying on the import side effect.
- **Risk**: medium — every entry point must call `ensure_runtime_setup()` before any core code runs, or the process continues without an embed model or default store. A missing call is the failure mode this change introduces.

## Filed by

`silent-failure-audit-and-guards` §8.4. This change is the follow-up; it is not implemented by that change.
