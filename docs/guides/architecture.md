# Architecture Decisions

This is a living document. It explains the "why" behind how this project is built — in plain English, for anyone who wants to understand the thinking, not just the code. Each section links to the full ADR for the details.

The one principle that shapes every decision here: **everything runs on your machine**. No cloud, no API keys, no recurring costs. Every technology choice either supports that or gets rejected.

---

## The technology stack

### Why LlamaIndex? ([ADR-002](../adr/002-adopt-llamaindex-for-rag-pipeline.md))

Reading a PDF, a Word document, a PowerPoint, and a CSV file all require completely different parsing logic. LlamaIndex handles all of that out of the box. Rather than building our own document readers for seven file formats, we use LlamaIndex's `SimpleDirectoryReader` and focus on the parts that are specific to this project. The trade-off is a large dependency tree, but the alternative — writing our own parsers — would have taken weeks and been worse.

### Why ChromaDB? ([ADR-003](../adr/003-use-chromadb-as-vector-store.md))

When you search for documents, the server compares your query against thousands of stored text chunks using vector similarity. Those vectors need to be stored somewhere. ChromaDB stores them in a folder on your disk — no server process, no configuration, no network. It just works. The main limitation is that it locks the vector dimension when you first create a collection, so switching embedding models requires deleting the store and re-indexing. That's a known trade-off, documented in the [Ingestion Guide](../guides/ingestion.md).

### Why MCP? ([ADR-004](../adr/004-adopt-mcp-protocol-for-server-interface.md))

The Model Context Protocol is the standard way AI assistants call external tools. By implementing MCP, this server works with Claude, GPT, Cursor, Windsurf, and any other MCP-compatible client without any custom integration code. The server runs as a subprocess and communicates over stdin/stdout — no open ports, no firewall rules, no web server to manage.

### Why uv? ([ADR-001](../adr/001-use-uv-as-package-manager.md))

uv is a Python package manager written in Rust. It's dramatically faster than pip or poetry, produces a lockfile for reproducible installs, and handles virtual environments automatically. `uv sync` installs everything; `uv run rag-mcp` runs the server. One tool, no ceremony.

### Why config.py? ([ADR-006](../adr/006-config-as-single-source-of-truth.md))

Early on, both the ingestion module and the retrieval module each set up the embedding model independently. When one was updated and the other wasn't, they'd silently use different settings. `config.py` was created as the single place where all configuration lives. Every other module imports from it. Nothing sets `Settings.embed_model` except `config.py`. This sounds obvious in hindsight, but it took a real bug to make it a rule.

---

## The search pipeline

### Why qwen3-embedding:0.6b? ([ADR-009](../adr/009-switch-to-qwen3-embedding-0-6b.md))

We ran experiments comparing three embedding models. The results were clear:

- `qwen3-embedding:8b` — perfect retrieval quality, but ingesting a 57-PDF Zotero library takes 3 hours. Unusable.
- `nomic-embed-text` — fastest (15 chunks/sec), but missed 1 in 17 test queries (94.1% accuracy).
- `qwen3-embedding:0.6b` — perfect retrieval quality (100% accuracy), ingests the same library in 13 minutes.

The 0.6b model is 13× faster than the 8b model with identical retrieval quality. It's also better than nomic on accuracy. The choice was straightforward. The benchmark data is in [`experiments/embedding-performance.md`](../../experiments/embedding-performance.md).

### Why a cross-encoder reranker? ([ADR-005](../adr/005-cross-encoder-reranker-with-onnx-runtime.md))

Vector similarity search is fast but imprecise. It finds chunks that are _similar_ to your query, but "similar" in vector space doesn't always mean "relevant" in human terms. A cross-encoder reranker reads each (query, chunk) pair together and scores them more accurately — the same way a human would judge relevance.

The challenge: most reranker implementations require PyTorch, a ~2 GB dependency. We use a pre-exported ONNX model (~23 MB) that runs via ONNX Runtime instead. No PyTorch, no GPU required. The reranker is optional and off by default — it adds ~90ms per query but improves accuracy from 87.5% to 100% in our experiments.

---

## Features added over time

### CLI and ingestion controls ([ADR-007](../adr/007-cli-and-parallel-ingestion.md))

The original server only worked through an MCP client. To test it, you needed the MCP Inspector. To ingest documents, you needed an AI assistant. That was inconvenient, so we added a CLI: `rag-mcp ingest`, `rag-mcp search`, `rag-mcp list`. The same binary, no arguments = MCP server; with subcommands = CLI tool.

Directory ingestion currently reads files sequentially and keeps ChromaDB writes serial behind a lock. Throughput tuning is focused on embedding work: `EMBED_BATCH_SIZE` controls Ollama batch size and `EMBED_CONCURRENCY` controls concurrent embedding API calls.

### Ingestion reports ([ADR-008](../adr/008-cli-folder-embed-progress.md))

When you ingest a large directory, you want to know what happened: which files succeeded, which failed, how many chunks were created. The `--report` flag writes a structured summary to a file. Use `.json` for machine-readable output (useful in CI), or any other extension for a Markdown table. The format is inferred from the file extension — no extra flags needed.

### File watcher ([ADR-010](../adr/010-file-watcher-auto-ingestion.md))

`rag-mcp watch <dir>` monitors a directory and automatically ingests new or changed files as they appear. This is particularly useful for Zotero users — new papers are indexed as soon as Zotero downloads them, with no manual step.

The watcher uses SHA-256 content hashing to skip files that haven't actually changed (even if their modification timestamp has). It debounces rapid writes (e.g. a file being downloaded in chunks) and limits concurrent ingestions to avoid overwhelming Ollama. If Ollama becomes unreachable, it logs a warning after 5 consecutive failures rather than silently failing.

