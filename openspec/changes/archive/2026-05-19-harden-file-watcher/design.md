## Context

The `add-file-watcher` change was implemented and archived (ADR-010). A subsequent security audit and code review identified 10 issues — 5 production-critical and 5 nice-to-have — across `watcher.py`, `ingestion.py`, and `test_watcher.py`. This change addresses them in a single hardening pass.

Key constraints:
- All changes must be backward-compatible with the existing `watch` CLI interface
- No breaking changes to `ingest_path()` return shape (fields are additive)
- Must maintain ≥ 90% coverage on `watcher.py`
- All AGENTS.md conventions apply: British English, type annotations, Google-style docstrings, no PyTorch

## Goals / Non-Goals

**Goals:**
- Prevent permanent shutdown hangs when Ollama is unresponsive mid-ingestion
- Block symlink-based path traversal outside the watch root
- Distinguish true `ConnectionError` from other embedding failures for accurate CRITICAL alerting
- Ensure every error path in `ingest_path()` returns both `error_type` and `message`
- Prevent memory leaks from stale timer entries and unbounded `_hash_cache` growth
- Protect against DoS via multi-gigabyte files in watched directories
- Make `_consecutive_errors` counter thread-safe under concurrent access
- Remove flaky test timing dependencies

**Non-Goals:**
- Persistent hash cache (v2 optimisation)
- Autonomous ingestion retry (v2 feature)
- Delete tracking for removed files (v2 feature)
- Changing the `BoundedSemaphore(2)` throttling model
- Adding an MCP tool mode for the watcher

## Decisions

### 1. Shutdown timeout: fixed 30-second grace period

**Choice**: Add a hardcoded 30-second timeout to the `while True` in-flight wait loop in `stop()`. On timeout, log WARNING with the count of abandoned in-flight ingestions and break.

**Alternatives considered**:
- *Configurable timeout via `--shutdown-timeout` flag*: Rejected — a watch subcommand with a shutdown-only flag is surprising UX. The timeout is an internal safety net, not a user-facing feature.
- *Force-kill in-flight ingestion (Thread.terminate-like)*: Rejected — Python has no safe thread termination. Force-killing could leave ChromaDB in an inconsistent state.

**Rationale**: 30 seconds is generous for a single-file `ingest_path()` call (typical ~14s for a 117-chunk PDF, 8.35 chunks/sec). If it hasn't completed within 30 seconds, Ollama is unresponsive and waiting longer won't help.

### 2. Symlink traversal: `Path.relative_to()` containment check

**Choice**: In `_do_ingest()`, after constructing `path = Path(file_path)`, resolve it with `path.resolve(strict=False)` and assert `resolved.relative_to(self._watch_root)`. On `ValueError`, log WARNING with "Path traversal blocked" and clean up timer/hash entries.

The `DocumentIngestHandler.__init__` SHALL accept an optional `watch_root: Path | None` parameter, defaulting to `None` for backward compatibility in tests. The SIGINT handler in `watch_directory()` SHALL pass the resolved watch path as `watch_root`.

**Alternatives considered**:
- *`os.path.realpath()` with string prefix check*: Rejected — string-based path containment is fragile on macOS case-insensitive filesystems.
- *`pathlib.Path.is_relative_to()` (Python 3.9+)*: Rejected — the project targets Python ≥ 3.10, but `.relative_to()` with `strict=False` is more defensive and handles both symlink targets and `..` traversal.

### 3. ConnectionError classification: distinguish `ConnectionError` from `RuntimeError` in ingestion pipeline

**Choice**: In `_embed_and_write_concurrent()`, catch `ConnectionError` separately from generic `Exception` in the batch embedding loop. Raise `ConnectionError` for Ollama connectivity issues specifically, and `RuntimeError` for other embedding failures (model errors, invalid input, ChromaDB write failures).

In `ingest_path()`, catch `ConnectionError` (→ `error_type: "connection"`) separately from `RuntimeError` (→ `error_type: "embedding"`).

