## 1. Factory injection and probe alignment

- [ ] 1.1 Write failing tests: `get_pdf_reader` accepts a reader name parameter and performs no composition-root default lookup (assert zero `get_default_effective_settings` references under `integrations/` after the change)
- [ ] 1.2 Write failing test: factory-local `auto` resolution selects `pypdfium2` when `liteparse` is missing and `pypdfium2` is installed (simulate import availability)
- [ ] 1.3 Change `get_pdf_reader(reader: str)` signature; remove the `get_default_effective_settings` import and call
- [ ] 1.4 Replace the local `auto` probe with the `liteparse → pypdfium2 → pypdf` order
- [ ] 1.5 Convert `_pdf_reader_logged` to a set keyed on the reader name; log the backend line once per name
- [ ] 1.6 Update the module docstring and `integrations/pdf/__init__.py` doc note to describe parameter injection

## 2. Call-site threading

- [ ] 2.1 Write failing test: `chunker._read_sync` path passes `resolved.pdf_reader` to the factory (mock the factory and assert the argument)
- [ ] 2.2 Update `core/ingestion/chunker.py` to call `get_pdf_reader(resolved.pdf_reader)`
- [ ] 2.3 Add `pdf_reader` parameter to `read_with_azure_fallback` and `_read_with_local_chain` in `integrations/azure.py` (keyword-only)
- [ ] 2.4 Update the chunker's Azure branch call to pass `resolved.pdf_reader`
- [ ] 2.5 Update `_read_with_local_chain` to call `get_pdf_reader(pdf_reader)`

## 3. Contract and regression tests

- [ ] 3.1 Contract test: factory-local `auto` resolution and `compose._resolve_pdf_reader` produce the same name for the same simulated installed set
- [ ] 3.2 Test: Azure fallback chain uses the caller's reader name, not the process default
- [ ] 3.3 Update existing factory tests that call `get_pdf_reader()` with no argument
- [ ] 3.4 Confirm no new import edges: `integrations/` does not import `compose`; run `uv run lint-imports`
- [ ] 3.5 Verify the fast suite passes with `PDF_READER=pypdf` conftest default unchanged

## 4. Validation and documentation

- [ ] 4.1 Search `docs/guides/` for descriptions of the factory self-fetch; update any that exist
- [ ] 4.2 Run `uv run ruff check` and `ruff format --check`
- [ ] 4.3 Run `openspec validate add-pdf-factory-settings-injection --strict`
- [ ] 4.4 Obtain approval, then run `uv run pytest -m "not slow" --cov=rag_mcp` before committing
