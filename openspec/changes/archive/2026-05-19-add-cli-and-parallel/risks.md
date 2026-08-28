# Security Assessment: add-cli-and-parallel
## Summary
- **Date**: 2026-05-18 | **Scope**: CLI interface, parallel ingestion, progress reporting for existing RAG MCP server
- **Verdict**: NEEDS FIXES — 3 HIGH, 7 MEDIUM findings; none blocking deployment but all should be addressed before release
- **CVE Impact**: 1 identified (CVE-2025-51480, ONNX path traversal) — **not exploitable** in this project due to hardened usage pattern

## Threat Model — Structured Findings

### 1. [MEDIUM] Path Traversal via CLI `ingest` Argument
**Location**: Planned CLI entrypoint (not yet written); analogous to `src/rag_mcp/ingestion.py:36`
**Vulnerability**: The current `ingest_path()` validates with `Path(path).exists()` but does **not** resolve or canonicalise the path before use. A user could pass `../../etc/passwd` or `~/secrets/keys.txt`. While `exists()` would catch non-existent paths, it would happily accept any existing file on the filesystem, including files outside the user's intended document scope.

**Attack Vector**: 
1. User runs: `rag-mcp ingest ../../../private_docs/financials.pdf`
2. The path resolves to a file outside the current working directory
3. Contents are chunked, embedded, and stored in ChromaDB (disk)
4. Anyone with filesystem access to `chroma_db/` can later extract these embeddings and text chunks

**Impact**: Sensitive documents accidentally ingested; data leakage through ChromaDB persistence. On a multi-user system, another local user who can read the `chroma_db/` directory could enumerate all indexed documents via `rag-mcp list` and extract text via `rag-mcp search`.

**Mitigation**:
```python
# Before path usage, resolve and validate:
from pathlib import Path

def _validate_path(user_path: str, allowed_roots: list[Path] | None = None) -> Path:
    """Resolve and validate a user-supplied path.

    Args:
        user_path: Raw path string from CLI or MCP tool.
        allowed_roots: Optional list of directories to confine access to.
            If None, defaults to [Path.cwd()].

    Returns:
        Resolved absolute Path.

    Raises:
        ValueError: If path is outside allowed roots.
    """
    resolved = Path(user_path).expanduser().resolve(strict=False)
    roots = allowed_roots or [Path.cwd().resolve()]
    for root in roots:
        try:
            resolved.relative_to(root)
            break
        except ValueError:
            continue
    else:
        raise ValueError(
            f"Path '{resolved}' is outside allowed directories: "
            f"{[str(r) for r in roots]}"
        )
    return resolved
```

**Severity**: MEDIUM — local-only tool, explicit user action required. Elevates to HIGH on multi-user systems.

---

### 2. [LOW] Shell Injection via CLI Arguments
**Location**: Planned CLI `sys.argv` handling
**Vulnerability**: Python argument parsers (`argparse`, `click`, `typer`) do **not** invoke shells when processing arguments. Unlike `os.system()` or subprocess with `shell=True`, argument values are passed as string objects, not interpreted by a shell.

**Attack Vector**: None practical — a user could pass `$(rm -rf /)` as a CLI argument, but argparse/typer will treat it as the literal string `"$(rm -rf /)"`, not execute it. The value would fail `Path().exists()` and return an error.

**Impact**: Negligible for Python CLI. Risk exists only if the implementation later uses `subprocess` with `shell=True` — which the AGENTS.md prohibits.

**Mitigation**: 
- Use `argparse`, `click`, or `typer` for argument parsing (never manual `sys.argv` string manipulation)
- **Never** pass user input to `subprocess` with `shell=True`
- Already covered by project convention (AGENTS.md: no API keys, no shell injection)

**Severity**: LOW — standard Python CLI parsing is safe by design.

---

### 3. [MEDIUM] ChromaDB Data Exposure via CLI `search` and `list`
**Location**: Planned CLI `search` and `list` commands; existing `src/rag_mcp/retrieval.py:44-129`, `src/rag_mcp/ingestion.py:87-114`
**Vulnerability**: The `list_indexed_documents` tool (and planned CLI equivalent) returns source file paths of all indexed documents without any access control. The `search_documents` tool returns full text chunks. On a multi-user system, any user with access to `chroma_db/` can read all indexed content.

