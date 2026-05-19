## Why

The `add-file-watcher` change was successfully implemented and archived, but a thorough code review and security audit identified 10 issues ranging from a production-critical shutdown hang to a symlink-based information disclosure vulnerability. These must be resolved before the file watcher is safe for production deployment.

## What Changes

**Production-critical fixes (must-fix):**
- Add a 30-second timeout to the `stop()` in-flight wait loop to prevent permanent shutdown hangs when Ollama is unresponsive mid-embedding
- Validate that resolved file paths are within the watch root to block symlink-based path traversal and arbitrary file ingestion
- Distinguish `ConnectionError` from other `RuntimeError` failures in `ingestion.py` so the watcher does not log false-positive CRITICAL "Ollama unreachable" alerts
- Add `error_type: "file"` and `message` fields when all files fail during ingestion (currently silent — watcher logs "unknown error")
- Clean up stale timer entries on `OSError` during file hashing to prevent gradual memory leaks

**Nice-to-have hardening:**
- Protect the `_consecutive_errors` counter with a `threading.Lock` to prevent lost increments under concurrent access
- Merge adjacent `_timers_lock` acquisitions into a single block for cleaner code
- Add a configurable maximum file size check in `_sha256_file` to prevent DoS from multi-gigabyte files
- Add an `LRU` eviction policy or size cap to `_hash_cache` for very long-running watchers
- Harden `test_stop_waits_for_in_flight` with a polling timeout instead of a fixed `time.sleep(0.2)`

## Capabilities

### New Capabilities

*(None — this change hardens existing functionality.)*

### Modified Capabilities

- `watch-command`: Multiple requirement additions for production hardening — shutdown timeout, symlink traversal protection, improved error classification, timer entry cleanup, thread-safe error counter, file size limit, hash cache size cap, and flaky test hardening.

## Impact

| Area            | Impact                                                                                                                 |
| --------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Source**          | `src/rag_mcp/watcher.py` — 8 functional changes; `src/rag_mcp/ingestion.py` — error classification + missing message fix   |
| **Tests**           | `tests/test_watcher.py` — new tests for timeout, symlink traversal, error_type distinction, OSError cleanup, file size limit, flaky test hardening; `tests/test_ingestion.py` — possible new tests for missing error fields |
| **ChromaDB**        | No schema change. No data migration needed.                                                                            |
| **Breaking**        | None. All changes are additive (new validation, new logging) or behavioural corrections under existing interfaces.      |
| **MCP tools**       | No change to tool schemas or behaviour.                                                                                |
| **Documentation**   | Update ADR-010 with post-review hardening decisions.                                                                   |
