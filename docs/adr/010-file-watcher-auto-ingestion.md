# ADR-010: File Watcher for Automatic Document Ingestion

**Status**: Accepted
**Date**: 2026-05-19
**Change**: `add-file-watcher`

## Context

The RAG MCP server requires manual invocation of `rag-mcp ingest <path>` (or the `ingest_documents` MCP tool) to index documents. For users who accumulate documents organically in a known directory — notably Zotero's storage layout (`storage/<hash>/<filename>.pdf`) — the index gradually goes stale unless they remember to re-run ingestion periodically.

We needed a mechanism that eliminates this manual step by auto-ingesting new and changed documents as they appear in the filesystem. The solution had to meet several constraints:

1. **No schema changes** — existing ChromaDB vectors must remain untouched
2. **No API keys or cloud services** — all-local operation per project hard boundaries
3. **Cross-platform** — macOS (FSEvents), Linux (inotify), Windows (ReadDirectoryChangesW)
4. **Graceful shutdown** — finish in-flight ingestion on SIGINT without corrupting state
5. **Concurrency-safe** — the watcher and manual `rag-mcp ingest` may share the same ChromaDB
6. **Backward compatible** — all existing CLI commands and MCP tools must continue to work unchanged

## Decision

**Implement a `rag-mcp watch <path>` CLI subcommand using the `watchdog` library, with per-file debouncing, SHA-256 content-hash deduplication, ingestion throttling, consecutive-error detection, and a watcher-owned graceful shutdown sequence.**

### Key design choices

| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|
| **Deployment mode** | CLI command only (`rag-mcp watch`) | Simple lifecycle: start in terminal, Ctrl+C to stop. No threading lifecycle conflicts with the MCP stdio transport. | MCP tool — risks orphan background threads if the client disconnects; async lifecycle management does not fit the request/response model. |
| **File watching library** | `watchdog` (Python-native) | Cross-platform, abstracts OS-level APIs (FSEvents, inotify, ReadDirectoryChangesW). Pure Python, well-maintained. | `fswatch` (CLI, not native), `inotify` (Linux-only), polling (wasteful, high latency). |
| **Debounce strategy** | `threading.Timer` per file path | Each new event for a file resets its timer. Ingestion fires only after the quiet period (default 2s) elapses. Simple, proven pattern. | `asyncio` delay (watchdog's handler is synchronous), rate-limiting bucket (over-engineered for file events). |
| **Deduplication** | In-memory SHA-256 content-hash cache | Fast, no external storage needed. SHA-256 chosen for FIPS portability (`hashlib.md5` is unavailable in FIPS-compliant Python). | ETag/timestamp (unreliable across OS writes), persistent hash DB (overkill for terminal process), MD5 (FIPS-incompatible). |
| **Event types** | `on_created` + `on_modified` | Covers new files and overwritten files. Both route through the same debouncer. | `on_any_event` (too noisy — fires on directory and permission changes). |
| **File filtering** | `PatternMatchingEventHandler` with patterns from `SUPPORTED_EXTENSIONS` (config.py) | Reuses the single source of truth for supported file types. Ignores hidden files (`.*`), Office temp files (`~$*`), generic temp (`*.tmp`, `*.part`), and `.git` directories. | Manual `if` checks in `on_any_event` (fragile, duplicates logic). |
| **Ingestion throttling** | `threading.BoundedSemaphore(2)` limiting concurrent `ingest_path()` calls | Under batch events (e.g., copying 500 PDFs into watched dir), prevents thread explosion. Matches the `_embed_semaphore` pattern already used in `ingestion.py:31`. | Single-worker queue (more complex), no throttling (risk of thread explosion). |
| **Graceful shutdown** | Watcher-owned shutdown sequence: cancel timers → wait in-flight → set `_shutdown_requested` → stop observer → exit | The watcher SHALL NOT rely on `_shutdown_requested` as its primary shutdown mechanism because `ingest_path()` unconditionally clears the flag at the start of every call (`ingestion.py:488`). The watcher cancels its own timers first to prevent new `ingest_path()` calls. | Reusing `_shutdown_requested` alone (race condition — `ingest_path()` clears it), `atexit` (poor SIGINT handling). |
| **Error recovery** | Log and track consecutive failures; no autonomous retry | On failure, file hash is NOT cached → next `modified` event triggers fresh attempt. If 5 consecutive failures are all `ConnectionError` (Ollama unreachable), logs CRITICAL recommending user check Ollama. | Autonomous retry with backoff (complex, risks infinite loops if Ollama is permanently down). |
| **error_type contract** | `ingestion.py` error return dicts include `error_type: "file"`, `"connection"`, or `"embedding"` | The watcher branches on `result.get("error_type")` instead of fragile substring matching on error messages. `"connection"` is raised when Ollama is unreachable (caught as `ConnectionError` in the embedding pipeline). `"embedding"` indicates non-connection embedding failures (model errors, corrupt input) — caught as `RuntimeError`. `"file"` covers path/extension validation failures and the case where all files fail to index. | String matching (`"cannot connect" in error_msg.lower()`) — fragile, language-dependent, breaks on message changes. |

### Architecture

```
cli.py (watch subcommand via Typer)
    │
    ▼
watch_directory(path, debounce, verbose)
    │
    ▼
DocumentIngestHandler(PatternMatchingEventHandler)
    ├── on_created  → _schedule_ingest → threading.Timer → _do_ingest
    ├── on_modified → _schedule_ingest → threading.Timer → _do_ingest
    │                                                           │
    │                                                    SHA-256 hash check
    │                                                    BoundedSemaphore(2)
    │                                                           │
    │                                                    ingest_path(file)
    └── stop()  ← SIGINT handler in watch_directory()
         ├── Cancel all pending threading.Timer callbacks
         ├── Wait for in-flight ingest_path() (30s timeout)
         ├── Set _shutdown_requested (belt-and-suspenders)
         └── Stop watchdog Observer
```

### Key implementation details

- **Hash cache race condition (documented, accepted for v1)**: With `BoundedSemaphore(2)`, two threads can concurrently compute the hash for the same file, both see it as changed, and both call `ingest_path()` before either updates the cache. This results in at most one wasted embedding call. ChromaDB upsert is idempotent, so no data corruption occurs under this race.

- **Consecutive ConnectionError threshold**: The watcher tracks consecutive `ConnectionError` failures. At 5 consecutive failures, it logs CRITICAL recommending the user check Ollama and restart the watcher. Successful ingestion resets the counter to zero.

- **Debug-level logging for normal races**: When a file is deleted between event arrival and debounce completion, the watcher logs at DEBUG level (not WARNING) — this is a normal filesystem race, not an application error.

## Consequences

### Positive

- **Zero-maintenance indexing**: For Zotero users, new papers are automatically indexed as they are added. The RAG index stays current without manual `rag-mcp ingest` commands.
- **No breaking changes**: All existing CLI commands (`ingest`, `search`, `list`), MCP tools (`ingest_documents`, `search_documents`, `list_indexed_documents`), and ChromaDB data are untouched.
- **Cross-platform**: `watchdog` provides native file-event monitoring on all major operating systems.
- **FIPS-compatible**: SHA-256 hashing works on FIPS-compliant Python builds where `hashlib.md5` is unavailable.
- **Graceful shutdown**: Two-phase Ctrl+C (first: cancel timers + wait in-flight; second: force kill) prevents partial ChromaDB writes.
- **Clean separation**: `watcher.py` is self-contained, lazy-imports `ingest_path` to avoid circular dependencies, and only imports `SUPPORTED_EXTENSIONS` from `config.py`.
- **90% test coverage on watcher.py, 49 tests**: covering all error paths, debouncing, throttling, deduplication, shutdown timeout, symlink traversal, error-type classification, file size limit, hash cache eviction, and thread-safe error counting.

### Neutral

- **Ephemeral hash cache**: On watcher restart, the first `modified` event for each unchanged file triggers unnecessary re-hashing and re-embedding. ChromaDB upsert makes this wasteful but not harmful. Persistent cache is a potential v2 optimisation.
- **Cold-start gap**: Files created between `observer.start()` and the first event loop iteration may be missed. Users should run `rag-mcp ingest <path>` before starting the watcher, and after any period where the watcher was stopped.

### Risks

| Risk | Mitigation |
|------|-----------|
| **Concurrent process contention**: Running `rag-mcp watch` and `rag-mcp ingest` (or the MCP server) simultaneously on the same ChromaDB causes write contention. The existing `_write_lock` serialises writes within a process, but separate processes do not share the lock. | Documented as a concurrency warning. ChromaDB's SQLite backing provides file-level locking. |
| **Ollama (embedding service) unreachable**: Files are not retried unless later modified (hash cache not updated on failure). | 5 consecutive ConnectionError failures trigger a CRITICAL log alerting the user. |
| **stop() hang on hung ingestion**: If an in-flight `ingest_path()` call hangs indefinitely (e.g., Ollama becomes unresponsive mid-embedding), the in-flight wait loop could block shutdown indefinitely. | ✅ Fixed in harden-file-watcher — `MAX_SHUTDOWN_SECONDS = 30` deadline-based timeout. On timeout, logs WARNING with abandoned count and force-stops. |
| **Symlink path traversal**: A symlink inside the watched directory pointing outside the watch root allows arbitrary file ingestion. | ✅ Fixed in harden-file-watcher — `Path.relative_to()` containment check validates resolved paths are within the watch root before ingestion. |

## Alternatives Considered

1. **MCP tool mode** — Exposing `watch_directory` as an MCP tool would let clients start a watcher programmatically. Rejected because the MCP stdio transport is request/response, not designed for long-lived background threads. Client disconnection leaves orphan watcher threads.

2. **Polling-based watcher** — Periodically scan the directory for new/modified files. Rejected: high latency (seconds between scans), wasteful CPU/disk I/O, and macOS FSEvents (used by `watchdog`) provides sub-second event delivery with zero polling.

3. **Persistent hash database** — Store content hashes on disk for persistence across watcher restarts. Rejected for v1: adds external storage dependency, increases complexity, and the cold-start re-hashing overhead (~8 chunks/sec) is acceptable for typical libraries (hundreds of files, not millions).

4. **Autonomous retry with backoff** — Automatically retry failed ingestions with exponential backoff. Rejected: risks infinite loops if Ollama is permanently down, requires persistent retry state, and makes the watcher harder to reason about. The v1 approach (fail, log, wait for next `modified` event) is simpler and more predictable.

5. **Delete tracking** — When a file is deleted from the watched directory, remove its vectors from ChromaDB. Rejected for v1: requires a `remove_document` function in `ingestion.py` first, which is out of scope. Stale vectors for deleted files remain in the index (harmless, just consume storage).

## References

- OpenSpec change: `openspec/changes/archive/2026-05-19-add-file-watcher/`
- Post-review hardening: `openspec/changes/harden-file-watcher/`
- Spec: `openspec/specs/watch-command/spec.md`
- Source: `src/rag_mcp/watcher.py`
- Tests: `tests/test_watcher.py`
- CLI integration: `src/rag_mcp/cli.py` (watch subcommand)
- `error_type` contract: `src/rag_mcp/ingestion.py` (ingest_path error returns)
- Config dependency: `src/rag_mcp/config.py` (SUPPORTED_EXTENSIONS)

## Post-Review Hardening

A code review and security audit of the original `add-file-watcher` implementation identified 10 issues across `watcher.py`, `ingestion.py`, and `test_watcher.py`. These were addressed in the `harden-file-watcher` change.

### Production-critical fixes

| # | Fix | Rationale |
|---|-----|-----------|
| 1 | **Shutdown timeout** — Added `MAX_SHUTDOWN_SECONDS = 30` constant and deadline-based timeout in `stop()`'s in-flight wait loop. On timeout, logs WARNING with abandoned count and force-stops. | Prevents permanent shutdown hangs when Ollama is unresponsive mid-embedding. A second Ctrl+C workaround was documented in the original ADR as a known risk. |
| 2 | **Symlink traversal protection** — Added `watch_root` parameter to `DocumentIngestHandler`. `_do_ingest()` resolves the event path and validates `resolved.relative_to(self._watch_root)` before proceeding. | Blocks path-traversal attacks via symlinks pointing outside the watch root. Originally noted as a security risk in the ADR. |
| 3 | **ConnectionError classification** — `_embed_and_write_concurrent()` now catches `ConnectionError` separately from generic `Exception`. `ingest_path()` distinguishes `ConnectionError` (→ `error_type: "connection"`) from `RuntimeError` (→ `error_type: "embedding"`). The watcher's consecutive-error counter only increments for `error_type: "connection"`. | Prevents false-positive CRITICAL "Ollama unreachable" alerts from non-connection embedding failures (model errors, corrupt input). |
| 4 | **Missing error fields** — `ingest_path()` now returns `error_type: "file"` and descriptive `message` when all files fail (`files_idx == 0` with non-empty `files_to_index`). | The watcher previously logged "unknown error" when all files failed — the missing fields made the error indistinguishable from other failures. |
| 5 | **OSError timer cleanup** — `_do_ingest()` now cleans up stale timer entries on `OSError` during file hashing (matching the existing `FileNotFoundError` handler). | Prevents gradual memory leaks from timer entries accumulating for files that cannot be hashed (permission denied, file size exceeded). |

### Hardening

| # | Fix | Rationale |
|---|-----|-----------|
| 6 | **Thread-safe error counter** — Added `self._error_counter_lock = threading.Lock()`. All mutations of `_consecutive_errors` (`+= 1`, `= 0`) are now protected. | Prevents lost increments under concurrent access from multiple `ingest_path()` threads. |
| 7 | **Lock consolidation** — Merged adjacent `_timers_lock` acquisitions in the `FileNotFoundError` handler into a single block. | Cleaner code; avoids an unnecessary unlock/re-lock cycle. |
| 8 | **File size limit** — Added `MAX_FILE_SIZE = 500 * 1024 * 1024` (500 MB). `_sha256_file()` raises `OSError` for files exceeding this limit before reading. | Prevents resource exhaustion from hashing multi-gigabyte files in watched directories. |
| 9 | **Hash cache eviction** — Added `MAX_HASH_CACHE_ENTRIES = 50_000`. When the cache exceeds this size, the oldest entry (by insertion order) is evicted before adding a new one. | Prevents unbounded memory growth in very long-running watchers. Evicted entries are re-hashed on next `modified` event (equivalent to watcher restart). |
| 10 | **Flaky test hardening** — `test_stop_waits_for_in_flight` now uses a polling loop (up to 50 iterations, 0.1s each) instead of a fixed `time.sleep(0.2)`. | Eliminates timing-dependent test failures in CI. |

### Updated risks

The following original ADR risk entries have been mitigated:

| Original Risk | Mitigation Status |
|---------------|-------------------|
| `stop()` hang on hung ingestion (second Ctrl+C workaround) | ✅ Fixed — 30-second timeout with WARNING log |
| Symlink path traversal (arbitrary file ingestion) | ✅ Fixed — `Path.relative_to()` containment check |

### Production Verification

The hardened watcher was tested live against a real Zotero storage directory
(60 items, `/Users/aizat/Zotero/storage`) running `qwen3-embedding:0.6b` via
Ollama.

| Test | Result |
|------|--------|
| Startup | ✅ Embedding model detected, watch path resolved, extensions listed |
| Shutdown (idle) | ✅ SIGINT → "Interrupt received — stopping watcher…" → "Watcher stopped cleanly" → exit 0 |
| Shutdown (in-flight) | ✅ File created during watch, ingestion completed before SIGINT arrived (happy path — below 30s threshold) |
| File detection | ✅ `.md` file created in watched directory detected by FSEvents |
| Debounce | ✅ 2s quiet period elapsed before timer fired |
| SHA-256 hashing | ✅ Hash computed, cache updated on success |
| Ingestion pipeline | ✅ File chunked (1 chunk), embedded via Ollama (HTTP 200), stored in ChromaDB |
| Hash deduplication | ✅ New hash triggered ingestion; hash cache updated (verified via subsequent `modified` event skipping) |
| Graceful shutdown | ✅ "Watcher stopped — all pending work completed" — no abandoned ingestions |

The end-to-end pipeline executed in ~3 seconds (2s debounce + ~1s chunk/embed/store).
The test document appeared in `list_indexed_documents` output with 1 chunk.

*Note: A dimension mismatch (768-dim query embedding vs 1024-dim collection) was
encountered when searching — the collection was originally created with
`qwen3-embedding:8b` (1024-dim) but the current `.env` uses `qwen3-embedding:0.6b`
(768-dim). This is the expected `EMBED_MODEL` constraint documented in AGENTS.md
("⚠️ Ask before mixing embedding models"). The watcher itself ingested correctly;
resolution requires either switching back to the 8b model or re-creating the
collection.*
