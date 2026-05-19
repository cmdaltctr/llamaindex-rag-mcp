# Security Assessment: add-file-watcher

## Summary
- **Date**: 2026-05-19 | **Scope**: `watcher.py` (full), `ingestion.py` (lines 457–569 `ingest_path`), `cli.py` (`watch` command)
- **Verdict**: **NEEDS FIXES** — 1 medium-severity path traversal, 2 medium-severity contract/classification bugs, 3 low-severity thread-safety/resource issues

---

## Findings

### [MEDIUM] F1 — Path Traversal via Symlink Resolution in `ingest_path` and `_sha256_file`

**Location**: `src/rag_mcp/watcher.py:135–140` (`_do_ingest` → `_sha256_file`), `src/rag_mcp/ingestion.py:491` (`ingest_path` → `Path.resolve()`)

**Vulnerability**: When a symlink with a supported extension (`.pdf`, `.txt`, `.md`, etc.) is placed inside the watched directory and points to a file **outside** the watch root, both `_sha256_file` (via `open()`) and `ingest_path` (via `Path.resolve()`) **follow the symlink** to the target file. There is no check that the resolved target path remains within the watch root. The suffix check in `ingest_path` applies to the **resolved path** (the target), so an attacker would need to create a symlink pointing to a file with a supported extension — but any such file on the filesystem is ingestible.

**Attack Vector**:
1. Attacker gains write access to the watched directory (or tricks a user into placing a symlink there).
2. Attacker creates `evil.txt → /Users/victim/Documents/secrets.txt` inside the watch root.
3. Watchdog detects the creation event.
4. `_sha256_file` opens and hashes `/Users/victim/Documents/secrets.txt` (the target).
5. `ingest_path("/watch/root/evil.txt")` resolves to `/Users/victim/Documents/secrets.txt`, passes the `.txt` suffix check, and ingests the file content into ChromaDB.
6. The content is now retrievable via the MCP `search_documents` tool.

**Caveats**:
- Only files with extensions in `SUPPORTED_EXTENSIONS` (`.pdf`, `.docx`, `.pptx`, `.txt`, `.md`, `.html`, `.csv`) can be targeted.
- The `rglob` calls in `_gather_supported_files` use `recurse_symlinks=False` (Python 3.12+ default), so bulk directory ingestion does NOT follow directory symlinks. Only the single-file `Path.resolve()` + `open()` path is vulnerable.
- Local-only tool — requires filesystem write access to the watch root.

**Mitigation**:
In `DocumentIngestHandler.__init__`, store the resolved watch root. In `_do_ingest`, validate that the resolved file path is within the watch root:

```diff
  # In __init__: accept and store the watch root
+ self._watch_root = Path(watch_root).resolve()

  # In _do_ingest, after line 135 (path = Path(file_path)):
+ resolved = path.resolve()
+ # Ensure the resolved file is within the watched directory tree
+ try:
+     resolved.relative_to(self._watch_root)
+ except ValueError:
+     logger.warning("Path traversal blocked: %s → %s", file_path, resolved)
+     with self._timers_lock:
+         self._timers.pop(file_path, None)
+     return
```

---

### [MEDIUM] F2 — `error_type: "connection"` Misclassification in `ingest_path`

**Location**: `src/rag_mcp/ingestion.py:549–555`

**Vulnerability**: `ingest_path` catches ALL `RuntimeError` exceptions from `_ingest_sequential`/`_ingest_parallel` and classifies them as `error_type: "connection"`. However, `_embed_and_write_concurrent` raises `RuntimeError` for ANY embedding batch failure — including model errors, invalid input, ChromaDB write failures, etc. — not only connection failures. This causes the watcher to increment `_consecutive_errors` and potentially log a CRITICAL "Ollama may be unreachable" message when Ollama is actually functioning correctly.

**Attack Vector**: Not exploitable for attack, but an operational hazard: a legitimate non-connection error (e.g., model returns malformed embeddings) triggers a false-positive CRITICAL alert about Ollama connectivity, potentially causing unnecessary incident response.

