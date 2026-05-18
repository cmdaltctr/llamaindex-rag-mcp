# Tasks: CLI Interface & Parallel Ingestion

**Change ID**: `add-cli-and-parallel`

## Phase 1: Foundation — CLI Framework & Config

- [ ] Add `typer` dependency: `uv add typer`
- [ ] Add `EMBED_BATCH_SIZE`, `INGEST_WORKERS`, `EMBED_CONCURRENCY` to `config.py`
- [ ] Change default `embed_batch_size` from 10 to 100 in `config.py`
- [ ] Create `src/rag_mcp/cli.py` with Typer app skeleton and `ingest`, `search`, `list` stubs
- [ ] Update `pyproject.toml` `[project.scripts]` so `rag-mcp` entry point detects CLI vs MCP mode
- [ ] Modify `server.py:main()` to check `sys.argv` and delegate to CLI when args present
- [ ] Update `.env.example` with `EMBED_BATCH_SIZE`, `INGEST_WORKERS`, `EMBED_CONCURRENCY`
- [ ] Verify `--help` output is discoverable and accurate for all subcommands
- [ ] Verify `rag-mcp` with no args still starts MCP server (backward compatibility)

## Phase 2: Ingestion Refactor

- [ ] Extract `_read_and_chunk_file(path: Path) -> list[Node]` in `ingestion.py`
- [ ] Refactor `ingest_path()` to use extracted function (no behaviour change yet)
- [ ] Write unit tests for `_read_and_chunk_file` with MockEmbedding
- [ ] Verify existing ingestion tests still pass

## Phase 3: Parallel File Processing

- [ ] Add `_ingest_parallel(files, workers, progress_callback)` to `ingestion.py`
- [ ] Implement two-phase pattern: parallel read/chunk → serial embed + write
- [ ] Add `threading.Lock` for ChromaDB write serialisation
- [ ] Add `BoundedSemaphore(2)` gate for Ollama embedding calls
- [ ] Wire `--workers` CLI flag and `INGEST_WORKERS` env var
- [ ] Add per-file error isolation: skip corrupt files, continue with rest
- [ ] Write tests: parallel produces same chunks as sequential
- [ ] Write tests: corrupt file skipped, remaining files indexed
- [ ] Write tests: all files fail returns non-zero exit code

## Phase 4: Progress Reporting

- [ ] Add Rich `Progress` context manager to CLI `ingest` command
- [ ] Implement dual progress bars: file reading + chunk embedding
- [ ] Add non-TTY detection: plain text fallback for pipes/CI
- [ ] Add elapsed time and ETA display
- [ ] Verify progress bars render correctly in iTerm2/Terminal.app
- [ ] Verify plain text output when piped

## Phase 5: Signal Handling & Robustness

- [ ] Register SIGINT handler in CLI `ingest` command
- [ ] Implement graceful shutdown: finish current chunk batch, skip remaining
- [ ] Ensure no partial ChromaDB writes on interrupt
- [ ] Add interrupt message: "Ingestion interrupted after N/M files"
- [ ] Write test: Ctrl+C during ingestion leaves clean state
- [ ] Handle `--workers` clamping (negative → 1, 0 → 1)

## Phase 6: CLI Polish & Integration

- [ ] Wire `rag-mcp search` command to `retrieval.search()`
- [ ] Wire `rag-mcp list` command to `ingestion.list_documents()`
- [ ] Add `--rerank` flag to search CLI command
- [ ] Add `--chunk-size` and `--chunk-overlap` options to ingest CLI
- [ ] Add `--threshold` option to search CLI
- [ ] Add `--top-k` option to search CLI
- [ ] Format search output nicely (table with Rich or aligned columns)
- [ ] Add `--json` flag to all commands for machine-readable output
- [ ] Test shell completion installation (`--install-completion`)
- [ ] Verify all CLI commands work when ChromaDB is empty
- [ ] Verify all CLI commands work when Ollama is unreachable (clear error)

## Phase 7: Documentation & Final Verification

- [ ] Update `README.md` with CLI usage examples
- [ ] Update `AGENTS.md` with CLI conventions
- [ ] Run full test suite: `uv run pytest -m "not slow" -v`
- [ ] Run coverage report: `uv run pytest -m "not slow" --cov=rag_mcp`
- [ ] Manual smoke test: ingest Zotero storage directory
- [ ] Manual smoke test: search Zotero storage
- [ ] Manual smoke test: list indexed documents
- [ ] Verify all existing tests still pass without modification
