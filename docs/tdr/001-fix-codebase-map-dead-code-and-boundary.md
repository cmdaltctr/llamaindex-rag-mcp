# TDR-001: Fix codebase map dead code and missing boundary validation

**Date:** 2026-06-28
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** codebase-map | security | dead-code | magika

## Context

The `add-fast-context-codebase-map` change introduced a `get_codebase_map` MCP
tool that builds a compact codebase map from file types, code communities,
document communities, and cross-links. A post-implementation review found
three HIGH-severity bugs that made the feature unsafe or non-functional, plus
three MEDIUM-severity hardening gaps.

The architecture (ADR-022: tree-sitter code graph, ADR-023: embedding
similarity document graph) was correct — the implementations had wiring
omissions that prevented the architecture from functioning.

### Root Cause Analysis

**H1 — Path boundary validation missing.**
`get_codebase_map_text()` checked `exists()` and `is_dir()` but never validated
that the path was within the project root. An MCP caller could pass `/etc` or
`../secret` and receive a full file inventory of a directory outside the
project. The `watcher.py` module already implemented the correct
`Path.resolve().relative_to()` pattern — it was not applied to the new tool.

**H2 — Document graph received `None` collection.**
`build_codebase_map()` called `build_document_graph(None)` at two call sites.
`build_document_graph()` returns an empty graph immediately when `collection
is None` (`doc_graph.py:308-309`). This meant document communities and
cross-links were always empty — the entire ADR-023 document graph pipeline
was dead code. The ChromaDB collection was never fetched because the original
implementation hardcoded `None` instead of obtaining the real collection.

**H3 — Inheritance data not stored on graph nodes.**
`build_code_graph()` stored `functions`, `imports`, `classes`, and `exports`
on graph nodes but omitted `inheritance`. The companion function
`_get_inheritance()` returned `[]` unconditionally, so inheritance edges were
never added despite AST extraction producing correct `(child, parent)` pairs.

**Additional root cause — Python class regex too narrow.**
The regex `r"^\s*class\s+(\w+)\s*\(([^)]+)\):"` only matched classes with
parentheses (`class Foo(Bar):`). Classes without inheritance (`class Foo:`)
were never added to the `classes` list, so even with the H3 fix, inheritance
edges could never find their target parent class.

**M1 — No file count or depth limits.** `scan_with_suffix()` used unbounded
`rglob("*")`; `scan_with_magika()` had no subprocess timeout. Scanning a
monorepo with 100k files would hang indefinitely.

**M2 — Cache files not in `.gitignore`.** `.opencode/codebase-graph.json` and
`.opencode/magika-inventory.json` were untracked and could be accidentally
committed.

**M3 — Magika and suffix scanner had different exclusion lists.** The suffix
scanner excluded `.git`, `__pycache__`, `node_modules`, `.venv`, `.opencode`.
The Magika scanner had no exclusion filtering at all, so the file inventory
differed depending on which scanner was active.

## Decision

**H1**: Add `Path.resolve().relative_to(Path.cwd())` check in
`get_codebase_map_text()` after `is_dir()`, before cache lookup. Return
`{"status": "error", "message": "Path resolves outside the project root"}`
on `ValueError`. Same pattern as `watcher.py:222-242`.

```python
# codebase_map.py — get_codebase_map_text()
try:
    path_obj.relative_to(Path.cwd())
except ValueError:
    return json.dumps(
        {
            "status": "error",
            "message": f"Path resolves outside the project root: {path}",
        }
    )
```

**H2**: Fetch the real ChromaDB collection in `build_codebase_map()` using the
same pattern as `retrieval.py:601-604`, and pass it to
`build_document_graph()`. Graceful degradation if collection is unavailable.

```python
# codebase_map.py — build_codebase_map()
collection = None
try:
    import chromadb
    from .config import CHROMA_PERSIST_DIR

    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    collection = db.get_collection("documents")
    if collection.count() == 0:
        collection = None
except Exception as exc:
    logger.warning("Could not access ChromaDB collection: %s", exc)

doc_graph = build_document_graph(collection)  # was: build_document_graph(None)
```

Also fixed duplicate `build_code_graph()` call in cross-links section —
reused `code_graph` variable instead of rebuilding.

**H3**: Store `inheritance=ast.inheritance` on graph nodes. Rewrite
`_get_inheritance()` to read from node data. Fixed Python class regex to
match both `class Foo(Bar):` and `class Foo:`.

```python
# code_graph.py — build_code_graph()
graph.add_node(
    entry.path,
    type="file",
    content_type=f"{entry.group}/{entry.label}",
    functions=ast.functions,
    imports=ast.imports,
    classes=ast.classes,
    exports=ast.exports,
    inheritance=ast.inheritance,  # was missing
)


# code_graph.py — _get_inheritance()
def _get_inheritance(node_data: dict) -> list[tuple[str, str]]:
    return node_data.get("inheritance", [])  # was: return []


# code_graph.py — regex fix
r"^\s*class\s+(\w+)\s*(?:\(([^)]+)\))?\s*:"  # was: required (...)
```

