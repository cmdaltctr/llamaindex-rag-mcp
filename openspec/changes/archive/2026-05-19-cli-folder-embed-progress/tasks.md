## 1. Per-file Tracking in Ingestion

- [x] 1.1 Extend `_ingest_sequential()` and `_ingest_parallel()` to collect per-file results: `{file: str, status: str, chunks: int, error: str | None}`
- [x] 1.2 Add `file_details` key to the return dict of `ingest_path()` containing the per-file list
- [x] 1.3 Write unit test: single file → `file_details` has one entry with status `"indexed"` and `chunks > 0`
- [x] 1.4 Write unit test: folder with a corrupt file → one entry has `status "failed"` with error message

## 2. Structured Per-file Logging

- [x] 2.1 Add INFO-level log line per file in `_ingest_sequential()` and `_ingest_parallel()` with file name, status, and chunk count or error
- [x] 2.2 Verify log output contains per-file lines when running `rag-mcp ingest` on a folder

## 3. Report Generation

- [x] 3.1 Add `--report <path>` option to the `ingest` CLI command in `cli.py`
- [x] 3.2 Implement report generation function: `_write_report(path, result, config)` that writes JSON (`.json` extension) or Markdown (otherwise)
- [x] 3.3 JSON report SHALL include: `timestamp`, `config` (model, batch_size, concurrency, workers, chunk_size, chunk_overlap), `input_path`, `summary` (total, indexed, failed, skipped, chunks), `files` array
- [x] 3.4 Markdown report SHALL include headers: Summary table, Configuration, Per-File Details table
- [x] 3.5 Add warning log when `--report` target file already exists (overwrite)
- [x] 3.6 Ensure no report is written when `--report` is not provided (backward compatible)

## 4. CLI Integration Tests

- [x] 4.1 Test `--report report.json` produces valid JSON with expected structure
- [x] 4.2 Test `--report report.md` produces Markdown with headers and tables
- [x] 4.3 Test without `--report` flag — no report file created
- [x] 4.4 Test `--report` with existing file — file overwritten, warning logged

## 5. Real PDF Integration Test

- [x] 5.1 Create test fixture with 5 sample PDFs (or use Zotero storage paths)
- [x] 5.2 Run `rag-mcp ingest <fixture_dir> --report report.json` and verify report content
- [x] 5.3 Verify all 5 PDFs appear in report with `status "indexed"` and `chunks > 0`

## 6. ADR Documentation

- [x] 6.1 Write `docs/adr/008-cli-folder-embed-progress.md` documenting the folder embedding workflow, report format, and design decisions

## 7. Final Verification

- [x] 7.1 Run full test suite: `uv run pytest -m "not slow" -v`
- [x] 7.2 Run coverage: `uv run pytest -m "not slow" --cov=rag_mcp` — overall ≥ 95%
- [x] 7.3 Manual smoke test: embed 5 PDFs from `/Users/aizat/Zotero/storage` with `--report`
- [x] 7.4 Verify report file is generated and contains correct data
