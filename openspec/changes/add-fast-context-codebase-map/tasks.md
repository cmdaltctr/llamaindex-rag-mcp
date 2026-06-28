## 1. Configuration & Dependencies

- [x] 1.1 Add `tree-sitter`, `tree-sitter-language-pack`, and `networkx` to `[project.dependencies]` in `pyproject.toml`
- [x] 1.2 Add `azure-ai-documentintelligence` to `[project.optional-dependencies]` under `azure` extra in `pyproject.toml`
- [x] 1.3 Add new constants to `config.py`: `MAGIKA_BINARY`, `DOC_SIMILARITY_THRESHOLD`, `DOCUMENT_BACKEND`, `AZURE_DOC_INTELLIGENCE_ENDPOINT`, `AZURE_DOC_INTELLIGENCE_KEY`, `AZURE_DOC_INTELLIGENCE_MODEL`, `CODEBASE_MAP_CACHE_DIR`, and `MAGIKA_LABEL_TO_TREESITTER` language mapping
- [x] 1.4 Add `DOCUMENT_BACKEND` validation logic in `config.py` (accept `"local"` / `"azure"`, warn + fallback on unknown)
- [x] 1.5 Add Azure credential validation at config load time (fallback to `"local"` if credentials missing when `DOCUMENT_BACKEND=azure`)
- [x] 1.6 Update `.env.example` with all new environment variables
- [x] 1.7 Run `uv sync` and verify all base dependencies resolve

## 2. Magika Integration (codebase_map.py)

- [x] 2.1 Create `src/rag_mcp/codebase_map.py` with `from __future__ import annotations`, type annotations, Google-style docstrings
- [x] 2.2 Implement `scan_with_magika(path: str) -> list[FileEntry]` — shell out to `magika -r <path> --jsonl`, parse JSONL output
- [x] 2.3 Implement `scan_with_suffix(path: str) -> list[FileEntry]` — fallback using `Path.suffix` → group/label mapping
- [x] 2.4 Implement `detect_file_types(path: str) -> FileInventory` — try Magika, fallback to suffix, detect mismatches
- [x] 2.5 Implement `format_inventory(inventory: FileInventory) -> str` — compact text with counts, globs, binary warnings, mismatch warnings
- [x] 2.6 Write unit tests for Magika parsing, suffix fallback, mismatch detection, and binary flagging (`pytest -m "not slow"`)

## 3. Code Graph (code_graph.py)

- [x] 3.1 Create `src/rag_mcp/code_graph.py` with `from __future__ import annotations`
- [x] 3.2 Implement `extract_ast_relationships(file_path: str, content: str, language: str) -> ASTResult` — tree-sitter parsing for imports, exports, classes, inheritance
- [x] 3.3 Implement `build_code_graph(files: list[FileEntry], project_root: str) -> nx.DiGraph` — iterate code files, extract AST, build NetworkX DiGraph with node/edge metadata
- [x] 3.4 Implement `detect_communities(graph: nx.DiGraph) -> list[Community]` — `louvain_communities()` with labelling by top filenames + shared keywords
- [x] 3.5 Implement `detect_hubs(graph: nx.DiGraph) -> list[Hub]` — top 10% in-degree or in-degree ≥ 5
- [x] 3.6 Implement `detect_bridges(graph: nx.DiGraph, communities: list[Community]) -> list[Bridge]` — betweenness centrality for cross-community connectors
- [x] 3.7 Handle edge cases: unsupported language (skip AST, log debug), malformed source (partial extraction, log warning), self-imports (no self-loops), small graphs (<5 files → single community)
- [x] 3.8 Write unit tests for AST extraction (TypeScript imports, Python imports, class inheritance), graph construction, community detection, hub detection, and edge cases

## 4. Document Graph (doc_graph.py)

- [x] 4.1 Create `src/rag_mcp/doc_graph.py` with `from __future__ import annotations`
- [x] 4.2 Implement `compute_similarity_edges(collection, threshold: float) -> list[Edge]` — fetch embeddings from ChromaDB, compute pairwise cosine similarity, create edges above threshold
- [x] 4.3 Implement `compute_metadata_edges(collection) -> list[Edge]` — shared category edges (weight 1.0), shared keyword edges (weight 0.5)
- [x] 4.4 Implement `compute_heading_edges(collection) -> list[Edge]` — parent-child edges from markdown heading hierarchy
- [x] 4.5 Implement `build_document_graph(collection, threshold: float) -> nx.Graph` — combine all edge types into undirected graph
- [x] 4.6 Implement `detect_document_communities(graph: nx.Graph) -> list[Community]` — Louvain with community labels from representative categories
- [x] 4.7 Implement `compute_cross_links(code_graph: nx.DiGraph, doc_graph: nx.Graph) -> list[CrossLink]` — filename matching (≥2 path segments), symbol matching, category keyword overlap
- [x] 4.8 Write unit tests for similarity edges, metadata edges, heading edges, community detection, cross-link detection (including false positive prevention)

## 5. Graph Assembly & MCP Tool (codebase_map.py + server.py)

