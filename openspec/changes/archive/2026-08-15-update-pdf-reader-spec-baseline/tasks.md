## 1. Verification

- [x] 1.1 Confirm `RESOLVED_PDF_READER` and every `RESOLVED_*` constant are absent from `config/` and `compose.py` (v2.0.0 deletion)
- [x] 1.2 Confirm unknown `PDF_READER` values warn and fall back to `auto` in `config/__init__.py`
- [x] 1.3 Confirm `compose.resolve_pdf_reader` is the single startup resolver
- [x] 1.4 Confirm per-file error conversion lives in `core/ingestion/pipeline.py` via `loader.make_file_detail`, and adapters do not catch
- [x] 1.5 Confirm `integrations/pdf/base.py` does not exist and `src/rag_mcp/readers/` is gone
- [x] 1.6 Confirm `liteparse>=2.0.0` is a main project dependency

## 2. Delta authoring

- [x] 2.1 Write MODIFIED env-var-selection requirement (settings field + composition-root resolution)
- [x] 2.2 Write REMOVED transition requirement with Reason and Migration
- [x] 2.3 Write MODIFIED error-dictionary requirement (pipeline-owned conversion)
- [x] 2.4 Write MODIFIED extensibility requirement (registry dispatch, parameterised factory, no shim)
- [x] 2.5 Write MODIFIED auto-default requirement (drop `RESOLVED_PDF_READER` phrasing)

## 3. Validation

- [x] 3.1 Run `openspec validate update-pdf-reader-spec-baseline --strict`
- [x] 3.2 Confirm no runtime files changed (`git status` shows only `openspec/`)
- [x] 3.3 Commit on a feature branch, PR into `v3`, merge after checks
