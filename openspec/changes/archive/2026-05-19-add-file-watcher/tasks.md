## 1. Dependency & Module Setup

- [x] 1.1 Add `watchdog` to `pyproject.toml` under `[project.dependencies]`
- [x] 1.2 Create `src/rag_mcp/watcher.py` with the module skeleton and imports
- [x] 1.3 Expose `watch` subcommand via `cli.py` with Typer argument and options (`--debounce`, `--verbose`)
- [x] 1.4 Register `watch` in `cli.py`'s `@app.command()` (import from `watcher`)

## 2. Core Watcher Implementation

- [x] 2.1 Implement `DocumentIngestHandler(PatternMatchingEventHandler)` class with:
  - `patterns` derived from `SUPPORTED_EXTENSIONS` in `config.py`
  - `ignore_patterns` for hidden files, temp files (`~$*`, `*.tmp`, `*.part`), `.git`
  - `ignore_directories=True`
- [x] 2.2 Implement `on_created` handler — route file creation events to debounced ingest
- [x] 2.3 Implement `on_modified` handler — route file modification events to debounced ingest
- [x] 2.4 Implement per-file debounce using `threading.Timer` (configurable interval, default 2s)
- [x] 2.5 Implement SHA-256 content-hash cache and deduplication check before ingestion. Do NOT update the hash on ingestion failure.
- [x] 2.6 Implement ingestion throttling via `threading.BoundedSemaphore(2)` to limit concurrent `ingest_path()` calls
- [x] 2.7 Wire the handler to call `ingestion.ingest_path(single_file_path)` on debounced events, with the semaphore acquired before the call
- [x] 2.8 Add logging with classified error levels: INFO (ingest start/success), WARNING (ingest failure except `FileNotFoundError`), DEBUG (skips, timer resets, file-not-found-during-debounce), CRITICAL (5 consecutive `ConnectionError` failures)
- [x] 2.9 Replace fragile ConnectionError string-matching in `_do_ingest()` (currently `"cannot connect" in error_msg.lower()`) with an explicit `error_type` contract. Add `error_type` field to `ingestion.py`'s error response dict (e.g. `"error_type": "connection"` vs `"error_type": "file"`) so the watcher can branch on `result.get("error_type")` instead of substring-matching the message. If changing `ingestion.py`'s return shape is out of scope, at minimum add a `# NOTE:` comment above the string-matching documenting its fragility.
- [x] 2.10 Move `import time` from inside `stop()` method (line ~243) to the module-level imports at the top of `watcher.py`.
- [x] 2.11 Document the potential hash-cache race condition in a code comment above the `_hash_cache` dict declaration: with `BoundedSemaphore(2)`, two threads can concurrently compute the hash for the same file, both see it as changed, and both call `ingest_path()` before either updates the cache. This results in at most one wasted embedding (ChromaDB upsert is idempotent). Acceptable for v1 — a `threading.Lock` around the cache read/update would close the window but adds complexity.

## 3. Graceful Shutdown & Lifecycle

- [x] 3.1 Implement `stop()` method that: cancels all pending `threading.Timer` callbacks, waits for any in-flight `ingest_path()` to complete (tracked via a counter or threading.Event), sets `_shutdown_requested` as belt-and-suspenders, then stops the watchdog `Observer`
- [x] 3.2 Add SIGINT handler in the `watch` CLI subcommand: (1) cancel timers → (2) wait in-flight → (3) set shutdown flag → (4) stop observer → (5) exit 0
- [x] 3.3 Do NOT rely on `_shutdown_requested` as the primary shutdown mechanism — the watcher must cancel its own timers first to prevent new `ingest_path()` calls (which would clear the flag)

## 4. CLI Plumbing

- [x] 4.1 Add `rag-mcp watch --help` output with meaningful description, argument, and option docs
- [x] 4.2 Validate the path argument early (fail fast on non-existent directory)
- [x] 4.3 Print warm welcome message to stderr: `Watching <path> for document changes…`
- [x] 4.4 Log ingestion outcomes in human-readable format (filename, chunk count, elapsed time)

## 5. Testing

- [x] 5.1 Write `tests/test_watcher.py` with mocks for `Observer`, `FileSystemEvent`, `threading.Timer`, and `ingest_path`
- [x] 5.2 Test that `on_created` with a supported PDF triggers `ingest_path` after debounce (mock `threading.Timer` to fire immediately)
- [x] 5.3 Test that `on_modified` with identical content (same SHA-256 hash) skips ingestion
- [x] 5.4 Test that `on_modified` with different content (changed hash) triggers ingestion
- [x] 5.5 Test that unsupported extensions (`.png`, `.tmp`, `.DS_Store`, `~$temp.docx`, `.gitkeep`) are ignored
- [x] 5.6 Test that rapid successive events are debounced to a single ingestion (mock `threading.Timer` to verify timer reset behaviour)
- [x] 5.7 Test graceful shutdown: `stop()` cancels all pending timers and waits for in-flight ingest via tracker
- [x] 5.8 Test `--debounce` flag overrides the default interval; reject `--debounce 0` (must be ≥ 0.5s)
- [x] 5.9 Test that `ingest_path()` raising `ConnectionError` logs WARNING, does NOT update hash cache, and increments consecutive failure counter
- [x] 5.10 Test that 5 consecutive `ConnectionError` failures trigger a CRITICAL-level log
- [x] 5.11 Test file deleted during debounce: `ingest_path()` raises `FileNotFoundError` → watcher logs DEBUG, removes hash entry, no crash
- [x] 5.12 Test `ingest_path()` raising generic `Exception` (corrupt file) logs WARNING, hash NOT updated, watcher continues
- [x] 5.13 Test watcher started on an empty directory: blocks, no errors, no ingestion calls
- [x] 5.14 Test ingestion throttling: with `BoundedSemaphore(2)`, 5 simultaneous events result in at most 2 concurrent `ingest_path()` calls
- [x] 5.15 Test `_sha256_file` raising `OSError` (e.g. permission denied) → WARNING logged, watcher continues, no crash. Mock `_sha256_file` with `side_effect=OSError("Permission denied")`.
- [x] 5.16 Test `--verbose` flag: calling `watch_directory(path, verbose=True)` sets `rag_mcp.watcher` logger level to `DEBUG`.
- [x] 5.17 Run `uv run pytest tests/test_watcher.py -m "not slow" --cov=rag_mcp.watcher --cov-report=term-missing` and confirm `watcher.py` coverage ≥ 90% (the module-specific target; overall project coverage is lower due to untested CLI paths like `benchmark` and search pretty-printing — these were never at 95% and are out of scope for this change).
- [x] 5.18 Mark debounce-timing integration test as `@pytest.mark.slow` (uses real `threading.Timer` with `time.sleep`)

## 6. Documentation

- [x] 6.1 Update CLI help text in `cli.py` for the `watch` subcommand, including `--debounce` and behaviour notes (no autonomous retry, cold-start gap)
- [x] 6.2 Add usage example to README or relevant docs: running initial ingest before starting watcher, Zotero storage path example
- [x] 6.3 Document concurrency warnings: (a) avoid running `rag-mcp watch` and `rag-mcp ingest` simultaneously on the same ChromaDB, (b) avoid running `rag-mcp watch` and the MCP server (`rag-mcp` with no args) simultaneously — two processes do not share `_write_lock`
- [x] 6.4 Document cold-start gap: the watcher only detects changes after it starts. Run `rag-mcp ingest <path>` before starting the watcher, and after any period where the watcher was stopped
- [x] 6.5 Review all docstrings, log messages, and CLI output for British English spelling (AGENTS.md requirement)