One important constraint: don't run `rag-mcp watch` and `rag-mcp ingest` simultaneously on the same ChromaDB. Two processes don't share the write lock.

### Multi-collection support and metadata extraction ([ADR-011](../adr/011-multi-collection-and-metadata-extraction.md))

Originally, everything went into one collection called `documents`. Research papers, work notes, and code documentation all mixed together. Multi-collection support lets you route content into named silos — `research`, `work`, `python` — and search each one independently.

Metadata extraction was added at the same time. During ingestion, each document is automatically categorised (AI, Biology, Philosophy, etc.) and that category is stored alongside the vectors. You can then filter searches by category: `metadata_filter={"category": "AI"}` returns only AI-related chunks. The default mode uses regex pattern matching — instant, zero dependencies. An Ollama-powered mode is available for richer classification.

### Document deletion ([ADR-012](../adr/012-document-deletion.md))

The server was originally append-only. Re-ingesting a file created duplicate chunks. There was no way to remove stale documents. ADR-012 added deletion and changed re-ingestion to upsert semantics: when you ingest a file that's already indexed, the old chunks are removed first. The file watcher also cleans up vectors when a watched file is deleted from disk.

Deletion works three ways: by file path, by metadata filter, or by dropping an entire collection. Collection drops require confirmation (or `--yes` to skip it).

### Hybrid category taxonomy ([ADR-013](../adr/013-hybrid-category-taxonomy-for-ollama-metadata.md))

The Ollama metadata extraction mode originally used a fixed list of five categories. Documents outside those categories were permanently labelled "uncategorised". The opposite extreme — letting the LLM invent any label — caused fragmentation: the same domain would get labelled "Machine Learning", "ML", "machine_learning", and "Deep Learning" across different documents. ChromaDB uses exact string matching, so `metadata_filter={"category": "ai"}` would miss all of those.

The solution: before classifying each document, query ChromaDB for all categories already in use, merge them with the five seed categories, and tell the LLM to prefer existing labels. New categories are allowed but only when nothing existing fits. All labels are normalised to lowercase with underscores. The taxonomy grows organically and stays consistent. This pattern is inspired by Microsoft's TnT-LLM paper (KDD 2024).

### Async ingestion path ([ADR-014](../adr/014-async-ingestion-path.md))

The MCP server runs an async event loop. When ingestion was synchronous, a long ingest (a large PDF, or Ollama-based metadata extraction) would block the entire server — search queries would queue up and wait. Making the ingest path async means the server stays responsive to search, list, and delete calls while ingestion runs in the background. ChromaDB's sync API is wrapped in `asyncio.to_thread()` to yield the loop during database writes.

---

## What we deliberately didn't do

A few constraints that shaped the design:

- **No PyTorch at runtime.** The reranker uses ONNX Runtime instead. PyTorch is ~2 GB; the ONNX model is ~23 MB.
- **No cloud services or API keys.** Every component — embeddings, classification, reranking, storage — runs locally via Ollama and ChromaDB. (Exception: optional Azure Document Intelligence backend — see [ADR-024](../adr/024-dual-deployment-modes.md).)
- **No breaking changes.** Every new feature (collections, metadata, deletion, the watcher) was added with backward-compatible defaults. `rag-mcp ingest ./docs` still works exactly as it did on day one.
- **No new Python dependencies in default mode.** The keyword metadata extraction mode uses only Python's standard library (`re`, `json`). The Ollama mode uses `urllib` (also stdlib). New dependencies are only added when there's no reasonable alternative.

---

## Codebase map (ADR-022, ADR-023, ADR-024)

The `get_codebase_map` MCP tool generates a compact, pre-computed map of a project's file types, code communities, document communities, cross-links, and architectural hubs. It is designed for agents starting a session on an unfamiliar codebase.

### Data flow

1. **Magika file-type detection** (`codebase_map.py`): Scans the project directory using the Magika CLI (with suffix-based fallback) to produce a file inventory with group/label classification.

2. **Code graph** (`code_graph.py`): Extracts AST relationships (imports, classes, inheritance) via tree-sitter, builds a NetworkX DiGraph, and detects Louvain communities, hubs (high in-degree), and bridges (high betweenness).

3. **Document graph** (`doc_graph.py`): Builds an undirected graph from ChromaDB embeddings (cosine similarity edges), metadata (category/keyword edges), and heading hierarchy. Detects document communities and cross-links to code communities.

4. **Graph assembly** (`codebase_map.py`): Orchestrates all components, formats the result as compact text (≤800 tokens), and caches per-project keyed by git commit hash.

5. **Type-aware ingestion** (`ingestion.py`): Uses Magika content-type detection to dispatch chunking — `CodeSplitter` for code, whole-file for config, existing chain for documents. Binary files are skipped.

6. **Azure Document Intelligence** (`azure_reader.py`, optional): When `DOCUMENT_BACKEND=azure`, PDF/DOCX files are parsed by Azure with structured table extraction and heading hierarchy. Falls back to local chain on any error.

### New modules

| Module            | Responsibility                                                          |
| ----------------- | ----------------------------------------------------------------------- |
| `codebase_map.py` | Magika detection, graph assembly, formatting, caching                   |
| `code_graph.py`   | Tree-sitter AST extraction, code graph, communities, hubs               |
| `doc_graph.py`    | Embedding similarity, metadata edges, document communities, cross-links |
| `azure_reader.py` | Azure Document Intelligence reader with fallback                        |

---

_Each section above links to the full ADR for the complete context, alternatives considered, and consequences. The ADRs are the authoritative record; this document is the readable summary._
