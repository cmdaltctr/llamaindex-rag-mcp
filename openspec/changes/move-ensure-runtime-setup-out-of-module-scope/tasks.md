## Tasks

- [ ] 1. Audit every module that imports `rag_mcp.compose` at module scope (entry points, experiment runners, test helpers).
- [ ] 2. Remove the module-scope `ensure_runtime_setup()` call from `compose.py`.
- [ ] 3. Add an explicit `ensure_runtime_setup()` call to each entry point's startup path.
- [ ] 4. Audit `transports/mcp.py` for other module-scope constructions with the same import-time-failure shape.
- [ ] 5. Move the `VECTOR_STORE` validation to the same startup-time call for consistency.
- [ ] 6. Update `tests/conftest.py` to call `ensure_runtime_setup()` explicitly if needed.
- [ ] 7. Test: `rag-mcp --help` succeeds with a valid config (does not trigger embed model construction).
- [ ] 8. Test: `rag-mcp --help` fails with a clear error on a bad `EMBED_PROVIDER` (not a traceback from deep inside an import chain).
- [ ] 9. Test: pytest collection succeeds without calling `ensure_runtime_setup()` (collection should not trigger construction).
