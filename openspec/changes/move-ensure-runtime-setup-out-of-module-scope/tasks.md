## Tasks

- [x] 1. Audit every module that imports `rag_mcp.compose` at module scope (entry points, experiment runners, test helpers).
- [x] 2. Remove the module-scope `ensure_runtime_setup()` call from `compose.py`.
- [x] 3. Add an explicit `ensure_runtime_setup()` call to each entry point's startup path.
- [x] 4. Audit `transports/mcp.py` for other module-scope constructions with the same import-time-failure shape.
- [x] 5. Move the `VECTOR_STORE` validation to the same startup-time call for consistency.
- [x] 6. Update `tests/conftest.py` to call `ensure_runtime_setup()` explicitly if needed.
- [x] 7. Test: `rag-mcp --help` succeeds with a valid config (does not trigger embed model construction).
- [x] 8. Test: MCP server startup fails with a clear error on a bad `EMBED_PROVIDER` (not a traceback from deep inside an import chain).
- [x] 9. Test: pytest collection succeeds without calling `ensure_runtime_setup()` (collection should not trigger construction).
