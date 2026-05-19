## Context

The `rag-mcp` server currently requires manual ingestion via `rag-mcp ingest <path>` or the `ingest_documents` MCP tool. For users who accumulate documents in a known directory (e.g. Zotero storage, project doc folders), this creates a maintenance burden — the index gradually goes stale unless they remember to re-run ingestion.

The codebase has a clean separation: `server.py` exposes MCP tools, `cli.py` provides CLI subcommands, `ingestion.py` handles the actual indexing pipeline, and `config.py` is the single source of truth for settings. The watcher should follow this pattern as a new module that plugs into the CLI.

The target use case is Zotero's storage layout: `storage/<8-char-hash>/<filename>.pdf`. Each paper gets its own subdirectory. A recursive watch on the top-level `storage/` directory captures new papers automatically.

## Goals / Non-Goals

**Goals:**
- Provide a `rag-mcp watch <path>` CLI command that monitors a directory tree for new/modified documents
- Auto-ingest detected documents using the existing `ingest_path()` pipeline
- Debounce rapid file-system events (e.g. streaming writes) before triggering ingestion
- Deduplicate by file content hash to avoid re-indexing unchanged files
- Graceful shutdown on SIGINT (Ctrl+C) — finish in-flight ingestion, then stop
- Cross-platform: macOS (FSEvents), Linux (inotify), Windows (ReadDirectoryChangesW)

**Non-Goals:**
- Delete tracking — removing stale vectors when a file is deleted (needs a `remove_document` function in `ingestion.py` first; out of scope for v1)
- MCP tool mode — starting/stopping a watcher from an MCP tool introduces background-thread lifecycle complexity that doesn't fit the stdio request/response model. CLI-only for v1.
- Web UI or dashboard — pure terminal-based
- Watching remote/S3/gcs paths — local filesystem only
- Initial bulk scan — use `rag-mcp ingest` for that; the watcher is for ongoing delta changes

## Decisions

| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|
| **File watching library** | `watchdog` | Python-native, cross-platform, abstracts OS-level APIs (FSEvents / inotify / ReadDirectoryChangesW). Pure Python, 72 code snippets available on Context7, well-maintained. | `fswatch` (CLI tool, not Python-native), `inotify` (Linux-only), `polling` (wasteful, high latency). |
| **Deployment mode** | CLI command only | Simple lifecycle: start in terminal, Ctrl+C to stop. No threading issues, no MCP server lifecycle conflicts. | MCP tool — risks orphan threads if client disconnects. |
| **Debounce strategy** | `threading.Timer` per file path | Each event resets a timer. Ingestion fires only after `N` seconds of quiet for that file. Simple, proven pattern. | `asyncio` delay (requires async handler — watchdog's handler is sync), rate-limiting bucket (over-engineered for file events). |
| **Deduplication** | In-memory SHA-256 cache | Fast, no external storage needed. Cache lives in the process — ephemeral (watcher restart re-hashes). SHA-256 is more portable than MD5 (works in FIPS-compliant Python builds where `hashlib.md5` is unavailable). File hashing is I/O-bound, so the algorithm choice makes no measurable difference. | ETag/timestamp (unreliable across OS writes), persistent hash DB (overkill for a long-running terminal process), MD5 (unavailable in FIPS-compliant Python). |
| **Event types** | `on_created` + `on_modified` | Covers new files and overwritten files. `on_closed` (file closed after write) is also considered for macOS where `on_modified` fires during active writes. Both events route through the same debouncer. | `on_any_event` (too noisy — would fire on directory changes, permission changes). |
| **File filtering** | `PatternMatchingEventHandler` with supported extensions | Reuses `SUPPORTED_EXTENSIONS` from `config.py`. Ignores hidden files, temp files, and `.git` directories. | Manual `if` checks in `on_any_event` (fragile, duplicates logic). |
| **Graceful shutdown** | Watcher-owned shutdown sequence: cancel timers → wait in-flight → set flag → stop observer | The watcher SHALL NOT rely on `_shutdown_requested` as its primary shutdown mechanism because `ingest_path()` unconditionally clears the flag at the start of every call (`ingestion.py:488`). Sequence: (1) cancel all pending `threading.Timer` callbacks to prevent new `ingest_path()` calls, (2) wait for any in-flight `ingest_path()` to complete naturally (single-file, will finish), (3) set `_shutdown_requested` as belt-and-suspenders for the in-flight call, (4) stop the watchdog `Observer`, (5) exit. | Reusing `_shutdown_requested` alone (race condition — `ingest_path()` clears it); `atexit` (doesn't handle SIGINT well); context manager on Observer (handles SIGINT poorly in daemon threads). |
| **Ingestion throttling** | `threading.BoundedSemaphore` limiting concurrent `ingest_path()` calls | Under batch file events (e.g. copying 500 PDFs into the watched directory), one `threading.Timer` is created per file. Without throttling, hundreds of timers could fire near-simultaneously, all calling `ingest_path()` and contending for the embedding pipeline. A `BoundedSemaphore(2)` in the watcher limits concurrent ingestions to 2, matching the pattern already used for `_embed_semaphore` in `ingestion.py:31`. Excess events queue naturally behind their timers. | Single-worker queue (more complex, fine for v2); no throttling (risk of thread explosion under batch events). |
| **Error recovery** | Log and track consecutive failures; no autonomous retry | When `ingest_path()` fails (e.g. Ollama unavailable, corrupt file), the watcher logs the failure at WARNING level and continues watching. The file hash is NOT updated in the cache, so the next `modified` event will trigger a fresh attempt. If N consecutive failures (default 5) are all `ConnectionError` (Ollama unreachable), the watcher logs a CRITICAL message recommending the user check Ollama and restart the watcher. Autonomous retry loops are out of scope for v1. | Autonomous retry with backoff (complex, risks infinite loops if Ollama is permanently down); silent failure (data loss risk). |

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **False positives from temp files** | Medium | Low | `PatternMatchingEventHandler` with `ignore_patterns` for `~$*` (Office temp), `.tmp`, `.part` (incomplete downloads) |
| **Double-ingestion on macOS FSEvents** | High | Low | macOS fires both `on_created` and `on_modified` for a new file. The debounce timer absorbs this — second event resets the timer, single ingestion fires after quiet window |
| **Zotero writes PDF in fragments** | Medium (large PDFs) | Low | Debounce window (default 2s) should be calibrated for Zotero's write pattern. If problematic, expose `--debounce` flag for user tuning |
| **Watcher misses file during observer startup** | Low | Low | Files created between `observer.start()` and the first event loop iteration may be missed. Acceptable — user runs an initial `ingest` first, and the watcher catches subsequent changes |
| **Memory growth from hash cache** | Very low | Very low | Each entry is ~40 bytes (path + hash). Even at 100K files, ~4 MB. Trivially fine |
| **Concurrent CLI commands** | Low | Medium | Running `rag-mcp watch` and `rag-mcp ingest` simultaneously on the same directory could cause ChromaDB write contention. The existing `_write_lock` in `ingestion.py` serializes writes **within a process**, but two separate processes do not share the lock. ChromaDB's `PersistentClient` uses SQLite which provides its own file-level locking, but this should be documented as a concurrency risk. Same applies to `rag-mcp watch` + MCP server (`rag-mcp` with no args) both writing to the same ChromaDB. Warn in docs. |
| **Ollama (embedding service) unreachable** | Medium | High | If Ollama is not running when the watcher fires ingestion, `ingest_path()` fails with `ConnectionError`. The file is NOT retried unless later modified (hash cache is not updated on failure). Consecutive-`ConnectionError` detection (default 5 failures) logs CRITICAL to alert the user. Documents the behaviour in `--help`. |
| **Timer thread accumulation under batch events** | Medium (bulk imports) | Medium | Mass file creation (e.g. importing 500 papers into Zotero) creates one `threading.Timer` per file. Without throttling, all could fire near-simultaneously. Mitigated by `BoundedSemaphore(2)` in the watcher limiting concurrent `ingest_path()` calls. |
| **File deleted during debounce window** | Medium | Low | If a file is created, triggers a debounce timer, then is deleted before the timer fires, `ingest_path()` returns "Path not found." The watcher catches this and logs DEBUG (not WARNING) — it's a normal race condition, not an error. |
| **Cold-start re-ingestion of unchanged files** | Low (on restart) | Low | The hash cache is ephemeral (in-memory only). After a watcher restart, the first `modified` event for an unchanged file will re-hash, re-chunk, and re-embed it unnecessarily. ChromaDB's upsert behaviour means this is wasteful but not harmful (no duplication). Acceptable for v1 — persistent cache is a v2 optimisation. |
| **FIPS-compliant Python builds** | Very low | High (crash) | Resolved: SHA-256 chosen over MD5 specifically for FIPS portability. `hashlib.md5` is unavailable in FIPS-compliant Python (raises `ValueError`); `hashlib.sha256` works everywhere.