**M1**: Added `CODEBASE_MAP_MAX_FILES=5000` and `CODEBASE_MAP_MAX_DEPTH=10`
to `config.py`. Enforce file truncation in `detect_file_types()`. Replaced
unbounded `rglob("*")` with depth-limited `_walk()` in `scan_with_suffix()`.
Added 30s `subprocess.run(timeout=30)` to `scan_with_magika()` with fallback
to suffix detection on `TimeoutExpired`.

**M2**: Added `.opencode/codebase-graph.json` and
`.opencode/magika-inventory.json` to `.gitignore`.

**M3**: Extracted shared `_EXCLUDED_DIRS` set in `codebase_map.py`, used by
both `scan_with_magika()` (post-filter results) and `scan_with_suffix()`
(pre-filter during traversal).

## Consequences

### Positive

- Document communities and cross-links now produce real output (ADR-023
  pipeline is fully active)
- Inheritance edges appear in the code graph (ADR-022 requirement met)
- Path boundary prevents directory traversal from MCP callers
- Monorepo scanning is bounded by file count, depth, and timeout
- File inventories are consistent regardless of Magika availability
- Cache files are gitignored

### Negative

- `CODEBASE_MAP_MAX_FILES` truncation silently drops files beyond the limit —
  communities may be incomplete for very large projects (mitigated by warning
  log and configurable env var)
- `CODEBASE_MAP_MAX_DEPTH` is not enforced in the Magika scanner (Magika CLI
  has no `--max-depth` flag); depth control is only effective for the suffix
  fallback. The 30s timeout and file count limit provide defense in depth.
- Cross-links section still calls `build_document_graph(collection)` a second
  time instead of reusing the `doc_graph` variable from the document graph
  section — minor performance waste, not a correctness issue.

### Neutral

- Three existing integration tests required `monkeypatch.chdir(tmp_path)` to
  pass `path="."` instead of `str(tmp_path)` — the boundary check correctly
  rejected the old pattern of passing absolute `tmp_path` from outside `cwd`.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Configurable `PROJECT_ROOT` env var for boundary | `Path.cwd()` is the natural project root for an MCP tool that defaults to `path="."`. Adding config increases surface area for no benefit. |
| Pass ChromaDB collection from MCP handler | `build_codebase_map()` is the orchestrator and should own its dependencies (invariant #3: server.py is a thin wrapper). |
| Pure tree-sitter node traversal for inheritance | ADR-022 already decided on regex extraction alongside tree-sitter for robustness and multi-language support. |
| Post-filter Magika results by path depth | Magika CLI has no depth flag; post-filtering would require parsing every result line. The 30s timeout + file count limit are sufficient. |

## How to Recognise / Handle This Again

1. **Document communities always empty**: Check if `collection` is `None` in
   `build_codebase_map()`. Run `python -c "import chromadb; db =
   chromadb.PersistentClient(path='chroma_db'); print(db.get_collection
   ('documents').count())"` to verify the collection exists and is populated.

2. **Inheritance edges missing**: Check if graph nodes have an `inheritance`
   key: `graph.nodes["file.py"].get("inheritance")` should return a list of
   `(child, parent)` tuples, not `[]`. If empty, verify the AST extraction
   produces inheritance pairs via `extract_ast_relationships()`.

3. **Path boundary rejection on valid paths**: The boundary check uses
   `Path.cwd()`. If tests pass absolute `tmp_path` values, they must
   `monkeypatch.chdir(tmp_path)` first and use `path="."`.

4. **Magika scan hangs on large projects**: Check if the 30s timeout is
   triggering the fallback. Look for the warning log "Magika scan timed out
   after 30s". Increase `CODEBASE_MAP_MAX_FILES` if the project legitimately
   has more files.

5. **Different file counts between Magika and suffix scanner**: Verify
   `_EXCLUDED_DIRS` is used in both `scan_with_magika()` and
   `scan_with_suffix()`. The sets must match.

## Revisit Triggers

- **Magika CLI adds `--max-depth` flag**: Revisit M1 to enforce depth in the
  Magika scanner directly, removing the gap with the suffix scanner.
- **Project exceeds 5000 files regularly**: Raise `CODEBASE_MAP_MAX_FILES`
  default or make it adaptive based on project size.
- `DOC_SIMILARITY_THRESHOLD` calibrated via experiment 10.1**: May affect
  document graph edge density and community quality.
- **ChromaDB collection schema changes**: The `db.get_collection("documents")`
  call assumes the collection name is `"documents"`. If multi-collection
  support is added (ADR-011), this needs updating.

## References

- ADR-022: Code graph via tree-sitter AST extraction (`docs/adr/022-code-graph-via-tree-sitter-ast.md`)
- ADR-023: Document graph via embedding similarity (`docs/adr/023-document-graph-via-embedding-similarity.md`)
- OpenSpec change: `openspec/changes/fix-codebase-map-review/`
- Original change: `openspec/changes/add-fast-context-codebase-map/`
- `src/rag_mcp/codebase_map.py` — H1, H2, M1, M3 fixes
- `src/rag_mcp/code_graph.py` — H3 fix + regex fix
- `src/rag_mcp/config.py` — M1 config constants
- `tests/security/test_codebase_map_boundary.py` — H1 regression tests
- `tests/unit/test_code_graph.py` — H3 regression tests
- `tests/unit/test_codebase_map.py` — H2 unit tests
