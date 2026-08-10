# Security Assessment: harden-file-watcher

## Summary
- **Date**: 2026-05-19 | **Scope**: Symlink traversal protection, error classification, information leakage in `watcher.py` and `ingestion.py`
- **Verdict**: NEEDS FIXES — one CRITICAL TOCTOU race, two HIGH information leakage findings, three MEDIUM hardening gaps

---

## Findings

### [CRITICAL] TOCTOU Race in Symlink Traversal Protection

**Location**: `src/rag_mcp/watcher.py:146–197`

**Vulnerability**: The containment check at line 146 resolves the path via `path.resolve(strict=False)` and verifies it lies within `self._watch_root` via `resolved.relative_to(self._watch_root)`. However, the **resolved path is discarded** — all subsequent operations use the **original, unresolved** `file_path`:

1. **Line 163**: `_sha256_file(path)` — hashes the original path, which may now resolve to a different file
2. **Line 197**: `ingest_path(file_path)` — passes the original path, and `ingest_path` internally re-resolves at line 511: `Path(path).expanduser().resolve()`

An attacker with write access to the watched directory can:
1. Place a symlink inside the watch root pointing to a legitimate file within the watch root
2. The containment check at line 146 passes (symlink resolves inside watch root)
3. Swap the symlink to point to an arbitrary file outside the watch root (e.g., `/etc/passwd`)
4. `_sha256_file()` and `ingest_path()` follow the now-malicious symlink, ingesting the external file into the RAG index

The debounce timer (minimum 0.5s) provides a predictable window for the symlink swap. The RAG index would then serve content from outside the watch root to any caller of `search_documents`.

**Attack Vector**: Filesystem TOCTOU — symlink swap between containment check and file use. Requires write access to the watched directory.

**Impact**: Arbitrary file ingestion into the RAG vector store, potentially exposing sensitive files (credentials, configuration, PII) through the semantic search interface. Violates OWASP A01:2021 (Broken Access Control) — the containment boundary is bypassable.

**Mitigation**:
```diff
--- a/src/rag_mcp/watcher.py
+++ b/src/rag_mcp/watcher.py
@@ -143,9 +143,13 @@ class DocumentIngestHandler(PatternMatchingEventHandler):
         # ── Symlink traversal protection ──────────────────────────────────
         if self._watch_root is not None:
             try:
                 resolved = path.resolve(strict=False)
                 _ = resolved.relative_to(self._watch_root)
             except ValueError:
                 logger.warning(
                     "Path traversal blocked: %s resolves to %s "
                     "outside watch root %s",
                     file_path,
                     resolved,
                     self._watch_root,
                 )
                 with self._timers_lock:
                     self._timers.pop(file_path, None)
                     self._hash_cache.pop(file_path, None)
                 return
+            # Use the resolved path for all subsequent operations to close
+            # the TOCTOU window (the original path may be a symlink that
+            # can be swapped between check and use).
+            path = resolved
+            file_path = str(resolved)
 
         # ── Content-hash deduplication ───────────────────────────────────
```

---

### [HIGH] Information Leakage — Traversal Block Warning Exposes Resolved Target Path

**Location**: `src/rag_mcp/watcher.py:149–155`

**Vulnerability**: When a symlink traversal is blocked, the WARNING-level log message includes:
- The attacker-supplied event path (`file_path`)
- The **resolved target path** outside the watch root (`resolved`)
- The watch root itself (`self._watch_root`)

```python
logger.warning(
    "Path traversal blocked: %s resolves to %s outside watch root %s",
    file_path,
    resolved,
    self._watch_root,
)
```

This reveals the resolved filesystem path that the attacker may not have known. In a multi-tenant environment where logs are aggregated or accessible to non-admin users, this constitutes an information disclosure that aids further attacks by confirming the existence and location of files outside the watch root.

**Attack Vector**: Log file inspection by unauthorised parties; log aggregation into centralised systems.

**Impact**: Moderate — exposes internal filesystem structure and confirms files exist at specific paths. OWASP A04:2021 (Insecure Design) — error messages reveal too much about the system.

**Mitigation**:
```diff
 logger.warning(
-    "Path traversal blocked: %s resolves to %s "
-    "outside watch root %s",
+    "Path traversal blocked: %s resolves outside watch root",
     file_path,
-    resolved,
-    self._watch_root,
 )
```

Alternatively, log the resolved path only at DEBUG level.

---

### [HIGH] File Path Leakage in Multiple WARNING-Level Log Messages

**Location**: `src/rag_mcp/watcher.py:173, 229–234, 249–250, 264–265`

**Vulnerability**: The following log messages emit full file paths at WARNING level (visible by default):
- Line 173: `"Cannot read file for hashing: %s — %s", file_path, exc`
- Lines 229–234: `"Ingestion failed (ConnectionError) for %s: %s [%d consecutive]", file_path, exc, current_errors`
- Lines 249–250: `"Ingestion failed for %s: %s", file_path, exc`
- Lines 264–265: `"Ingestion failed for %s: %s", file_path, exc`

