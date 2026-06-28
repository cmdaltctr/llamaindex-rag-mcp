## Context

The RAG MCP (v1.7.0) ingests documents and provides semantic retrieval, but agents entering a new codebase burn 5–20 tool calls on exploratory `list_directory`/`glob`/`read_file` before doing useful work. The project needs a pre-computed codebase map (file types, code structure, document clusters) that agents receive at session start — eliminating discovery overhead.

The existing codebase provides:
- Async ingestion pipeline (`ingest_path_async`) with heading-aware markdown chunking
- ChromaDB PersistentClient for vector storage (qwen3-embedding:0.6b, 1024-dim)
- Pluggable PDF reader factory (LiteParse → pypdfium2 → pypdf fallback chain, ADR-020)
- Metadata extraction with normalised categories and keywords (ADR-013)
- `config.py` as single source of truth for all settings

This change adds a **code graph** (tree-sitter AST → NetworkX), a **document graph** (embedding similarity + metadata → NetworkX), **Magika file-type detection**, and an optional **Azure Document Intelligence** backend for hybrid deployment.

### Current Architecture Constraints (from AGENTS.md)

- `config.py` is the single source of truth — all new constants go there
- No cross-imports between `ingestion.py` and `retrieval.py`
- `server.py` and `cli.py` are thin wrappers — logic lives in dedicated modules
- No PyTorch at runtime (ONNX Runtime only)
- No hardcoded paths or secrets — everything via `.env`
- Never raise from MCP tool handlers — return error dicts

## Goals / Non-Goals

**Goals:**

- G1: Provide a `get_codebase_map` MCP tool that returns a compact (~500–800 token) codebase map including file types, code communities, document communities, cross-links, and hubs
- G2: Use deterministic, zero-LLM-cost methods for graph construction (tree-sitter for code, cosine similarity for documents)
- G3: Support both Full Local (default, zero-cost, offline) and Hybrid (Azure Doc Intelligence for document parsing) deployment modes
- G4: Integrate Magika for content-type detection with graceful fallback to extension-based detection
- G5: Add type-aware ingestion dispatch (CodeSplitter for code, skip binaries, content_type metadata)
- G6: Cache the codebase map per-project, invalidated by git commit hash
- G7: Provide a thin OpenCode plugin that injects the map into agent system prompts at session start

**Non-Goals:**

- NG1: LLM-based entity extraction at index time (deferred to future on-demand tool)
- NG2: GraphRAG / LightRAG / KnowledgeGraphIndex (out of scope for initial implementation)
- NG3: Retrieval-side consumption of tree-sitter data (code search remains embedding-based)
- NG4: Real-time incremental graph updates during watcher events (full rebuild on cache miss)
- NG5: Monorepo-aware community detection (single-workspace scope)
- NG6: Cross-codebase knowledge sharing between separate MCP instances

## Decisions

### D1: Two-strategy graph — tree-sitter for code, embedding similarity for documents

**Decision**: Use AST extraction (tree-sitter) for code files and embedding cosine similarity + metadata categories for documents. Neither uses an LLM at index time.

**Rationale**: Code has explicit, parseable relationships (imports, calls, inheritance) that tree-sitter extracts deterministically. Documents have only implicit relationships (topical similarity) that existing embeddings already capture. Both strategies are free, fast, and reproducible.

**Alternatives considered**:
- *LLM-based entity extraction for both*: Expensive (~500 LLM calls for 500 chunks), slow, JSON instability risk. Violates zero-cost indexing goal.
- *Embedding similarity for both*: Loses the exact code relationships (imports aren't "similar" — they're structural). Would produce vague code communities.
- *tree-sitter for both*: Documents have no AST. Not applicable.

### D2: NetworkX with built-in Louvain over graspologic Leiden

**Decision**: Use `networkx.algorithms.community.louvain_communities()` for community detection.

