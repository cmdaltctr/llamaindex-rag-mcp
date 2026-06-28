# Security Assessment: add-fast-context-codebase-map

## Summary
- **Date**: 2026-06-28
- **Scope**: `codebase_map.py`, `code_graph.py`, `doc_graph.py`, `azure_reader.py`, `config.py`, `server.py`, `ingestion.py`, `.opencode/plugins/fast-context.ts`, `.env.example`
- **Auditor**: a-security
- **Verdict**: NEEDS FIXES

## Findings

### [HIGH] H1 — No path boundary validation in `get_codebase_map`

**Location**: `src/rag_mcp/codebase_map.py:656-664` (`get_codebase_map_text`)

**Vulnerability**: The `get_codebase_map` MCP tool accepts an arbitrary `path` parameter from the caller. While `Path(path).expanduser().resolve()` normalises the path and resolves `..` segments, there is no check that the resolved path falls within an expected project boundary. An MCP client (or AI agent) could pass `path=/etc`, `path=/Users`, or any directory on the filesystem and receive a full file-type inventory and dependency graph of that directory.

**Attack Vector**: A compromised or misdirected AI agent calling the MCP tool with a path outside the intended project scope. Also: a symlink within the project directory pointing outside (e.g., `ln -s /etc/passwd ./symlink`) would be followed by `Path.resolve()` and the Magika `-r` flag, exposing files outside the project.

**Impact**: Information disclosure — file types and internal project structure of arbitrary directories become readable via the MCP tool. On a single-user machine this is low-impact (the user can already read those files), but in a multi-agent or shared environment it constitutes unintended filesystem access.

**Mitigation**:
```diff
  def get_codebase_map_text(path: str = ".", refresh: bool = False) -> str:
      try:
          path_obj = Path(path).expanduser().resolve()
          if not path_obj.exists():
              ...
          if not path_obj.is_dir():
              ...
+         # Prevent traversal outside the current working directory tree.
+         cwd = Path.cwd().resolve()
+         try:
+             path_obj.relative_to(cwd)
+         except ValueError:
+             return json.dumps({
+                 "status": "error",
+                 "message": f"Path is outside the project directory: {path}",
+             })
```

**The watcher module** (`src/rag_mcp/watcher.py:226`) already implements the same `relative_to()` boundary check — `codebase_map` should adopt the same pattern.

**Regression test**: [`tests/security/test_codebase_map_boundary.py`](../../tests/security/test_codebase_map_boundary.py) — 3 tests written by `@a-test` (TDD red state verified: 2 fail before fix, 1 passes). Tests cover: absolute path outside project (`/etc`), current directory works, and `../` escape path. Run with: `uv run pytest tests/security/test_codebase_map_boundary.py -v`.

---

### [MEDIUM] M1 — No depth or file-count limits on filesystem traversal

**Location**: 
- `src/rag_mcp/codebase_map.py:207` — `scan_with_suffix()` uses `project_root.rglob("*")` with no limits
- `src/rag_mcp/ingestion.py:114` — `_gather_supported_files()` uses `path_obj.rglob(f"*{ext}")` with no limits
- `src/rag_mcp/codebase_map.py:150` — Magika `-r` flag scans recursively with no limit

**Vulnerability**: Scanning a directory with a very large number of files (e.g., Linux kernel source at 70k+ files, or a project with deeply nested `node_modules`) can cause resource exhaustion — memory for storing all `FileEntry` objects and CPU for AST parsing each code file.

**Attack Vector**: An MCP caller passes a path to a massive directory tree. The server enumerates all files, builds a NetworkX graph of all code relationships, and stores the results in memory — potentially exhausting memory or taking minutes to complete.

**Impact**: Denial of service via resource exhaustion. The MCP server process could be killed by OOM or become unresponsive until the scan completes.

**Mitigation**:
1. Add a configurable `CODEBASE_MAP_MAX_FILES` limit (default: 5000) in `config.py`
2. Add a `CODEBASE_MAP_MAX_SCAN_DEPTH` (default: 10) for directory depth
3. Add a timeout on the Magika subprocess call
4. Skip known-large directories like `node_modules`, `.git`, `__pycache__`, `.venv`, `.opencode` (the suffix scan already does this for some)

**Note**: The suffix-based fallback scanner already skips `node_modules`, `.venv`, `.git`, `.opencode`, and `__pycache__` (line 210-212). Magika's `-r` does NOT skip these directories and would scan everything.

---

### [MEDIUM] M2 — Cache files not protected from accidental git commit