**Attack Vector**:
1. User A indexes sensitive documents (e.g., `~/private/contracts/`)
2. User B on the same machine runs `rag-mcp list` → sees `/home/userA/private/contracts/doc1.pdf`
3. User B runs `rag-mcp search "salary"` → retrieves chunks containing salary data

**Impact**: Cross-user data leakage. The ChromaDB database has no authentication or authorisation layer — it trusts the OS filesystem permissions.

**Mitigation**:
- Document this as a **known limitation** in README.md: this is a single-user tool; ChromaDB permissions are filesystem-level
- Consider adding a `--collection` flag to allow users to maintain separate collections (mitigation, not fix)
- For multi-user systems, recommend: `chmod 700 chroma_db/` after indexing
- Add a warning banner on first run: `ChromaDB stores document contents in plain text on disk at ./chroma_db/. Ensure this directory has appropriate filesystem permissions.`

**Severity**: MEDIUM — scope-limited to local filesystem access; expected behaviour for a local-first tool.

---

### 4. [HIGH] Race Condition: Concurrent ChromaDB Writes
**Location**: Planned parallel ingestion; existing `src/rag_mcp/ingestion.py:70-78`
**Vulnerability**: The current ingestion code creates a **new `VectorStoreIndex`** for each ingestion call. In a concurrent scenario (ThreadPoolExecutor processing 10 files in parallel), each thread would:
1. Load documents independently
2. Create **separate `VectorStoreIndex` instances** writing to the same ChromaDB collection
3. ChromaDB's underlying SQLite database is **not designed for concurrent writes** from multiple processes/threads

**Attack Vector**: Not a malicious attack, but a **data integrity and reliability** issue:
- Two threads could interleave writes, corrupting the SQLite WAL
- Duplicate document chunks may be inserted (no deduplication currently exists)
- ChromaDB may crash with `sqlite3.OperationalError: database is locked`
- Silent data loss: some embeddings may be written but never committed

**Impact**: Corrupted vector store requiring full re-indexing. Lost user time. Non-deterministic failures that are hard to debug.

**Mitigation**:
```python
import threading

# Single ingestion lock — prevents concurrent ChromaDB writes
_ingestion_lock = threading.Lock()

def ingest_path(path: str) -> dict:
    with _ingestion_lock:
        return _ingest_path_inner(path)
```

Or, better for CLI parallelism:
```python
from concurrent.futures import ThreadPoolExecutor

def ingest_directory_parallel(dir_path: Path, max_workers: int = 4) -> dict:
    """Ingest multiple files in parallel but serialise ChromaDB writes."""
    files = list(_gather_supported_files(dir_path))

    # Phase 1: Load and chunk all files in parallel (I/O bound, safe)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_load_and_chunk_file, f): f for f in files}
        all_nodes = {}
        for future in futures:
            try:
                nodes = future.result()
                all_nodes[futures[future]] = nodes
            except Exception as e:
                errors.append((futures[future].name, str(e)))

    # Phase 2: Write to ChromaDB sequentially (avoiding race)
    with _ingestion_lock:
        for file, nodes in all_nodes.items():
            _write_nodes_to_chromadb(nodes)

    return {"status": "ok", "files_indexed": len(all_nodes),
            "errors": errors}
```

**Severity**: HIGH — guarantees data corruption under load. Must be addressed before shipping parallel ingestion.

---

### 5. [HIGH] Resource Exhaustion: Ollama Embedding Overload
**Location**: Implicit in parallel ingestion; `src/rag_mcp/config.py:24-28` sets `embed_batch_size=10`
**Vulnerability**: If 8 threads each send `embed_batch_size=10` requests to Ollama simultaneously, that's 80 concurrent embedding requests. Ollama runs on CPU (or GPU with limited VRAM) and will:
- Queue all requests, causing 30–60s latency per thread
- ThreadPoolExecutor threads will remain blocked, consuming memory
- The default `ThreadPoolExecutor` has unbounded queue growth — could exhaust memory with large directories

