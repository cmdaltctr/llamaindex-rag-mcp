# Architecture Decision Records

This directory records the significant architectural decisions made during the
development of the LlamaIndex RAG MCP Server.

## Index

| ADR                                                                | Title                                                                                        | Date       | Status   |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | ---------- | -------- |
| [001](./001-use-uv-as-package-manager.md)                          | Use uv as Package Manager                                                                    | 2026-05-11 | Accepted |
| [002](./002-adopt-llamaindex-for-rag-pipeline.md)                  | Adopt LlamaIndex for RAG Pipeline                                                            | 2026-05-11 | Accepted |
| [003](./003-use-chromadb-as-vector-store.md)                       | Use ChromaDB as Vector Store                                                                 | 2026-05-11 | Superseded for default by ADR-049 |
| [004](./004-adopt-mcp-protocol-for-server-interface.md)            | Adopt MCP Protocol for Server Interface                                                      | 2026-05-11 | Accepted |
| [005](./005-cross-encoder-reranker-with-onnx-runtime.md)           | Cross-Encoder Reranker with ONNX Runtime                                                     | 2026-05-11 | Accepted |
| [006](./006-config-as-single-source-of-truth.md)                   | Config as Single Source of Truth                                                             | 2026-05-12 | Accepted |
| [007](./007-cli-and-parallel-ingestion.md)                         | CLI Interface and Parallel Ingestion                                                         | 2026-05-15 | Accepted |
| [008](./008-cli-folder-embed-progress.md)                          | CLI Folder Embedding with Progress and Reports                                               | 2026-05-19 | Accepted |
| [009](./009-switch-to-qwen3-embedding-0-6b.md)                     | Switch to `qwen3-embedding:0.6b` as the Default Embedding Model                              | 2026-05-19 | Accepted |
| [010](./010-file-watcher-auto-ingestion.md)                        | File Watcher for Automatic Document Ingestion                                                | 2026-05-19 | Accepted |
| [011](./011-multi-collection-and-metadata-extraction.md)           | Multi-Collection Support and Metadata Extraction                                             | 2026-05-19 | Accepted |
| [012](./012-document-deletion.md)                                  | Document Deletion                                                                            | 2026-05-20 | Accepted |
| [013](./013-hybrid-category-taxonomy-for-ollama-metadata.md)       | Hybrid Category Taxonomy for Ollama Metadata Extraction                                      | 2026-05-20 | Proposed |
| [014](./014-async-ingestion-path.md)                               | Async Ingestion Path                                                                         | 2026-05-20 | Accepted |
| [015](./015-rag-reliability-correctness-fixes.md)                  | RAG Reliability and Correctness Fixes                                                        | 2026-05-27 | Accepted |
| [016](./016-rag-retrieval-quality-improvements.md)                 | RAG Retrieval Quality Improvements                                                           | 2026-05-27 | Accepted |
| [017](./017-hybrid-retrieval-rrf.md)                               | Hybrid Retrieval with Reciprocal Rank Fusion                                                 | 2026-05-27 | Proposed |
| [018](./018-balanced-retrieval-defaults.md)                        | Balanced Retrieval Defaults                                                                  | 2026-05-29 | Accepted |
| [019](./019-reranker-disabled-for-technical-workloads.md)          | Disable Reranker for Technical Workloads                                                     | 2026-06-01 | Accepted |
| [020](./020-use-liteparse-as-pdf-reader.md)                        | Adopt LiteParse as Pluggable PDF Reader                                                      | 2026-06-23 | Accepted |
| [021](./021-reranker-inference-optimisation.md)                    | Reranker Inference Optimisation — CoreML, Batching, and Reduced Fetch Pool                   | 2026-06-23 | Accepted |
| [022](./022-code-graph-via-tree-sitter-ast.md)                     | Code Graph via Tree-Sitter AST                                                               | 2026-06-28 | Accepted |
| [023](./023-document-graph-via-embedding-similarity.md)            | Document Graph via Embedding Similarity                                                      | 2026-06-28 | Accepted |
| [024](./024-dual-deployment-modes.md)                              | Dual Deployment Modes — Full Local vs Hybrid                                                 | 2026-01-15 | Accepted |
| [025](./025-pluggable-inference-backend.md)                        | Pluggable Inference Backend — Ollama and llama.cpp                                           | 2026-07-01 | Accepted |
| [026](./026-provider-registry-and-openrouter.md)                   | Provider Registry Pattern and OpenAI-Compatible API Providers                                | 2026-07-15 | Accepted |
| [027](./027-local-cloud-provider-naming.md)                        | Local/Cloud Provider Naming Taxonomy                                                         | 2026-07-16 | Accepted |
| [028](./028-swap-reranker-to-gte-modernbert.md)                    | Swap Default Reranker to gte-reranker-modernbert-base                                        | 2026-07-31 | Rejected |
| [029](./029-disable-coreml-for-reranker-silent-fallback-lesson.md) | Disable CoreML for Reranker — Silent Fallback Lesson                                         | 2026-07-31 | Accepted |
| [030](./030-prefer-int8-onnx-variant-for-modernbert-rerankers.md)  | Prefer int8 Quantised ONNX Variant for ModernBERT Rerankers                                  | 2026-08-03 | Proposed |
| [031](./031-three-layer-config-compose-di.md)                      | Three-Layer Architecture — Config, Compose, DI                                               | 2026-08-04 | Accepted |
| [032](./032-phase-1-refactor-modular-extraction.md)                | Phase 1 Refactor — Modular Core Extraction                                                   | 2026-08-03 | Accepted |
| [033](./033-phase-2-refactor-di-refinement.md)                     | Phase 2 Refactor — DI Refinement (Inject Constructed Objects, Resolve Settings at Call Time) | 2026-08-04 | Accepted |
| [034](./034-phase-3-refactor-vectordb-abstraction.md)              | Phase 3 Refactor — Vector Store Abstraction Interface                                        | 2026-08-04 | Accepted |
| [035](./035-phase-4-refactor-profiles-dual-use-case.md)            | Phase 4 Refactor — Profiles: Dual Use Cases (Documents + Codebase)                           | 2026-08-04 | Accepted |
| [036](./036-phase-5-refactor-transport-separation.md)              | Phase 5 Refactor — Transport Separation (MCP / CLI / API)                                    | 2026-08-04 | Accepted |
| [037](./037-architecture-v2-conformance.md)                        | Architecture v2 Conformance                                                                  | 2026-08-05 | Accepted |
| [038](./038-pluggable-reranker-backend.md)                         | Pluggable Reranker Backend                                                                   | 2026-08-11 | Accepted |
| [039](./039-mcp-2-0-upgrade.md)                                    | MCP Python SDK 2.0 Upgrade                                                                   | 2026-08-12 | Accepted |
| [040](./040-huggingface-hub-1-0-upgrade.md)                        | huggingface-hub 1.0 + transformers 5.0 Upgrade                                               | 2026-08-12 | Accepted |
| [041](./041-onnxruntime-1-28-upgrade.md)                           | onnxruntime 1.28.0 Upgrade                                                                   | 2026-08-12 | Accepted |
| [042](./042-dependency-floor-integrity.md)                         | Dependency Floor Integrity                                                                   | 2026-08-12 | Accepted |
| [043](./043-apple-acceleration-for-the-reranker.md)                | Apple Acceleration for the Reranker                                                          | 2026-08-13 | Accepted |
| [044](./044-pluggable-community-detection.md)                    | Pluggable Community Detection                                                                | 2026-08-14 | Accepted |
| [045](./045-hosted-chroma-cloud-backend.md)                      | Hosted Chroma Cloud Backend for Experiment Storage                                           | 2026-08-15 | Accepted |
| [046](./046-lancedb-vector-store-backend.md)                     | LanceDB as the Second Vector-Store Backend                                                   | 2026-08-17 | Accepted |
| [047](./047-semantic-vector-store-swappability.md)               | Semantic Vector-Store Swappability                                                           | 2026-08-18 | Accepted |
| [048](./048-bounded-failure-safe-ingestion.md)                   | Bounded and Failure-Safe Ingestion                                                           | 2026-08-19 | Accepted |
| [049](./0049-lancedb-default-and-chroma-isolation.md)           | LanceDB Default and Chroma Isolation                                                         | 2026-08-21 | Accepted |
| [050](./050-configure-pdf-inspector-as-default-reader.md)       | Configure pdf-inspector as the Default PDF Reader                                            | 2026-08-24 | Accepted |
| [051](./051-fail-closed-embedding-write-contract.md)          | Fail-Closed Embedding Write Contract                                                         | 2026-08-28 | Proposed |
| [052](./052-stable-source-chunk-lineage.md)                   | Stable Source and Chunk Lineage                                                              | 2026-08-28 | Proposed |

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