- [x] 5.1 Implement `build_codebase_map(path: str) -> CodebaseMap` in `codebase_map.py` — orchestrate Magika scan, code graph, document graph, cross-links, hubs
- [x] 5.2 Implement `format_codebase_map(map: CodebaseMap) -> str` — compact text output ≤800 tokens with File Types, Code Communities, Document Communities, Cross-links, Hubs sections
- [x] 5.3 Implement community truncation (>4 files → show top 4 + "... and N more")
- [x] 5.4 Implement caching: `load_cache(path) -> Optional[CodebaseMap]` and `save_cache(path, map)` — keyed by `git rev-parse HEAD`, stored in `.opencode/`
- [x] 5.5 Handle no-git case: build without caching, log info
- [x] 5.6 Add `get_codebase_map` MCP tool in `server.py` with `ToolAnnotations(readOnlyHint=True, destructiveHint=False)`, params `path: str = "."` and `refresh: bool = False`
- [x] 5.7 Ensure error handling returns `{"status": "error", "message": "..."}` — never raises from MCP handler
- [x] 5.8 Write integration tests for full build pipeline, caching, cache invalidation, and MCP tool invocation

## 6. Type-Aware Ingestion (ingestion.py)

- [x] 6.1 Modify `_read_and_chunk_file_async()` to accept `content_type: Optional[str]` parameter
- [x] 6.2 Add dispatch logic: `code/*` → `CodeSplitter(language=...)`, binary → skip, `config/*` → whole-file chunk, documents → existing splitter
- [x] 6.3 Add Magika detection call at start of `ingest_path_async()` for all files in the batch
- [x] 6.4 Add `content_type` metadata field to ChromaDB document metadata for all chunks
- [x] 6.5 Add `status="skipped"` support in `file_details` for binary files
- [x] 6.6 Ensure content_type takes precedence over extension (Magika says JS but file is `.txt` → use CodeSplitter)
- [x] 6.7 Ensure fallback when Magika unavailable (dispatch falls through to existing extension-based routing)
- [x] 6.8 Write unit tests for type dispatch, CodeSplitter routing, binary skip, content_type metadata, and fallback behaviour

## 7. Azure Document Intelligence (azure_reader.py)

- [x] 7.1 Create `src/rag_mcp/azure_reader.py` with `from __future__ import annotations`
- [x] 7.2 Implement `AzureDocReader` class — send document to Azure, receive structured JSON
- [x] 7.3 Implement `parse_azure_response(result) -> list[Document]` — convert Azure structured JSON to LlamaIndex Documents with paragraphs, tables, and metadata
- [x] 7.4 Implement table-aware chunking — tables as intact chunks with `content_type: "table"` metadata, large tables split into row groups
- [x] 7.5 Implement Azure heading/paragraph role extraction for document graph hierarchy edges
- [x] 7.6 Implement graceful fallback: network error → LiteParse chain, rate limit → retry once (5s delay) then fallback, missing credentials → config-time fallback to local
- [x] 7.7 Guard Azure SDK import at runtime (lazy import, never top-level)
- [x] 7.8 Integrate into `ingestion.py`: branch on `DOCUMENT_BACKEND=azure` for document files, bypassing PDF reader chain
- [x] 7.9 Write unit tests for Azure response parsing, table chunking, fallback paths, and import guarding

## 8. OpenCode Plugin (fast-context.ts)

- [x] 8.1 Create `.opencode/plugins/fast-context.ts` — thin plugin calling `get_codebase_map` via MCP
- [x] 8.2 Implement per-session caching via `injected` Set keyed by `sessionID`
- [x] 8.3 Inject map into `experimental.chat.system.transform` output
- [ ] 8.4 Manual test with OpenCode — verify map appears in agent system prompt

## 9. Documentation & ADRs

- [x] 9.1 Write ADR for code graph via tree-sitter AST extraction (docs/adr/)
- [x] 9.2 Write ADR for document graph via embedding similarity (docs/adr/)
- [x] 9.3 Write ADR for dual deployment modes — Full Local vs Hybrid (docs/adr/)
- [x] 9.4 Update `docs/guides/architecture.md` with new modules and data flow
- [x] 9.5 Update `docs/guides/configuration.md` with new environment variables
- [x] 9.6 Update `docs/guides/mcp-tools.md` with `get_codebase_map` tool reference
- [x] 9.7 Update `AGENTS.md` with new module inventory, architecture invariants, and gotchas
- [x] 9.8 Update `README.md` with fast context feature description

## 10. Experiments & Validation

- [ ] 10.1 Experiment: document similarity threshold calibration — test 0.80, 0.85, 0.90 on qwen3-embedding:0.6b output _(requires manual execution)_
- [ ] 10.2 Experiment: code community detection quality — verify communities match actual modules on the RAG MCP's own codebase _(requires manual execution)_
- [ ] 10.3 Experiment: type-aware chunking retrieval quality — compare CodeSplitter vs SentenceSplitter for code retrieval _(requires manual execution)_
- [ ] 10.4 Experiment: Azure table extraction quality — compare Azure-extracted table chunks vs LiteParse-flattened tables (hybrid mode) _(requires manual execution)_
- [ ] 10.5 Manual test: full pipeline end-to-end on 3 projects (this codebase, receipt-scanner, one code-heavy project) _(requires manual execution)_

## 11. Final Verification

- [x] 11.1 Run `uv run pytest -m "not slow" --cov=rag_mcp` — 549 passed, 88% overall coverage (core modules ≥90%)
- [x] 11.2 Run `uv run pytest -v` — all tests pass
- [ ] 11.3 Manual test: `get_codebase_map` on this codebase — verify output is compact, accurate, and ≤800 tokens _(requires manual execution)_
- [ ] 11.4 Manual test: OpenCode agent starts with codebase map in system prompt — verify reduced exploration calls _(requires manual execution)_
- [x] 11.5 Verify no regressions: existing `ingest_documents`, `search_documents`, `list_collections`, `delete_documents` tools unchanged
