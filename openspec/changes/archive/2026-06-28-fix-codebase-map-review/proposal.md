## Why

A post-implementation review of the `add-fast-context-codebase-map` change identified three HIGH-severity bugs that make the codebase map feature unsafe or non-functional before merge: (1) `get_codebase_map` accepts arbitrary paths like `/etc` with no boundary check, (2) `build_document_graph(None)` is hardcoded so document communities and cross-links never appear, and (3) `_get_inheritance()` always returns `[]` so class hierarchy edges are invisible. Three MEDIUM-severity hardening items (file count/depth limits, cache files in `.gitignore`, Magika exclusion alignment) should also be addressed before merge.

## What Changes

- **H1 — Path boundary validation**: Add `Path.resolve().relative_to(Path.cwd())` check in `get_codebase_map_text()` to reject paths outside the project root. Regression tests already exist in `test_codebase_map_boundary.py`.
- **H2 — Document graph collection**: Fetch the actual ChromaDB collection in `build_codebase_map()` and pass it to `build_document_graph()` instead of `None`. Also fix the duplicate `build_code_graph()` call in the cross-links section.
- **H3 — Inheritance edges**: Store `ast.inheritance` on graph nodes in `build_code_graph()` and rewrite `_get_inheritance()` to read from node data instead of returning `[]`.
- **M1 — File count/depth limits**: Add `CODEBASE_MAP_MAX_FILES` (default 5000) and `CODEBASE_MAP_MAX_DEPTH` (default 10) to `config.py`. Enforce in `detect_file_types()`. Add subprocess timeout (30s) to Magika shell-out.
- **M2 — Cache gitignore**: Add `.opencode/codebase-graph.json` and `.opencode/magika-inventory.json` to `.gitignore`.
- **M3 — Magika exclusion alignment**: Sync excluded directories (`.git`, `node_modules`, `__pycache__`, `.venv`) between Magika scanner and suffix scanner.
- **Deferred**: Manual tests (tasks 8.4, 11.3, 11.4) and experiments (10.1–10.5) remain post-merge as in the original change.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `codebase-map`: Add path boundary validation requirement, file count/depth limits requirement, and cache file gitignore requirement
- `code-graph`: Fix inheritance edge construction — node must store `inheritance` data from AST extraction
- `document-graph`: Fix collection parameter — `build_document_graph()` must receive actual ChromaDB collection, not `None`

## Impact

- **Modified files**: `codebase_map.py` (H1, H2, M1, M3), `code_graph.py` (H3), `config.py` (M1), `.gitignore` (M2)
- **New tests**: `test_codebase_map_boundary.py` already exists (H1); new regression test for inheritance edges (H3)
- **No new dependencies**: All fixes use existing libraries (`pathlib`, `chromadb`, `networkx`)
- **Architecture invariants preserved**: `config.py` remains single source of truth, no cross-imports, no PyTorch, no cloud services