Additionally, INFO-level messages at lines 194 and 208–209 emit full paths.

**Attack Vector**: Default log output accessible to users with access to stderr. In MCP server deployments where logs are forwarded to monitoring systems, these paths become visible to operations staff or log analysis tools.

**Impact**: Low-Moderate — for a local-only tool this is acceptable, but if the watcher runs as a service or logs are shipped to a central aggregator, the watched directory structure is exposed. OWASP A09:2021 (Security Logging and Monitoring Failures).

**Mitigation**: Consider logging only the filename (`Path(file_path).name`) at INFO/WARNING and reserving full paths for DEBUG. The watcher is a local CLI tool, so this is lower risk — but document the tradeoff.

---

### [MEDIUM] Unhandled `OSError` from `path.resolve()` Can Crash Timer Thread

**Location**: `src/rag_mcp/watcher.py:145–148`

**Vulnerability**: The `try/except` block only catches `ValueError` from `relative_to()`. If `path.resolve(strict=False)` raises `OSError` (e.g., permission denied on a parent directory, filesystem I/O error, unmounted NFS volume), the exception propagates unhandled. In a threading.Timer callback, unhandled exceptions are silently swallowed by the Python runtime — the thread dies, timer and hash cache entries are never cleaned up, and the watcher effectively stops processing new files for that path.

```python
try:
    resolved = path.resolve(strict=False)  # ← OSError NOT caught
    _ = resolved.relative_to(self._watch_root)
except ValueError:
    ...
```

**Attack Vector**: Denial of service — if an attacker can cause `resolve()` to fail (e.g., exhausting inotify watches, creating deep directory structures, triggering NFS issues), the timer thread dies silently.

**Impact**: Watcher silently stops processing events; no alert is raised. OWASP A08:2021 (Software and Data Integrity Failures) — silent failure undermines availability.

**Mitigation**:
```diff
 try:
     resolved = path.resolve(strict=False)
     _ = resolved.relative_to(self._watch_root)
 except ValueError:
     ...
+except OSError as exc:
+    logger.warning("Cannot resolve path for containment check: %s — %s", file_path, exc)
+    with self._timers_lock:
+        self._timers.pop(file_path, None)
+        self._hash_cache.pop(file_path, None)
+    return
```

---

### [MEDIUM] Double `path.stat()` Race in `_sha256_file()` Size Check

**Location**: `src/rag_mcp/watcher.py:339–343`

**Vulnerability**: `_sha256_file()` calls `path.stat().st_size` twice — once for the size comparison and once inside the error message f-string:

```python
if path.stat().st_size > MAX_FILE_SIZE:  # call 1 (line 339)
    raise OSError(
        f"File exceeds maximum size of {MAX_FILE_SIZE} bytes "
        f"(got {path.stat().st_size} bytes)"  # call 2 (line 342)
    )
```

If the file is replaced or truncated between the two calls, the second `path.stat()` may raise `FileNotFoundError` or return a different size, producing a misleading error or crashing the error-message construction. This is caught by `_do_ingest`'s `except FileNotFoundError` handler, so it doesn't crash the watcher — but it obscures the root cause.

**Attack Vector**: Race condition during file write — low exploitability, timing-dependent.

**Impact**: Misleading log entry; debugging difficulty. Not directly exploitable.

**Mitigation**:
```diff
-def _sha256_file(path: Path) -> str:
+def _sha256_file(path: Path) -> str:
+    st = path.stat()
+    if st.st_size > MAX_FILE_SIZE:
         raise OSError(
             f"File exceeds maximum size of {MAX_FILE_SIZE} bytes "
-            f"(got {path.stat().st_size} bytes)"
+            f"(got {st.st_size} bytes)"
         )
```

---

### [MEDIUM] `_embed_and_write_concurrent` May Leak Internal Paths via Batch Error Messages

**Location**: `src/rag_mcp/ingestion.py:428–440`

**Vulnerability**: The `logger.error` calls include the raw exception string from embedding batch failures:

```python
except ConnectionError as exc:
    batch_errors.append(
        f"Batch {batch_idx} failed (connection): {exc}"
    )
    logger.error(
        "Embedding batch %d failed (connection): %s",
        batch_idx, exc,
    )
```

If `exc` contains file paths or embedding model details (which Ollama error messages may include), these are logged at ERROR level. The raised exception at line 445–448 does NOT include the detailed `batch_errors` list, so the API response is safe — but the **log** could contain internal details.

**Attack Vector**: Log inspection by unauthorised parties.

**Impact**: Low — the `batch_errors` list is not exposed through the API, only in logs.