**Mitigation**:
Introduce distinct exception types or error_type values. Example approach:
```diff
  # In _embed_and_write_concurrent, distinguish error types
+ class EmbeddingConnectionError(RuntimeError):
+     """Ollama / embedding service unreachable."""
+     pass
+ 
+ class EmbeddingProcessError(RuntimeError):
+     """Embedding failed for non-connection reasons."""
+     pass

  # In ingest_path, catch both types:
  except EmbeddingConnectionError:
      return {"status": "error", "error_type": "connection", ...}
  except EmbeddingProcessError:
      return {"status": "error", "error_type": "embedding", ...}
```
At minimum, wrap the `RuntimeError` raise in `_embed_and_write_concurrent` with logic that inspects the underlying exception type to distinguish connection errors from other failures.

---

### [MEDIUM] F3 — Missing `error_type` and `message` When All Files Fail

**Location**: `src/rag_mcp/ingestion.py:560–565`

**Vulnerability**: When `_ingest_sequential` or `_ingest_parallel` returns `files_idx == 0` (all files failed during reading/chunking), the result dict has `status: "error"` but **no `error_type` key** and **no `message` key**. The watcher at `watcher.py:175` defaults `error_msg` to `"unknown error"` and raises `RuntimeError("unknown error")`, which is caught as a generic `Exception` at line 217 and logged as a WARNING. The actual per-file errors (available in `file_details`) are never surfaced to the watcher logs, creating a **silent failure** scenario.

**Impact**: Operators may not realise all files failed. The watcher continues running with no indication that every queued file failed, unless they inspect the ChromaDB index.

**Mitigation**:
```diff
  # In ingest_path, after _ingest_sequential/_ingest_parallel returns:
  result = {
      "status": "ok" if files_idx > 0 else "error",
      "files_indexed": files_idx,
      "chunks_created": chunks,
      "file_details": all_details,
  }
+ if files_idx == 0:
+     result["error_type"] = "file"
+     result["message"] = (
+         f"All {len(files_to_index)} file(s) failed to index. "
+         f"See file_details for per-file errors."
+     )
  if errors:
      result["warnings"] = errors
```

---

### [LOW] F4 — Race Condition on `_consecutive_errors` Counter

**Location**: `src/rag_mcp/watcher.py:191`