In `watcher.py`, branch on `error_type == "connection"` for the consecutive-error counter; treat `error_type == "embedding"` as a generic ingestion failure.

**Alternatives considered**:
- *String-matching on exception message*: Already replaced in task 2.9. Would be fragile and require maintaining the match list.
- *Custom exception hierarchy*: Rejected — over-engineered. The existing `ConnectionError` (built-in) is sufficient.

### 4. Missing error fields: complete error return shape in `ingest_path()`

**Choice**: When `_ingest_sequential`/`_ingest_parallel` returns `files_idx == 0` with `files_to_index` non-empty, set `error_type: "file"` and `message: "All N file(s) failed to index. See file_details for per-file errors."` in the result dict.

**Alternatives considered**:
- *Custom error type per file_detail*: Rejected — the `file_details` array already has per-file `error` strings. The aggregated `error_type`/`message` provides a quick summary for the watcher to decide between "retriable" and "fatal" without parsing file_details.

### 5. Timer cleanup on OSError: symmetric with FileNotFoundError

**Choice**: In `_do_ingest()`, the `except OSError` block SHALL also clean up the timer entry from `self._timers` (via `_timers_lock`), matching the existing `FileNotFoundError` handler.

### 6. Thread-safe error counter: dedicated `threading.Lock`

**Choice**: Add `self._error_counter_lock = threading.Lock()` in `__init__`. Wrap all mutations of `_consecutive_errors` (`+= 1`, `= 0`) in `with self._error_counter_lock:`.

### 7. Hash cache size cap: LRU eviction at configurable max entries

**Choice**: Add `MAX_HASH_CACHE_ENTRIES = 50_000` constant. When the cache exceeds this size, evict the oldest entry (by insertion order) using `collections.OrderedDict` or `dict.popitem()` (Python 3.7+ dicts maintain insertion order).

### 8. File size limit: configurable max before hashing

**Choice**: Add `MAX_FILE_SIZE = 500 * 1024 * 1024` (500 MB) constant. In `_sha256_file()`, check `path.stat().st_size > MAX_FILE_SIZE` before reading and raise `OSError` with a descriptive message. The `_do_ingest()` handler already catches `OSError` from hashing and logs WARNING.

### 9. Lock consolidation: merge adjacent `_timers_lock` blocks

**Choice**: In `_do_ingest()`'s `FileNotFoundError` handler, merge the two adjacent `with self._timers_lock:` blocks into a single block.

### 10. Flaky test hardening: polling wait instead of fixed sleep

**Choice**: In `test_stop_waits_for_in_flight`, replace `time.sleep(0.2)` + immediate assert with a polling loop that checks `handler.in_flight_count > 0` up to 50 times (5-second timeout) with `time.sleep(0.1)` between checks.

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 30s timeout abandons in-flight ingestion | Low (requires Ollama hang) | Low | ChromaDB upsert is idempotent — abandoned write may leave partial data, but next event re-ingests. WARNING logged so operator knows. |
| Symlink traversal check catches legitimate use | Low | Low | A user who intentionally places symlinks outside the watch root now gets a WARNING and the file is not ingested. They should use `rag-mcp ingest` directly for such paths. |
| File size limit blocks legitimate large PDFs | Very low | Low | 500 MB PDFs are extremely rare in document indexing workflows. If encountered, the operator can increase the limit or ingest manually. |
| Hash cache eviction causes re-ingestion | Low | Low | LRU eviction is standard — the most-recently-used files stay cached, recently unused files get re-hashed on next event. Equivalent to watcher restart behaviour. |

## Open Questions

1. **Should the hash cache cap be configurable?** Currently scoped to hardcoded `MAX_HASH_CACHE_ENTRIES = 50_000`. A `--max-cache-entries` flag could be added but increases CLI surface. Defer to user feedback.
2. **Should `_sha256_file` file size limit use a `.env` config var?** Currently scoped to a module constant. The project convention (`config.py` as single source of truth) suggests yes, but `MAX_FILE_SIZE` is a safety limit, not a user-tuning parameter. Defer to user preference.
