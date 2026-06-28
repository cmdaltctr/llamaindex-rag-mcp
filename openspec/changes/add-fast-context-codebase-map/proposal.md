## Why

When an AI agent starts a session on an unfamiliar codebase, it burns 5–20 tool calls (~2,000+ tokens) on exploratory `list_directory`, `glob`, and `read_file` calls just to map the project before doing useful work. A pre-computed codebase map — file types, code communities, document topic clusters, and architectural hubs — eliminates this discovery phase entirely.

The RAG MCP already ingests and embeds documents but has no awareness of **code structure** (imports, call graphs, inheritance) or **file types** (binary vs. code vs. config). Adding a unified codebase graph that combines tree-sitter AST extraction for code with embedding-similarity clustering for documents gives agents a ground-truth map at session start.

## What Changes

- **New `get_codebase_map` MCP tool**: Returns a compact (~500–800 token) codebase map including file-type inventory, code communities, document communities, cross-links, and architectural hubs.
- **Magika file-type detection**: Classifies every file by content type (code, document, config, binary) using Google's Magika CLI — no LLM needed.
- **Code graph via tree-sitter**: Extracts imports, exports, function calls, and class inheritance from AST — builds a NetworkX directed graph with Louvain community detection.
- **Document graph from existing embeddings**: Computes pairwise cosine similarity on already-embedded document chunks + shared metadata categories — builds a NetworkX undirected graph with Louvain communities.
- **Cross-links between code and document communities**: Filename/symbol matching connects code modules to their documentation.
- **Type-aware ingestion**: Code files use `CodeSplitter` (tree-sitter boundaries); binary files are skipped; `content_type` metadata is added to ChromaDB.
- **Optional Azure Document Intelligence backend**: Hybrid deployment mode where document parsing uses Azure for structured table/layout extraction, while embeddings, code graph, and search stay fully local. Gated behind `DOCUMENT_BACKEND=azure` config flag with automatic fallback to LiteParse.
- **OpenCode plugin**: Thin `fast-context.ts` plugin calls `get_codebase_map` at session start and injects the result into the system prompt.

## Capabilities

### New Capabilities
- `codebase-map`: Magika file-type inventory + graph assembly + compact map generation via `get_codebase_map` MCP tool
- `code-graph`: tree-sitter AST extraction for code files → NetworkX directed graph with Louvain community detection and hub identification
- `document-graph`: Embedding-similarity + metadata-based document clustering → NetworkX undirected graph with Louvain communities and cross-links to code graph
- `type-aware-ingestion`: Content-type-aware chunking dispatch (CodeSplitter for code, skip binaries, content_type metadata in ChromaDB)
- `azure-document-backend`: Optional Azure Document Intelligence integration for hybrid deployment mode (structured table/layout extraction with automatic LiteParse fallback)

### Modified Capabilities
- `async-ingestion`: Ingestion pipeline gains type-aware dispatch branch (Magika detection → chunking strategy selection) and optional Azure/LiteParse branching for document files
- `pdf-reader`: Reader factory extended with Azure Document Intelligence as an optional upstream backend (DOCUMENT_BACKEND=azure bypasses LiteParse chain; falls back to existing chain on failure)

## Impact

- **New files**: `codebase_map.py`, `code_graph.py`, `doc_graph.py`, `azure_reader.py`, `.opencode/plugins/fast-context.ts`
- **Modified files**: `ingestion.py` (type-aware dispatch), `config.py` (new constants), `server.py` (new MCP tool)
- **Unchanged files**: `retrieval.py`, `metadata_extractor.py`, `chroma_utils.py`, `reranker.py`
- **New dependencies (both modes)**: `tree-sitter`, `tree-sitter-language-pack`, `networkx`, `magika` (system CLI via `brew install`)
- **New dependency (hybrid only)**: `azure-ai-documentintelligence` (optional extra)
- **Architecture invariants preserved**: No PyTorch, no cloud for embeddings/search, async ingestion, `config.py` remains single source of truth
- **Hard boundary exception**: `DOCUMENT_BACKEND=azure` introduces an optional cloud dependency for document parsing only — gated behind explicit config, never on by default, automatic fallback to local
