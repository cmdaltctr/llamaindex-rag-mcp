# Tasks: Thread settings through Magika content-type detection

## 1. Regression tests first

- [ ] 1.1 Write a failing regression test: ingesting a small fixture through `ingest_path_async` with explicitly injected settings (no process-global default installed) produces no "Magika detection failed" warning and yields a populated `content_type` (or the documented "CLI not installed" warning when the binary is absent). Confirm it FAILS on current code.
- [ ] 1.2 Write a unit test: `_magika_binary(settings=...)` returns the injected `magika_binary` and never calls `get_default_effective_settings` (assert via a raising stub on the global getter).

## 2. Implementation

- [ ] 2.1 Add the optional `settings` parameter to `integrations/magika.py` (`_magika_binary`, `_is_magika_available`, `scan_with_magika`) and read `settings.magika_binary` when provided.
- [ ] 2.2 Thread the parameter through `codebase_map.detect_file_types`.
- [ ] 2.3 Pass `settings=resolved_settings` at the `detect_file_types` call site in `core/ingestion/pipeline.py`.
- [ ] 2.4 Pass the boundary-resolved `effective` into `detect_file_types` inside `generate_codebase_map`.

## 3. Verification

- [ ] 3.1 Run the new tests; confirm the regression test from 1.1 now passes.
- [ ] 3.2 Run the fast suite (`uv run pytest -m "not slow"`) and `scripts/local_ci.sh` gates for the touched modules (ruff, import-linter, OpenSpec strict validation).
- [ ] 3.3 Update `docs/guides/` only if any guide documents the Magika fallback path (grep for "Magika" and correct drift; none expected).
