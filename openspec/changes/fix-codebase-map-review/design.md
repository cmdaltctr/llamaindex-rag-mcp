## Context

The `add-fast-context-codebase-map` change introduced a `get_codebase_map` MCP tool that builds a compact codebase map from file types, code communities, document communities, and cross-links. A post-implementation review found three HIGH-severity bugs and three MEDIUM-severity hardening gaps. All fixes are surgical — no new modules, no new dependencies, no architectural changes.

Current state of the affected code:

- `get_codebase_map_text()` in `codebase_map.py:642-689` resolves the path and checks `exists()` + `is_dir()` but never validates the path is within the project root. The watcher module (`watcher.py:222-242`) already implements the correct `relative_to()` pattern.
- `build_codebase_map()` in `codebase_map.py:469-563` calls `build_document_graph(None)` at lines 522 and 543. The `None` collection causes `build_document_graph()` to return an empty graph immediately (`doc_graph.py:308-309`), so document communities and cross-links are never produced.
- `build_code_graph()` in `code_graph.py:452-524` stores `functions`, `imports`, `classes`, and `exports` on graph nodes but **not** `inheritance`. The `_get_inheritance()` function at line 527-535 returns `[]` unconditionally, so inheritance edges are never added despite AST extraction working correctly.
- `detect_file_types()` has no file count or depth limits — scanning a monorepo with 100k files would hang.
- Cache files (`.opencode/codebase-graph.json`, `.opencode/magika-inventory.json`) are not in `.gitignore`.
- Magika and suffix scanner have different directory exclusion lists.

## Goals / Non-Goals

**Goals:**

- Fix all three HIGH-severity bugs so the codebase map feature is safe and functional
- Address MEDIUM-severity hardening items (limits, gitignore, exclusion alignment)
- All fixes pass the existing test suite plus new regression tests

**Non-Goals:**

- Optimising O(n²) loops in document graph edge computation (post-merge)
- Running experiments 10.1–10.5 or manual tests 8.4/11.3/11.4 (post-merge)
- Redesigning the document graph or cross-link architecture
- Adding new MCP tools or changing the tool interface

## Decisions

### D1: Path boundary check using `relative_to(Path.cwd())`

**Decision**: Add a `Path.resolve().relative_to(Path.cwd())` check in `get_codebase_map_text()` after the `is_dir()` check and before the cache lookup. On `ValueError`, return `{"status": "error", "message": "Path ... resolves outside the project root"}`.

**Rationale**: This is the same pattern used in `watcher.py:222-242`. The regression tests in `test_codebase_map_boundary.py` already test this exact behaviour and were written to fail against the unpatched code.

**Alternative considered**: Restricting to a configurable `PROJECT_ROOT` env var. Rejected — `Path.cwd()` is the natural project root for an MCP tool that defaults to `path="."`, and adding config increases surface area for no benefit.

### D2: Fetch ChromaDB collection in `build_codebase_map()`

**Decision**: In `build_codebase_map()`, obtain the collection via `chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)` → `db.get_collection("documents")` (same pattern as `retrieval.py:601-604`). Pass the collection object to `build_document_graph()`. If the collection doesn't exist or is empty, log a warning and skip document graph construction (graceful degradation — the code graph and file inventory still work).

**Rationale**: The document graph functions (`compute_similarity_edges`, `compute_metadata_edges`, `compute_heading_edges`) all accept a `collection` parameter and already handle `None` by returning `[]`. Passing the real collection activates all three edge types.

**Alternative considered**: Passing the collection through `get_codebase_map_text()` from the MCP handler. Rejected — `build_codebase_map()` is the orchestrator and should own its dependencies. The MCP handler stays thin per invariant #3.

### D3: Fix duplicate `build_code_graph()` call

**Decision**: In the cross-links section of `build_codebase_map()` (lines 536-550), reuse the `code_graph` variable from the code graph section (line 494) instead of calling `build_code_graph(code_files, path)` a second time.

**Rationale**: The current code builds the entire code graph, discards it, then builds it again. This doubles the AST extraction cost for no reason. The `code_graph` variable is already in scope.

### D4: Store `inheritance` on graph nodes

**Decision**: Add `inheritance=ast.inheritance` to the `graph.add_node()` call in `build_code_graph()` at line 483-491. Rewrite `_get_inheritance()` to return `node_data.get("inheritance", [])`.

**Rationale**: The AST extraction already populates `result.inheritance` correctly (verified by tests at `test_code_graph.py:37-42` and `:58-63`). The data is just not stored on the node. This is a two-line fix.

### D5: File count/depth limits via config

**Decision**: Add `CODEBASE_MAP_MAX_FILES` (default 5000) and `CODEBASE_MAP_MAX_DEPTH` (default 10) to `config.py`. Enforce in `detect_file_types()` by truncating the file list and logging a warning. Add a 30-second subprocess timeout to the Magika shell-out in `scan_with_magika()`.

**Rationale**: Prevents unbounded scanning on monorepos or directory trees with no depth limit. The defaults are generous enough for normal projects but prevent hangs on pathological inputs.

### D6: Cache files in `.gitignore`

**Decision**: Add `.opencode/codebase-graph.json` and `.opencode/magika-inventory.json` to `.gitignore`.

**Rationale**: These are per-project cache artefacts keyed by git commit hash. They should never be committed.

### D7: Align Magika and suffix scanner exclusions

**Decision**: Extract a shared `_EXCLUDED_DIRS` set (e.g., `{".git", "node_modules", "__pycache__", ".venv", ".pytest_cache", "dist", "build"}`) and use it in both `scan_with_magika()` and `scan_with_suffix()`.

**Rationale**: Currently the two scanners skip different directories, so the file inventory differs depending on whether Magika is installed. A shared exclusion list ensures consistent results.

## Risks / Trade-offs

- **[Risk] ChromaDB not initialised when `get_codebase_map` is called** → Mitigation: `db.get_collection()` raises if the collection doesn't exist; catch and log warning, skip document graph. Code graph and file inventory still work.
- **[Risk] `Path.cwd()` differs from the intended project root** → Mitigation: The MCP tool defaults to `path="."` which resolves to `cwd`. If a user passes a subdirectory of `cwd`, `relative_to` succeeds. If they pass a sibling or parent, it's correctly rejected.
- **[Risk] `CODEBASE_MAP_MAX_FILES` truncation hides files** → Mitigation: Log a warning with the truncated count. The limit is configurable via env var for large projects.
- **[Trade-off] O(n²) loops in document graph remain** → Accepted for now. Post-merge optimisation can use numpy vectorisation or approximate nearest neighbours.