**Attack Vector**: Accidental DoS against local Ollama service. A user ingesting 500 files with `max_workers=16` could bring Ollama to its knees, affecting other applications relying on it.

**Impact**: Degraded performance, potential OOM, blocked processes. Makes the tool appear broken.

**Mitigation**:
- Use a **semaphore** to limit concurrent embedding calls:
```python
import threading

# Limit concurrent Ollama API calls to avoid overwhelming the server
_embed_semaphore = threading.BoundedSemaphore(value=2)

def _embed_texts(texts: list[str]) -> list[list[float]]:
    with _embed_semaphore:
        return Settings.embed_model.get_text_embedding_batch(texts)
```
- Make `max_workers` configurable via `.env` (`INGEST_MAX_WORKERS=4`)
- Add a warning on `--max-workers > 4`: `"High concurrency may overload Ollama"`

**Severity**: HIGH — reliability issue. Users will encounter timeouts and crashes.

---

### 6. [MEDIUM] Incomplete Ingestion State on Partial Failure
**Location**: Planned parallel ingestion; existing `src/rag_mcp/ingestion.py:25-84`
**Vulnerability**: If the user ingests a directory of 100 files and the process fails at file #47 (e.g., corrupt PDF, Ollama crash), the ChromaDB collection contains:
- Chunks from files 1–46 (successfully written)
- **No record of which files failed**
- The existing `ingest_path` has no transactional semantics — it's not atomic

**Attack Vector**: Not a security attack per se, but a **data consistency** vulnerability. A user who re-runs ingestion after a failure will get **duplicate chunks** for files 1–46, inflating the vector store. Repeated partial failures → exponential growth.

**Impact**: Wasted disk space. Degraded search quality (duplicate chunks skew relevance). User confusion about "why is my db 5GB?"

**Mitigation**:
- Add **deduplication** by file hash before ingestion:
```python
import hashlib
from pathlib import Path

def _file_hash(file_path: Path) -> str:
    """Compute SHA-256 of file contents for deduplication."""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()

def _ingest_path_deduped(path: Path) -> dict:
    file_hash = _file_hash(path)
    existing = _get_ingested_hashes()
    if file_hash in existing:
        return {"status": "ok", "files_indexed": 0, "message": "Already indexed"}
    ...
```
- Store a **manifest** of ingested file hashes in ChromaDB metadata or a sidecar file
- Implement `rag-mcp ingest --skip-existing` flag (default: on)
- Add `rag-mcp ingest --force` to override dedup

**Severity**: MEDIUM — reliability issue. Long-term operational risk.

---

### 7. [MEDIUM] Signal Handling: Ctrl+C During Parallel Ingestion
**Location**: Planned parallel ingestion with ThreadPoolExecutor
**Vulnerability**: When a user presses Ctrl+C:
1. Python's `KeyboardInterrupt` is raised on the main thread
2. Background threads in `ThreadPoolExecutor` continue running with their ChromaDB connections open
3. If the main thread exits, the process terminates, potentially leaving ChromaDB in an inconsistent state (open transactions, unflushed WAL)
4. The ONNX reranker singleton (`CrossEncoderReranker._instance`) holds a thread lock that may be in a locked state if killed mid-inference

**Attack Vector**: Denial of service (self-inflicted). Corrupted ChromaDB requiring manual repair or deletion.

**Impact**: Lost work, corrupted database, need to `rm -rf chroma_db` and re-index.

**Mitigation**:
```python
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

_shutdown_requested = threading.Event()

def _handle_sigint(signum, frame):
    print("\nShutting down gracefully... (press Ctrl+C again to force)",
          file=sys.stderr)
    _shutdown_requested.set()

signal.signal(signal.SIGINT, _handle_sigint)

def ingest_parallel(paths: list[Path], max_workers: int = 4) -> dict:
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_ingest_single, p): p for p in paths}
        for future in as_completed(futures):
            if _shutdown_requested.is_set():
                pool.shutdown(wait=True, cancel_futures=True)
                break
            # ... process result
```
- Add `signal.SIGTERM` handler as well
- Document: "Ctrl+C during ingestion will complete the current file then exit"

**Severity**: MEDIUM — reliability issue. Users WILL hit Ctrl+C.

