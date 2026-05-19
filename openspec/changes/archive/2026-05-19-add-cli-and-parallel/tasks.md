# Tasks: CLI Interface & Parallel Ingestion

**Change ID**: `add-cli-and-parallel`

## Phase 1: Foundation — CLI Framework & Config

- [x] Add `typer` dependency: `uv add typer`
- [x] Add `EMBED_BATCH_SIZE`, `INGEST_WORKERS`, `EMBED_CONCURRENCY` to `config.py`
- [x] Change default `embed_batch_size` from 10 to 100 in `config.py`
- [x] Create `src/rag_mcp/cli.py` with Typer app skeleton and `ingest`, `search`, `list` stubs
- [x] Update `pyproject.toml` `[project.scripts]` so `rag-mcp` entry point detects CLI vs MCP mode
- [x] Modify `server.py:main()` to check `sys.argv` and delegate to CLI when args present
- [x] Update `.env.example` with `EMBED_BATCH_SIZE`, `INGEST_WORKERS`, `EMBED_CONCURRENCY`
- [x] Verify `--help` output is discoverable and accurate for all subcommands
- [x] Verify `rag-mcp` with no args still starts MCP server (backward compatibility)

## Phase 2: Ingestion Refactor

- [x] Extract `_read_and_chunk_file(path: Path) -> list[Node]` in `ingestion.py`
- [x] Refactor `ingest_path()` to use extracted function (no behaviour change yet)
- [x] Write unit tests for `_read_and_chunk_file` with MockEmbedding
- [x] Verify existing ingestion tests still pass

## Phase 3: Parallel File Processing

- [x] Add `_ingest_parallel(files, workers, progress_callback)` to `ingestion.py`
- [x] Implement two-phase pattern: parallel read/chunk → serial embed + write
- [x] Add `threading.Lock` for ChromaDB write serialisation
- [x] Add `BoundedSemaphore(2)` gate for Ollama embedding calls
- [x] Wire `--workers` CLI flag and `INGEST_WORKERS` env var
- [x] Add per-file error isolation: skip corrupt files, continue with rest
- [x] Write tests: parallel produces same chunks as sequential
- [x] Write tests: corrupt file skipped, remaining files indexed
- [x] Write tests: all files fail returns non-zero exit code

## Phase 4: Progress Reporting

- [x] Add Rich `Progress` context manager to CLI `ingest` command
- [x] Implement dual progress bars: file reading + chunk embedding
- [x] Add non-TTY detection: plain text fallback for pipes/CI
- [x] Add elapsed time and ETA display
- [x] Verify progress bars render correctly in iTerm2/Terminal.app
- [x] Verify plain text output when piped

## Phase 5: Signal Handling & Robustness

- [x] Register SIGINT handler in CLI `ingest` command
- [x] Implement graceful shutdown: finish current chunk batch, skip remaining
- [x] Ensure no partial ChromaDB writes on interrupt
- [x] Add interrupt message: "Ingestion interrupted after N/M files"
- [x] Write test: Ctrl+C during ingestion leaves clean state
- [x] Handle `--workers` clamping (negative → 1, 0 → 1)

## Phase 6: CLI Polish & Integration

- [x] Wire `rag-mcp search` command to `retrieval.search()`
- [x] Wire `rag-mcp list` command to `ingestion.list_documents()`
- [x] Add `--rerank` flag to search CLI command
- [x] Add `--chunk-size` and `--chunk-overlap` options to ingest CLI
- [x] Add `--threshold` option to search CLI
- [x] Add `--top-k` option to search CLI
- [x] Format search output nicely (table with Rich or aligned columns)
- [x] Add `--json` flag to all commands for machine-readable output
- [x] Test shell completion installation (`--install-completion`)
- [x] Verify all CLI commands work when ChromaDB is empty
- [x] Verify all CLI commands work when Ollama is unreachable (clear error)

## Phase 7: Documentation & Final Verification

- [x] Update `README.md` with CLI usage examples
- [x] Update `AGENTS.md` with CLI conventions
- [x] Run full test suite: `uv run pytest -m "not slow" -v`
- [x] Run coverage report: `uv run pytest -m "not slow" --cov=rag_mcp`
- [x] Manual smoke test: ingest Zotero storage directory
- [x] Manual smoke test: search Zotero storage
- [x] Manual smoke test: list indexed documents
- [x] Verify all existing tests still pass without modification

## Phase 8: Automated CLI Testing (see `testing.plan.md`)

### A: Foundation — CLI test file setup

- [x] Create `tests/test_cli.py` with `CliRunner`, imports, verify conftest fixtures apply
- [x] Write `TestEntryPoint`: `--version` flag, `--help` flag, unknown subcommand error

### B: CLI output — JSON mode

- [x] `TestIngestCLI`: `--json` success, `--json` error, non-existent path, unsupported extension
- [x] `TestSearchCLI`: `--json` empty store, `--json` with results after ingest
- [x] `TestListCLI`: `--json` empty store, `--json` with documents after ingest
- [x] `TestPrintOllamaError`: console output (stderr contains "Ollama"), JSON output, detail inclusion

### C: CLI output — Rich table mode

- [x] `TestSearchCLI`: table output contains Score, Source, Text column headers; results rendered
- [x] `TestListCLI`: table output contains Source, Chunks columns; total summary displayed
- [x] `TestSanitiseDisplayName`: no ANSI passthrough, strips colour codes, strips cursor movement, empty string

### D: CLI ingest — flags, exit codes, edge cases

- [x] `TestIngestCLI`: `--workers 4`, `--chunk-size 128`, `--chunk-overlap 32`, workers clamped (-5, 0)
- [x] `TestIngestCLI`: success exit code 0, error exit code 1, success message format
- [x] `TestIngestCLI`: `--help` includes all options
- [x] `TestSearchCLI`: `--top-k`, `--threshold`, `--rerank` flags, `--help` includes all options

### E: Progress reporting

- [x] `TestProgressReporting`: plain-text "Reading file N/M…" on non-TTY
- [x] `TestProgressReporting`: plain-text "Embedding K chunks…" message
- [x] `TestProgressReporting`: plain-text "Embedding complete" message
- [x] `TestProgressReporting`: `--json` suppresses all progress output

### F: Concurrency & signal edge cases (extend existing test files)

- [x] `test_ingestion_parallel.py`: concurrent `_write_lock` serialises — two threads, only one in critical section
- [x] `test_ingestion_parallel.py`: `BoundedSemaphore` limits to 2 concurrent embeddings
- [x] `test_ingestion_parallel.py`: parallel shutdown via `pool.shutdown(wait=False, cancel_futures=True)`
- [x] `test_signal_handling.py`: double-check lock re-checks `_shutdown_requested` inside `_write_lock`
- [x] `test_signal_handling.py`: `ingest_path()` resolves `~` (expanduser) and `../` (resolve)

### G: Validation & coverage

- [x] Run full suite: `uv run pytest -m "not slow" -v` — all tests pass
- [x] Coverage: `uv run pytest -m "not slow" --cov=rag_mcp` — `cli.py` ≥ 90%, overall ≥ 95%
- [x] Verify no regressions in existing test files