**Location**: 
- `src/rag_mcp/config.py:276` — `CODEBASE_MAP_CACHE_DIR = os.getenv("CODEBASE_MAP_CACHE_DIR", ".opencode")`
- `src/rag_mcp/codebase_map.py:336-337` — `_save_cache()` writes to `.opencode/codebase-graph.json`
- `.opencode/.gitignore` — does not exclude `codebase-graph.json` or `magika-inventory.json`

**Vulnerability**: The codebase map cache is written to `.opencode/codebase-graph.json`. The `.opencode/` directory is tracked in git (contains commands, skills, opencode.json). The nested `.opencode/.gitignore` only excludes `node_modules`, `package.json`, `package-lock.json`, `bun.lock`, and `.gitignore` — it does NOT exclude auto-generated cache files. If a developer runs `git add .opencode/` or `git add .`, the cache JSON could be committed.

**Impact**: Accidental exposure of codebase structure information in the git repository. The cache contains a full file inventory plus community/hub analysis — not secrets, but not intended for version control either.

**Mitigation**:
Add the following to `.opencode/.gitignore`:
```gitignore
# Auto-generated codebase map cache files
codebase-graph.json
magika-inventory.json
```

---

### [LOW] L1 — Magika `-r` flag scans unfiltered (no directory exclusion)

**Location**: `src/rag_mcp/codebase_map.py:150-154`

**Vulnerability**: When Magika is used for file-type detection, the `-r` flag recursively scans the entire directory tree including `node_modules`, `.git`, `__pycache__`, and other directories that the suffix-based fallback correctly skips. This creates a discrepancy: the presence of Magika makes the scan SLOWER and more resource-intensive than without it.

**Impact**: Performance degradation and potential resource exhaustion when Magika is installed.

**Mitigation**: Use Magika's `--exclude` flag or pre-filter directories before passing to Magika. Alternatively, use `scan_with_suffix()` for directory filtering, then augment with Magika results for detected files.

---

### [LOW] L2 — MAGIKA_BINARY environment variable allows arbitrary executable

**Location**: `src/rag_mcp/config.py:248` → `src/rag_mcp/codebase_map.py:151`

**Vulnerability**: The `MAGIKA_BINARY` env var controls which binary is executed via `subprocess.run()`. While `shutil.which(MAGIKA_BINARY)` validates that the binary exists on `$PATH`, it allows any executable on the path. An attacker with environment control could set `MAGIKA_BINARY=python3` and pass a malicious script as the `path` argument (though `path` must resolve to an existing directory).

**Impact**: Low — requires control of the server's environment variables AND a crafted directory on disk. For a local single-user MCP server, the attacker is the user.

**Mitigation**: Consider validating that `MAGIKA_BINARY` resolves to a binary named `magika` specifically, or pin it to a known safe set of names.

---

### [LOW] L3 — OpenCode plugin error swallowing could inject malformed content

**Location**: `.opencode/plugins/fast-context.ts:31-36`