---

### 8. [LOW] `sys.argv` Exposure in Error Messages
**Location**: Planned CLI error handling
**Vulnerability**: If a CLI tool prints the raw command line in error messages (e.g., `f"Invalid path: {sys.argv[2]}"`), and the terminal output is logged or captured, argument values could be exposed. This is primarily a concern if the CLI is later wrapped by scripts that pipe output to logs.

**Attack Vector**: Minimal — requires log capture and sensitive command-line arguments. Low likelihood for a local-only tool.

**Impact**: Negligible for current use case. Becomes relevant only if deployed in CI/CD pipelines.

**Mitigation**:
- Sanitise error messages: never echo raw user input verbatim without context
- Prefer: `"Invalid path: the provided path does not exist or is not accessible"`
- Avoid: `"Invalid path: ../../etc/shadow"`

**Severity**: LOW — informational hygiene.

---

### 9. [MEDIUM] Progress Bar (tqdm/rich) Terminal Escape Injection
**Location**: Planned CLI progress reporting
**Vulnerability**: Progress bars written to stderr display file paths. If a file contains ANSI escape sequences in its name (e.g., `\x1b[2Jclear_screen.pdf`), and the progress bar prints the filename without escaping, it could:
- Clear the terminal
- Warp the cursor
- Inject fake progress output

**Attack Vector**: A maliciously named file in a directory being ingested could manipulate the terminal display. This is an **output sanitisation** issue, not a code execution vulnerability.

**Impact**: Cosmetic — terminal display corruption. No data loss or code execution.

**Mitigation**:
- Sanitise filenames before display: `repr(filename)` or strip control characters:
```python
import re

def _sanitise_display_name(name: str) -> str:
    """Remove ANSI escape sequences from display strings."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', name)
```
- tqdm already handles this for its own output; the risk is in custom status messages

**Severity**: MEDIUM — cosmetic but technically an injection vector. Easy to fix.

---

### 10. [LOW] Click/Typer Argument Injection via Shell Aliases
**Location**: Planned CLI parsing
**Vulnerability**: If the user has a shell alias that overrides `rag-mcp` (e.g., `alias rag-mcp='rag-mcp --collection=evil'`), or if a modified `rag-mcp` script is placed earlier in `$PATH`, the user could unknowingly run a compromised version. This is a **supply chain / environment** concern, not a code vulnerability.

**Attack Vector**: 
1. Attacker with local access modifies `~/.bashrc` or `~/.zshrc` to add `alias rag-mcp='...malicious payload...'`
2. User runs `rag-mcp ingest docs/` — executes malicious code

**Impact**: Complete compromise (attacker already has local access). This is OS-level, not application-level.

**Mitigation**:
- Document: "Ensure your PATH is trusted and no shell aliases shadow rag-mcp"
- Ship with a `--version` flag to verify the binary
- Not a code fix — this is a user education issue

**Severity**: LOW — requires existing local access, which is game-over anyway.

---

## Dependency Audit