**Vulnerability**: `self._consecutive_errors += 1` is not atomic in Python (it's a read-modify-write). With `BoundedSemaphore(2)`, two threads can be inside the `ConnectionError` handler simultaneously. Under CPython's GIL, bytecode-level preemption can cause a lost increment (both threads read the same value, both write `value + 1`). This could prevent the `CONSECUTIVE_ERROR_THRESHOLD` from being reached when it should.

**Impact**: If Ollama is unreachable, the CRITICAL alert might not fire at exactly 5 errors — it could take 6 or more.

**Mitigation**: Add a lock around `_consecutive_errors` reads/writes, or use `threading.Lock`:
```diff
+ self._error_counter_lock = threading.Lock()

  # In ConnectionError handler:
+ with self._error_counter_lock:
      self._consecutive_errors += 1
```

---

### [LOW] F5 — Timer Entry Leak on `OSError` in `_do_ingest`

**Location**: `src/rag_mcp/watcher.py:149–151`

**Vulnerability**: When `_sha256_file` raises `OSError` (e.g., `PermissionError`), the `_do_ingest` method logs a warning and returns **without popping the timer entry** from `_timers` or the hash from `_hash_cache`. Compare with the `FileNotFoundError` handler at lines 139–148 which properly cleans up both. Each `OSError` event leaks a stale dict entry. Over time, if a file with permission issues receives repeated events, `_timers` grows unbounded (memory leak).

**Mitigation**:
```diff
  except OSError as exc:
      logger.warning("Cannot read file for hashing: %s — %s", file_path, exc)
+     with self._timers_lock:
+         self._timers.pop(file_path, None)
+         self._hash_cache.pop(file_path, None)
      return
```

---

### [LOW] F6 — Unbounded Hash Cache Growth

**Location**: `src/rag_mcp/watcher.py:81` (`_hash_cache`)

**Vulnerability**: `_hash_cache` grows monotonically — entries are added at line 187 on successful ingestion and removed only on `FileNotFoundError` (line 147, 214) or `OSError` (none currently — see F5). There is no eviction policy. For a long-running watcher monitoring a directory with many files that are never deleted, `_hash_cache` grows without bound.

**Impact**: Memory exhaustion in very long-running deployments with many files (thousands+).

**Mitigation**: Implement a bounded LRU cache (e.g., `functools.lru_cache` or `cachetools.LRUCache`) with a reasonable max size, or prune entries for files that no longer exist.

---

### [LOW] F7 — No File Size Limit in `_sha256_file`

**Location**: `src/rag_mcp/watcher.py:282–286`

**Vulnerability**: `_sha256_file` reads the entire file in 8 KB chunks with no upper bound on file size. A maliciously large file (multi-gigabyte) could cause CPU exhaustion during hashing and memory pressure from the read buffer.

**Impact**: Denial of service on the watcher process.

**Mitigation**: Add a maximum file size check before hashing:
```diff
  def _sha256_file(path: Path) -> str:
+     MAX_SIZE = 500 * 1024 * 1024  # 500 MB
+     if path.stat().st_size > MAX_SIZE:
+         raise OSError(f"File exceeds maximum size ({MAX_SIZE} bytes): {path}")
      hasher = hashlib.sha256()
      with open(path, "rb") as f:
          ...
```

---

## Dependency Audit

| Check | Result |
|-------|--------|
| `uv pip check` | ✅ All 150 packages compatible, no conflicts |
| `watchdog` CVEs | ✅ No known CVEs for the watchdog Python library |
| `chromadb` CVEs | ✅ No known CVEs for chromadb (CVE-2024-45848 is for MindsDB, not chromadb-core) |
| `llama-index` CVEs | ✅ No critical CVEs identified |
| `huggingface-hub` | ℹ️ Version 0.36.2 — current, no known issues |

**Overall**: Dependencies are clean. No known vulnerabilities in the dependency tree that would affect this project's threat model.

---

## OWASP Top 10 Summary

| OWASP Category | Status | Notes |
|----------------|--------|-------|
| A01:2021 Broken Access Control | ✅ Low risk | No network exposure; local-only CLI tool |
| A03:2021 Injection | ✅ Low risk | No SQL/command injection surfaces; Ollama API is the only external I/O |
| A04:2021 Insecure Design | ⚠️ F1, F2, F3 | Path traversal via symlinks; error contract inconsistent |
| A05:2021 Security Misconfiguration | ✅ Low risk | `.env`-based config; no hardcoded secrets |
| A06:2021 Vulnerable Components | ✅ Clean | No known CVEs in dependencies |
| A08:2021 Software Integrity Failures | ✅ Low risk | Local-only; no integrity validation needed for CLI |

---

## Error-Type Contract Analysis

### Current Contract
| `ingest_path` returns | `error_type` | Watcher behaviour |
|---|---|---|
| Path not found | `"file"` | `RuntimeError` → caught as generic `Exception` → WARNING log |
| Unsupported extension | `"file"` | Same as above |
| Embedding fails (RuntimeError) | `"connection"` | `ConnectionError` → `_consecutive_errors++` → may trigger CRITICAL |
| All files failed to read (`files_idx == 0`) | **MISSING** | `RuntimeError("unknown error")` → caught as generic → WARNING |
| No supported files found | N/A (`"ok"`) | No error — correct |

### Issues
1. **F2**: `"connection"` over-classifies — non-connection embedding errors get the connection label.
2. **F3**: `files_idx == 0` path has no `error_type` or `message` — silent failure in watcher.
3. **F4**: Race on `_consecutive_errors` mutates shared state without synchronisation.

---

## Recommendations (Priority-Ordered)

1. **Fix F1 (Path Traversal)** — Validate that resolved file paths are within the watch root. This is the only finding with a real (if narrow) information-disclosure risk.
2. **Fix F3 (Missing error_type)** — Add `error_type: "file"` and a descriptive `message` when all files fail.
3. **Fix F2 (Misclassification)** — Distinguish connection errors from other embedding failures to avoid false-positive CRITICAL alerts.
4. **Fix F5 (Timer leak)** — Add cleanup in the `OSError` handler.
5. **Fix F4 (Race on counter)** — Add a lock around `_consecutive_errors`.
6. **Fix F6 (Unbounded cache)** — Add LRU eviction or max size for `_hash_cache`.
7. **Fix F7 (No file size limit)** — Add a configurable max file size for hashing.