**Rationale**: graspologic adds heavy scipy/scikit-learn transitive dependencies (~200 MB). For codebase-scale graphs (typically <1000 nodes), Louvain is sufficient and keeps the dependency footprint light. NetworkX is pure Python with no native compilation issues.

**Alternatives considered**:
- *graspologic Leiden*: Better theoretical resolution limit, but the codebase graphs here are small enough that Louvain and Leiden produce near-identical communities. The dependency cost is not justified.
- *igraph*: Fast C implementation but adds a native dependency that complicates cross-platform builds.

### D3: Magika as CLI subprocess, not Python package

**Decision**: Shell out to `magika` CLI binary (`brew install magika`) rather than importing the Python package.

**Rationale**: The Magika CLI is faster (optimised binary), avoids Python dependency conflicts (Magika's Python package has TensorFlow dependencies in some versions), and is available via Homebrew bottle. The system degrades gracefully if the binary is missing — falling back to extension-based detection.

**Alternatives considered**:
- *python-magic / libmagic*: Less accurate than Magika for code detection, requires native library installation.
- *Magika Python package*: Risk of heavy transitive deps (TensorFlow in some builds). The CLI avoids this entirely.
- *Extension-only detection*: Too unreliable — a `.txt` file might be JavaScript, a `.py` file might be a shell script.

### D4: Per-project cache keyed by git commit hash

**Decision**: Cache the codebase map at `<project>/.opencode/codebase-graph.json` and `<project>/.opencode/magika-inventory.json`, keyed by `git rev-parse HEAD`.

**Rationale**: Simple, deterministic invalidation. When files change, they get committed, which changes the hash. The cache directory (`.opencode/`) is already used by the OpenCode toolchain and is gitignored by convention.

**Alternatives considered**:
- *File mtime tracking*: Complex, error-prone with git operations (checkout changes mtimes), and doesn't handle deleted files.
- *Watchdog-based invalidation*: Adds coupling to the watcher module. The graph is not performance-critical enough to warrant real-time updates.
- *No caching*: Magika + tree-sitter scan takes <5 seconds for 500 files. Acceptable for fresh builds but wasteful for repeated sessions.

### D5: Thin OpenCode plugin — all logic in RAG MCP

**Decision**: The OpenCode plugin (`fast-context.ts`) does nothing except call `get_codebase_map` via MCP and inject the result into `experimental.chat.system.transform`. All graph computation lives in the RAG MCP Python code.

**Rationale**: Keeps the plugin trivial to maintain. If the plugin interface changes (experimental API), agents can call `get_codebase_map` directly. No duplicate logic across TypeScript and Python.

### D6: Azure Document Intelligence as optional document backend

**Decision**: Support `DOCUMENT_BACKEND=azure` as an optional mode for document parsing. Azure extracts structured JSON (tables, fields, layout) that LiteParse cannot. Gated behind explicit config with automatic fallback.

**Rationale**: Complex PDFs with tables/figures benefit from Azure's layout analysis. The user already has Azure Doc Intelligence proven in the receipt-scanner project. Embedding, code graph, document similarity graph, and search remain fully local in both modes — only the document parsing step goes to the cloud.

**Alternatives considered**:
- *Always local*: Insufficient for complex PDFs with tables. Would leave structured content as flattened text.
- *Always Azure*: Violates offline/privacy requirements. Not all projects can send data to the cloud.
- *Other cloud services*: AWS Textract, Google Document AI — the user has existing Azure infrastructure and SDK experience from receipt-scanner.

### D7: New modules follow existing architecture invariants

**Decision**: New files (`codebase_map.py`, `code_graph.py`, `doc_graph.py`, `azure_reader.py`) follow the same patterns as existing modules:
- All settings read from `config.py`
- No cross-imports between graph modules and retrieval
- `server.py` calls graph modules via thin wrapper
- Type annotations + `from __future__ import annotations` in all new modules
- Google-style docstrings on all public functions

### D8: CodeSplitter for code files, skip binaries

**Decision**: During ingestion, Magika-detected code files use LlamaIndex's `CodeSplitter` (which respects tree-sitter function boundaries), and binary files (executables, images, archives) are skipped entirely.

**Rationale**: Generic `SentenceSplitter` produces poor chunks for code — it splits mid-function. `CodeSplitter` uses tree-sitter to split at function/class boundaries, producing semantically coherent chunks. Binary files are not meaningful for text search and waste ChromaDB space.

**Alternatives considered**:
- *Continue using SentenceSplitter for code*: Produces incoherent chunks that split mid-function. Degrades retrieval quality.
- *No binary skip*: Attempting to embed binary content produces garbage embeddings and wastes storage.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|------|----------|------------|
| Magika CLI not installed | 🟡 Medium | Graceful degradation to `Path.suffix`-based detection. Log warning. All downstream code works with either detection method. |
| tree-sitter grammar missing for a language | 🟢 Low | `tree-sitter-language-pack` covers 50+ languages. Unknown languages fall back to `SentenceSplitter`. |
| Document similarity threshold too high/low | 🟡 Medium | Expose `DOC_SIMILARITY_THRESHOLD` in config (default 0.85). Experiment in Phase 3 to calibrate. |
| System prompt bloat from codebase map | 🟡 Medium | Hard cap at ~800 tokens. Use counts + glob patterns, not full file lists. Truncate communities by size. |
| `experimental.chat.system.transform` API changes | 🟢 Low | Plugin is <20 lines. Agents can call `get_codebase_map` directly as fallback. |
| Azure Document Intelligence unavailable (hybrid mode) | 🟡 Medium | Automatic fallback to LiteParse → pypdfium2 → pypdf chain. Logged as warning, not error. |
| Azure cost accumulation | 🟢 Low | Incremental indexing (changed files only). Free tier: 500 pages/month. Per-project config flag. |
| NetworkX memory for large graphs | 🟢 Low | Codebase graphs are typically <1000 nodes. NetworkX handles 10K+ nodes in <1 second. |
| Cross-link false positives (filename matching) | 🟡 Medium | Require minimum 2 path segments for matching (not just "config"). Validate in Phase 3. |
| New dependencies increase install size | 🟢 Low | tree-sitter + networkx are lightweight. Azure SDK is optional (not in base install). |

## Migration Plan

No migration needed for existing data. This change is additive:

1. **Existing ChromaDB data**: Unchanged. New `content_type` metadata is added only to newly-ingested documents.
2. **Existing ingestion behaviour**: Unchanged for users who don't enable Magika or type-aware chunking. The dispatch falls through to existing SentenceSplitter.
3. **Existing MCP tools**: Unchanged. `get_codebase_map` is a new tool alongside existing ones.
4. **Deployment**: `uv sync` installs new base dependencies (tree-sitter, networkx). Magika requires `brew install magika` (system). Azure SDK only needed with `DOCUMENT_BACKEND=azure`.
5. **Rollback**: Remove new files and revert `config.py` / `server.py` / `ingestion.py` changes. No data migration needed.

## Open Questions

1. **Similarity threshold**: What cosine similarity threshold for document graph edges? Default 0.85 — needs experiment with qwen3-embedding:0.6b output distribution.
2. **tree-sitter relationship depth**: Start with imports + class inheritance only, or include function calls? Start narrow, widen if communities are too fragmented.
3. **Community labelling**: Top filenames + shared keywords (deterministic), or LLM-generated labels (expensive)? Start with deterministic.
4. **Cross-link false positives**: Generic terms ("config", "utils") may over-connect. Require minimum path depth for filename matching.
5. **Monorepo handling**: Single workspace scope for v1. Cross-workspace communities deferred to future change.
6. **Azure table chunking**: Whole table as one chunk vs row groups? Needs experiment with retrieval quality.