| Package | Version | Known CVE? | Relevant? | Notes |
|---------|---------|-----------|-----------|-------|
| `onnxruntime` | 1.25.1 | CVE-2025-51480 (path traversal) | **NOT exploitable** | ONNX model loaded from HuggingFace Hub via `hf_hub_download()`, not user-supplied path. The `InferenceSession()` receives a trusted local path. |
| `chromadb` | 1.5.9 | No direct CVEs | — | Underlying SQLite has known CVEs but ChromaDB bundles a recent version. The concurrent write issue (Finding #4) is the primary concern. |
| `transformers` | 4.57.6 | No critical CVEs | — | Used only for tokenizer loading in reranker. No model execution via transformers. |
| `huggingface-hub` | 0.36.2 | No critical CVEs | — | Used for model download only. Cached locally after first use. |
| `requests` | 2.33.1 | No critical CVEs | — | Indirect dependency. |
| `pydantic` | 2.13.4 | No critical CVEs | — | Used for MCP tool parameter validation. |
| `llama-index` | 0.14.21 | No known CVEs | — | Core framework. |

**Overall**: No exploitable CVEs in the dependency tree for this project's usage patterns. The ONNX CVE-2025-51480 is a false positive in this context — the attack requires loading a malicious model from an attacker-controlled path, but this project uses a hardcoded HuggingFace Hub model ID.

---

## OWASP Top 10 Coverage

| Risk | Status | Details |
|------|--------|---------|
| A01: Broken Access Control | ⚠️ Partial | ChromaDB has no internal access control; relies on filesystem permissions. Documented limitation. |
| A02: Cryptographic Failures | ✅ N/A | No cryptography implemented. Filesystem-level trust. |
| A03: Injection | ✅ Low risk | No SQL, no shell interpolation. Path traversal partially addressed (Finding #1). ANSI injection noted (Finding #9). |
| A04: Insecure Design | ⚠️ Partial | No concurrency safety design (Finding #4, #5). No atomic ingestion (Finding #6). |
| A05: Security Misconfiguration | ✅ Low risk | `.env.example` provides good defaults. No exposed endpoints. |
| A06: Vulnerable Components | ✅ Low risk | No exploitable CVEs (see Dependency Audit). |
| A07: Auth Failures | ✅ N/A | Local-only tool. No auth needed. |
| A08: Software/Data Integrity | ⚠️ Partial | No file hash verification (Finding #6). ONNX model downloaded via HTTPS with HF integrity checks — acceptable. |
| A09: Logging & Monitoring | ✅ N/A | No logging of PII. Errors go to stderr. |
| A10: SSRF | ✅ N/A | No server-side requests from user input. |

---

## Findings Summary

| # | Severity | Title | Action Required |
|---|----------|-------|----------------|
| 1 | MEDIUM | Path traversal via CLI `ingest` | Add path canonicalisation and optional root confinement |
| 2 | LOW | Shell injection via CLI arguments | Use standard parsers (argparse/click/typer) — effectively mitigated |
| 3 | MEDIUM | ChromaDB data exposure via CLI | Document single-user limitation; recommend filesystem permissions |
| 4 | **HIGH** | Race condition in concurrent ChromaDB writes | **MUST FIX**: Serialise ChromaDB writes with a lock |
| 5 | **HIGH** | Ollama embedding overload from parallelism | **MUST FIX**: Add semaphore for concurrent embedding calls |
| 6 | MEDIUM | Incomplete ingestion state on failure | Add file hash deduplication and `--skip-existing` flag |
| 7 | MEDIUM | Ctrl+C during parallel ingestion | Add SIGINT handler with graceful shutdown |
| 8 | LOW | sys.argv exposure in error messages | Sanitise error messages |
| 9 | MEDIUM | ANSI escape injection in progress display | Strip control characters from filenames in progress output |
| 10 | LOW | PATH/shell alias injection | Document; not a code issue |

---

## Recommendations

### Before Merging (BLOCKERS)
1. **Serialise ChromaDB writes** — use `threading.Lock` around all `VectorStoreIndex` creation and `_get_chroma_collection()` calls
2. **Limit concurrent embedding calls** — `BoundedSemaphore(2)` before Ollama API calls

### Before Release (HIGH PRIORITY)
3. Add path resolution and optional root confinement for CLI `ingest`
4. Implement graceful SIGINT/SIGTERM handling for parallel ingestion
5. Add file deduplication via content hash to prevent duplicate ingestion

### Nice to Have (MEDIUM PRIORITY)
6. Document ChromaDB filesystem permission recommendations
7. Strip control characters from filenames displayed in progress bars
8. Sanitise error messages to avoid echoing raw user input
9. Add a `--version` flag for binary verification

### Dependency Management
- No immediate action required — no exploitable CVEs
- Monitor `chromadb` for CVEs related to SQLite write concurrency
- Pin `onnxruntime` to a version range that excludes CVE-2025-51480 (already done: `<1.26.0` excludes the vulnerable range)

---

## Escalation Assessment

**No BLOCKED-level findings.** All issues are mitigatable with straightforward code changes. The two HIGH-severity findings (#4 and #5) are reliability/data-integrity concerns rather than remote exploitation risks, consistent with the local-only threat model.

**Recommendation**: Proceed with implementation, addressing findings #1–#7 in the first PR. Findings #8–#10 can be addressed in a follow-up.
