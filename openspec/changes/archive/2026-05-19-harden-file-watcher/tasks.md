## 1. Ingestion Pipeline Hardening

- [x] 1.1 Distinguish `ConnectionError` from `RuntimeError` in `_embed_and_write_concurrent()` — catch `ConnectionError` separately from generic `Exception` in the batch embedding loop. Raise `ConnectionError` for Ollama connectivity issues; raise `RuntimeError` for other embedding failures.
- [x] 1.2 Update `ingest_path()` to catch `ConnectionError` separately (→ `error_type: "connection"`) from `RuntimeError` (→ `error_type: "embedding"`). Both return `{"status": "error", ...}`.
- [x] 1.3 Add `error_type: "file"` and `message` fields when all files fail (`files_idx == 0` with non-empty `files_to_index`) in `ingest_path()`. Message: `"All N file(s) failed to index. See file_details for per-file errors."`.
- [x] 1.4 Update `ingest_path()` docstring to reflect the new `error_type` values (`"file"`, `"connection"`, `"embedding"`).

## 2. Watcher Production Hardening

- [x] 2.1 Add `MAX_SHUTDOWN_SECONDS = 30` constant and implement a deadline-based timeout in `stop()`'s in-flight wait loop. On timeout, log WARNING with count of abandoned in-flight ingestions and break.
- [x] 2.2 Add `watch_root: Path | None` parameter to `DocumentIngestHandler.__init__()`. Store resolved root path.
- [x] 2.3 Implement symlink traversal check in `_do_ingest()`: resolve `path` with `path.resolve(strict=False)`, verify `resolved.relative_to(self._watch_root)`. On `ValueError`, log WARNING "Path traversal blocked" and clean up timer/hash entries. Skip if `watch_root` is None (backward compat).
- [x] 2.4 Update `watch_directory()` to pass the resolved watch path as `watch_root` parameter to `DocumentIngestHandler`.
- [x] 2.5 Add `MAX_FILE_SIZE = 500 * 1024 * 1024` (500 MB) constant. In `_sha256_file()`, check `path.stat().st_size > MAX_FILE_SIZE` before reading; raise `OSError` with descriptive message if exceeded.
- [x] 2.6 Clean up stale timer entry on `OSError` in `_do_ingest()`'s except block — add `with self._timers_lock: self._timers.pop(file_path, None)` matching the `FileNotFoundError` handler.
- [x] 2.7 Add `self._error_counter_lock = threading.Lock()` and protect all mutations of `_consecutive_errors` (`+= 1`, `= 0`).
- [x] 2.8 Update `_do_ingest()` to branch on `error_type == "connection"` for the consecutive-error counter; treat `error_type == "embedding"` (or absent `error_type`) as generic failure.
- [x] 2.9 Add `MAX_HASH_CACHE_ENTRIES = 50_000` constant. In `_do_ingest()`, when adding a new hash entry, check cache size and evict the oldest entry if exceeded (Python 3.7+ dict insertion order).
- [x] 2.10 Merge adjacent `_timers_lock` acquisitions in the `FileNotFoundError` handler into a single block (remove the redundant lock/unlock cycle).

## 3. Testing

- [x] 3.1 Test `stop()` timeout: mock `ingest_path` to sleep forever; assert `stop()` completes within the timeout (not hanging indefinitely). Verify WARNING log emitted with abandoned count.
- [x] 3.2 Test symlink traversal blocked: create a handler with `watch_root`, mock `_sha256_file` to return a hash, trigger an event where `path.resolve()` returns `/etc/passwd`. Assert `ingest_path` NOT called and WARNING log emitted.
- [x] 3.3 Test symlink traversal allowed: create a handler with `watch_root`, mock `_sha256_file`, trigger an event where the resolved path IS within the watch root. Assert `ingest_path` IS called.
- [x] 3.4 Test `error_type: "connection"` from `ingest_path()` increments `_consecutive_errors` and triggers CRITICAL after 5.
- [x] 3.5 Test `error_type: "embedding"` from `ingest_path()` does NOT increment `_consecutive_errors` (consecutive counter stays 0 or resets).
- [x] 3.6 Test `error_type: "file"` from `ingest_path()` logs WARNING and does NOT increment `_consecutive_errors`.
- [x] 3.7 Test that `ingest_path()` returns `error_type: "file"` and `message` when all files fail.
- [x] 3.8 Test file size limit: mock `_sha256_file` to raise `OSError("File exceeds maximum size")` and verify WARNING log emitted.
- [x] 3.9 Test hash cache eviction: populate cache beyond `MAX_HASH_CACHE_ENTRIES`, assert oldest entry evicted, new entry present.
- [x] 3.10 Harden `test_stop_waits_for_in_flight`: replace `time.sleep(0.2)` with a polling loop (up to 50 iterations, 0.1s each) that waits for `handler.in_flight_count > 0` before asserting.
- [x] 3.11 Run `uv run pytest tests/test_watcher.py -m "not slow" --cov=rag_mcp.watcher --cov-report=term-missing` and confirm coverage remains ≥ 90%.
- [x] 3.12 Run full test suite `uv run pytest -m "not slow"` and confirm all tests pass.

## 4. Documentation

- [x] 4.1 Update ADR-010 `docs/adr/010-file-watcher-auto-ingestion.md` with a "Post-Review Hardening" section listing the 10 fixes applied and their rationale.
- [x] 4.2 Review all new/modified docstrings and log messages for British English spelling (AGENTS.md requirement).
