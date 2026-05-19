# Architecture Decision Records

This directory records the significant architectural decisions made during the
development of the LlamaIndex RAG MCP Server.

## Index

| ADR | Title | Date | Status |
|-----|-------|------|--------|
| [001](./001-use-uv-as-package-manager.md) | Use uv as Package Manager | 2026-05-11 | Accepted |
| [002](./002-adopt-llamaindex-for-rag-pipeline.md) | Adopt LlamaIndex for RAG Pipeline | 2026-05-11 | Accepted |
| [003](./003-use-chromadb-as-vector-store.md) | Use ChromaDB as Vector Store | 2026-05-11 | Accepted |
| [004](./004-adopt-mcp-protocol-for-server-interface.md) | Adopt MCP Protocol for Server Interface | 2026-05-11 | Accepted |
| [005](./005-cross-encoder-reranker-with-onnx-runtime.md) | Cross-Encoder Reranker with ONNX Runtime | 2026-05-11 | Accepted |
| [006](./006-config-as-single-source-of-truth.md) | Config as Single Source of Truth | 2026-05-12 | Accepted |
| [007](./007-cli-and-parallel-ingestion.md) | CLI Interface and Parallel Ingestion | 2026-05-15 | Accepted |
| [008](./008-cli-folder-embed-progress.md) | CLI Folder Embedding with Progress and Reports | 2026-05-19 | Accepted |
| [009](./009-switch-to-qwen3-embedding-0-6b.md) | Switch to `qwen3-embedding:0.6b` as the Default Embedding Model | 2026-05-19 | Accepted |
| [010](./010-file-watcher-auto-ingestion.md) | File Watcher for Automatic Document Ingestion | 2026-05-19 | Accepted |

## Convention

Each ADR follows the template:

- **Context** — the problem, constraints, and forces at play
- **Decision** — what was chosen and why
- **Consequences** — positive, negative, and neutral outcomes
- **Alternatives Considered** — options that were rejected
- **References** — links to relevant files or documentation

ADRs are immutable once their status is "Accepted". Superseded decisions are
marked with a "Superseded by ADR-00X" note.

## Creating a New ADR

1. Copy the template from any existing ADR
2. Number sequentially (three-digit, zero-padded)
3. Set status to "Proposed" initially
4. Update this index table