**Vulnerability**: The plugin checks for error responses using a simple string match:
```ts
if (text && !text.includes('"status": "error"')) {
    output.system.push(`# Codebase Map\n\n${text}`);
}
```
If the codebase map tool returns a response that contains the string `"status": "error"` as part of legitimate content (unlikely but possible — e.g., in a file path or code content), the map would be incorrectly suppressed. Conversely, if the error format changes (e.g., to `"status": "fail"`), a genuine error would be injected into the system prompt.

**Impact**: Low — at worst, error text is injected as system prompt context; at best, a valid map is suppressed. No code execution vector.

**Mitigation**: Parse the response as JSON and check the `status` field structurally rather than via string match. If the response is a formatted text map (non-JSON), treat it as valid.

---

### [INFO] I1 — Symlink handling inconsistency between Magika and suffix scan

- **Magika `-r`**: May follow symlinks (behaviour depends on Magika version and OS)
- **Python `rglob("*")`**: Does NOT follow symlinks (Python 3.11+ default)
- **`Path.resolve()`**: DOES follow symlinks

This means the suffix-based scanner won't traverse into symlinked directories, but Magika might. If Magika is installed and encounters a symlink loop, it could cause infinite recursion or resource exhaustion.

**Recommendation**: Add explicit symlink checks and document the expected behaviour. Consider using `Path.is_symlink()` to skip symlinks before passing to Magika.

---

### [INFO] I2 — No `.env` committed, credentials well-managed

Verified that `.env` is gitignored (`.gitignore` line 16) and not in git history. Azure credentials (`AZURE_DOC_INTELLIGENCE_ENDPOINT`, `AZURE_DOC_INTELLIGENCE_KEY`) are:
- Read from environment only (`config.py:282-283`)
- Validated at config load time (`config.py:288-293`) — if missing when `DOCUMENT_BACKEND=azure`, backend falls back to `local`
- Not hardcoded or logged in error paths (verified `azure_reader.py` log statements)

---

## Dependency CVE Audit

```
$ uv pip check
Checked 155 packages in 3ms
All installed packages are compatible
```

No dependency conflicts or known CVEs detected by `uv pip check`.

**New dependencies introduced by this change**:

| Package | Version | Source | Assessment |
|---------|---------|--------|-----------|
| `tree-sitter` | 0.25.2 | PyPI | Active maintenance, MIT license. AST parsing only — no network access. |
| `tree-sitter-language-pack` | 1.10.9 | PyPI | Community-maintained parser collection. Compiled parsers, no runtime execution. |
| `networkx` | 3.6.1 | PyPI | Well-established (3.0k+ GitHub stars). Pure Python graph library — no C extensions. |
| `azure-ai-documentintelligence` | 1.0.2 | PyPI (optional) | Microsoft official SDK. In `[azure]` optional extra — not installed by default. |

No CVEs requiring action. Azure SDK is gated behind optional `[azure]` extra and disabled by default.

**Confirmed by `@a-tech-researcher`** (cross-referenced OSV.dev, GHSA, NVD, and Tavily):

| Package | Version | CVEs (CRITICAL/HIGH) | Status |
|---------|---------|---------------------|--------|
| `tree-sitter` | 0.25.2 | 0 CVEs | Clean |
| `tree-sitter-language-pack` | 1.10.9 | 0 CVEs | Clean |
| `networkx` | 3.6.1 | 0 CVEs | Clean |
| `azure-ai-documentintelligence` | 1.0.2 | CVE-2025-30387 (CVSS 9.8 CRITICAL) | **NOT reachable** — affects Azure cloud Studio service, not the PyPI client SDK. Patched server-side July 2025. |

Project usage patterns (local-file AST parsing, internally-constructed NetworkX graphs, standard SDK HTTP client) carry no additional reachability risk. No version bumps required.

---

## OWASP Top 10 Coverage

| ID | Category | Status | Notes |
|----|----------|--------|-------|
| A01 | Broken Access Control | N/A | Local MCP server — no multi-tenant access control. Tool inputs are trusted (user is the operator). |
| A02 | Cryptographic Failures | ✓ | No cryptography in the codebase map feature. Azure credentials use HTTPS transport (Azure SDK). |
| A03 | Injection | ⚠ | Magika subprocess uses argument array (safe from shell injection) but lacks `--` separator for path arguments (see H1 audit note). Code graph import resolution uses regex on source files, not user input — no injection vector. |
| A04 | Insecure Design | ⚠ | No path-boundary enforcement (see H1). Cache directory shared with git-tracked `.opencode/` (see M2). |
| A05 | Security Misconfiguration | ✓ | Azure credentials validated at load time. Default backend is `local` (no cloud). |
| A06 | Vulnerable Components | ✓ | `uv pip check` clean. All new deps from PyPI, pinned in `uv.lock`. |
| A07 | Identification & Auth Failures | N/A | No authentication — local stdio MCP server. |
| A08 | Software & Data Integrity | ✓ | Dependencies locked via `uv.lock`. No runtime code fetching. |
| A09 | Security Logging & Monitoring | ⚠ | Azure errors log exception details — could include sensitive data in edge cases. Recommend sanitising Azure API exceptions before logging. |
| A10 | SSRF | N/A | No server-side URL fetching in the codebase map feature. Azure SDK handles HTTPS connections to a configured endpoint. |

## Verdict Justification

The change adds significant new surface area (filesystem traversal, subprocess execution, graph construction from AST) but the security posture is reasonable for a **local, single-user MCP server**. No CRITICAL findings were identified — no hardcoded secrets, no remote code execution vectors, and no authentication bypass concerns (the server has no authentication).

Two HIGH findings warrant fixes before merge:
1. **H1**: Missing path boundary validation in `get_codebase_map` — the watcher already has this pattern; it should be replicated in the codebase map for consistency and defence in depth.
2. **M1**: No depth/file-count limits on traversal — a large directory could cause resource exhaustion. The suffix scanner already skips known-large directories but Magika does not.

The MEDIUM finding (M2 — cache files not gitignored) is a simple fix. The LOW findings are hardening opportunities that can be addressed post-merge.

**Verdict**: NEEDS FIXES — H1 and M1 must be addressed before merge. M2 and LOW items are recommended but not blocking.
