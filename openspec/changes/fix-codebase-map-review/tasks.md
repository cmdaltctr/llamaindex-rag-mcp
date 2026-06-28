## 1. H1 — Path boundary validation

- [x] 1.1 Add `Path.resolve().relative_to(Path.cwd())` check in `get_codebase_map_text()` after `is_dir()` check, before cache lookup. Return error dict on `ValueError`.
- [x] 1.2 Run existing boundary tests: `uv run pytest tests/security/test_codebase_map_boundary.py -v`
- [x] 1.3 Verify tests fail without the fix (revert, run, re-apply) — optional but recommended

## 2. H2 — Document graph collection

- [x] 2.1 In `build_codebase_map()`, fetch ChromaDB collection: `chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)` → `db.get_collection("documents")` wrapped in try/except. Import `CHROMA_PERSIST_DIR` from `config.py`.
- [x] 2.2 Pass the collection object to `build_document_graph(collection)` at line 522 instead of `build_document_graph(None)`. If collection is unavailable, skip document graph section (log warning).
- [x] 2.3 Fix duplicate `build_code_graph()` call: reuse `code_graph` variable from line 494 in the cross-links section (line 542) instead of rebuilding.
- [x] 2.4 Pass the collection to `build_document_graph()` in the cross-links section (line 543) as well.
- [x] 2.5 Write unit test: `build_codebase_map()` with a mock collection produces non-empty `doc_communities`.

## 3. H3 — Inheritance edges

- [x] 3.1 Add `inheritance=ast.inheritance` to `graph.add_node()` in `build_code_graph()` (line 483-491).
- [x] 3.2 Rewrite `_get_inheritance()` to return `node_data.get("inheritance", [])` instead of `[]`.
- [x] 3.3 Write regression test: two files with `class Child(Parent)` and `class Parent` produce an inheritance edge in the code graph.
- [x] 3.4 Run existing code graph tests: `uv run pytest tests/unit/test_code_graph.py -v`

## 4. M1 — File count/depth limits

- [x] 4.1 Add `CODEBASE_MAP_MAX_FILES` (default 5000) and `CODEBASE_MAP_MAX_DEPTH` (default 10) to `config.py`.
- [x] 4.2 Enforce `CODEBASE_MAP_MAX_FILES` in `detect_file_types()` — truncate file list and log warning.
- [x] 4.3 Enforce `CODEBASE_MAP_MAX_DEPTH` in directory traversal (both Magika and suffix scanner).
- [x] 4.4 Add 30-second subprocess timeout to `scan_with_magika()` — fall back to suffix on timeout.
- [x] 4.5 Add `CODEBASE_MAP_MAX_FILES` and `CODEBASE_MAP_MAX_DEPTH` to `.env.example`.

## 5. M2 — Cache gitignore

- [x] 5.1 Add `.opencode/codebase-graph.json` and `.opencode/magika-inventory.json` to `.gitignore`.

## 6. M3 — Magika exclusion alignment

- [x] 6.1 Extract shared `_EXCLUDED_DIRS` set in `codebase_map.py` (`.git`, `node_modules`, `__pycache__`, `.venv`, `.pytest_cache`, `dist`, `build`).
- [x] 6.2 Use `_EXCLUDED_DIRS` in `scan_with_magika()` (pass to Magika or filter results).
- [x] 6.3 Use `_EXCLUDED_DIRS` in `scan_with_suffix()` directory traversal.

## 7. Tests & verification

- [x] 7.1 Run fast tests: `uv run pytest -m "not slow" -v`
- [x] 7.2 Run coverage: `uv run pytest -m "not slow" --cov=rag_mcp`
- [x] 7.3 Verify no regressions in existing `test_codebase_map.py`, `test_code_graph.py`, `test_doc_graph.py`

## 8. Deferred (post-merge)

- [ ] 8.1 Manual test: `get_codebase_map` on this codebase — verify output is compact, accurate, and ≤800 tokens (original task 11.3)
- [ ] 8.2 Manual test: OpenCode agent starts with codebase map in system prompt (original task 8.4)
- [ ] 8.3 Manual test: OpenCode agent reduced exploration calls (original task 11.4)
- [ ] 8.4 Experiment 10.1: document similarity threshold calibration
- [ ] 8.5 Experiment 10.2: code community detection quality
- [ ] 8.6 Experiment 10.3: type-aware chunking retrieval quality
- [ ] 8.7 Experiment 10.4: Azure table extraction quality
- [ ] 8.8 Experiment 10.5: full pipeline end-to-end on 3 projects