**Mitigation**: Consider sanitising the exception message before logging, or logging only the batch index and exception type:
```python
logger.error(
    "Embedding batch %d failed (connection): %s",
    batch_idx,
    type(exc).__name__,
)
```

---

## Confirmed-Safe Patterns

The following patterns were verified as secure:

| Pattern | Location | Rationale |
|---------|----------|-----------|
| **Ingestion error messages use `.name` only** | `ingestion.py:181, 262` | `errors.append(f"{file_path.name}: {exc}")` — filename, not full path. The `warnings` key in the API response only exposes filenames. |
| **`_make_file_detail` uses `file_name`** | `ingestion.py:46–49, 172–176` | Only the basename is recorded, not the absolute path. |
| **Watchdog ignore patterns block hidden/temp files** | `watcher.py:62–67` | `.*`, `~$*`, `*.tmp`, `*.part` patterns prevent ingestion of editor temp files and system files. |
| **`_error_counter_lock` used consistently** | `watcher.py:222, 226–228, 247–248` | All reads/writes to `_consecutive_errors` are protected by the lock. No race condition on the counter. |
| **`_shutdown_requested` checked at all bailout points** | `watcher.py:138, 187` | Early return at entry to `_do_ingest` and after acquiring semaphore prevents new work during shutdown. |
| **`_ingest_semaphore` limits concurrent ingestions** | `watcher.py:186` | `BoundedSemaphore(2)` prevents resource exhaustion from rapid file events. |
| **`ingest_path` distinct error categories** | `ingestion.py:569–582` | `ConnectionError`, `RuntimeError`, and `file` error types are cleanly separated; no string-matching on messages. |
| **`embeddings` list initialised with `None` placeholders** | `ingestion.py:405` | `[None] * len(nodes)` — safe because `batch_errors` check at line 443 prevents access to `None` entries; if any batch fails, the function raises before the write phase. |
| **ChromaDB upsert idempotency** | `watcher.py:82–85` (comment) | Duplicate hash cache writes at most cause redundant embedding calls; no data corruption. Documented as acceptable v1 race. |
| **`watch_root` resolved by caller** | `watcher.py:383` | `watch_directory()` resolves `watch_path` before passing to `DocumentIngestHandler`, ensuring consistent canonical form. |
| **macOS `/tmp` → `/private/tmp` consistency** | `watcher.py:383, 400` | Both `watch_root` and watchdog event paths use the resolved canonical path, so `relative_to()` comparisons are consistent regardless of `/tmp` symlink. |
| **Second SIGINT forces immediate quit** | `watcher.py:416–419` | Prevents infinite hang if `stop()` itself blocks. |

---

## OWASP Top 10 Coverage

| OWASP Category | Status | Notes |
|---------------|--------|-------|
| **A01:2021 — Broken Access Control** | ⚠️ Finding | TOCTOU race in symlink containment (CRITICAL) |
| **A02:2021 — Cryptographic Failures** | ✅ Safe | SHA-256 for content deduplication only (not auth); no crypto misuse |
| **A03:2021 — Injection** | ✅ Safe | No SQL, no command execution; `ingest_path` uses LlamaIndex API, not shell |
| **A04:2021 — Insecure Design** | ⚠️ Finding | Traversal block log leaks resolved path (HIGH); double-stat race (MEDIUM) |
| **A05:2021 — Security Misconfiguration** | ✅ Safe | `.env` for all config; no hardcoded defaults for model names |
| **A06:2021 — Vulnerable Components** | Not assessed | Dependency audit out of scope for this review |
| **A07:2021 — Auth Failures** | N/A | Local tool; no authentication layer |
| **A08:2021 — Software/Data Integrity Failures** | ⚠️ Finding | Silent thread death on `resolve()` failure (MEDIUM) |
| **A09:2021 — Security Logging Failures** | ⚠️ Finding | Full paths at INFO/WARNING in watcher logs (HIGH) |
| **A10:2021 — SSRF** | N/A | No outbound requests from watcher (Ollama is localhost) |

---

## Dependency Audit

Not performed in this review (out of scope). Recommend running `uv pip check` and checking `pyproject.toml` dependencies for known CVEs separately.

---

## Overall Assessment

The hardening changes are a **meaningful improvement** over having no containment at all — the symlink traversal check, content-hash deduplication, file size limits, and error classification all reduce the attack surface. The code is well-structured and the tests cover the intended behaviour thoroughly.

However, the **TOCTOU race in the containment check** is a real vulnerability that allows bypass of the very boundary the hardening was designed to enforce. The fix is straightforward (reuse the resolved path) and should be applied before deployment in any environment where an untrusted party could write to the watched directory.

The information leakage findings are lower severity for a local CLI tool but should be addressed before the watcher is used as a long-running service or in any environment with log aggregation.

**Recommendation**: Apply the TOCTOU fix (CRITICAL) immediately, address the HIGH findings, then proceed to production. The MEDIUM findings can be addressed in a follow-up hardening pass.
