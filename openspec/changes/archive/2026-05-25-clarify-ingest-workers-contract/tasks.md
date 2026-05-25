## 1. Code and Config Cleanup (Hard Remove)

- [x] 1.1 Remove the `--workers/-w` option and its clamping logic from `rag-mcp ingest` in `cli.py`.
- [x] 1.2 Remove the `workers` field from the ingest report JSON output.
- [x] 1.3 Remove `INGEST_WORKERS` constant from `config.py`.
- [x] 1.4 Remove `INGEST_WORKERS` entry from `.env.example`.
- [x] 1.5 Remove the `workers` parameter from `ingest_path_async()` signature in `ingestion.py` and update all internal call sites.
- [x] 1.6 Update `rag-mcp ingest` help text and docstring to direct users to `EMBED_BATCH_SIZE` and `EMBED_CONCURRENCY` for throughput tuning.

## 2. Tests and Docs

- [x] 2.1 Update CLI tests that pass `--workers` or assert on `workers` in help/report output (remove the assertions; add a negative test that `--workers` errors).
- [x] 2.2 Update ingestion tests that call `ingest_path_async(..., workers=...)` to drop the keyword.
- [x] 2.3 Remove or update any documentation mentioning `INGEST_WORKERS` or file-reader workers.

## 3. Verification and Release

- [x] 3.1 Run CLI and ingestion test suites (`uv run pytest -m "not slow" -v`).
- [x] 3.2 Confirm `uv run rag-mcp ingest --help` no longer shows `--workers`.
- [x] 3.3 Confirm `uv run rag-mcp ingest ./docs --workers 4` exits with a "No such option" error.
- [x] 3.4 Validate the OpenSpec change.
- [x] 3.5 When committing, use `feat!:` prefix or include a `BREAKING CHANGE:` footer so `python-semantic-release` performs the correct version bump.
