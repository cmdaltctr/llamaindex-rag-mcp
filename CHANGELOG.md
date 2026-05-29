# CHANGELOG

<!-- version list -->

## v1.3.0 (2026-05-29)

### Features

- **retrieval**: Promote balanced defaults
  ([`183734d`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/183734dbf25938e9db3a154e561da22545491f62))


## v1.2.0 (2026-05-29)

### Features

- **ingestion**: Markdown-aware chunking and overlap bump
  ([`0b91d03`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/0b91d036369e2fbac438ac636eff2f98c81f34ae))

- **retrieval**: Improve markdown retrieval quality
  ([`e963046`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/e9630467491d8a3520a7cf736c87be7d27bd7b27))

- **retrieval**: Query embedding cache and configurable rerank pool
  ([`abea2b5`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/abea2b52dbab04003d6a93e80eace0b5c7ea0990))


## v1.1.0 (2026-05-27)

### Bug Fixes

- Offload keyword extraction to thread + large corpus experiment replication
  ([`735ef52`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/735ef52491bd879951ff8ce923ec7980f49f5e58))

### Features

- Expose metadata_filter on MCP search and harden Ollama metadata extraction
  ([`30ccb2d`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/30ccb2d624a9da428d3483a35f4e44cb55f194d5))


## v1.0.0 (2026-05-25)

### Features

- Implement archived OpenSpec maintenance changes
  ([`1be0e73`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1be0e739042f2dd812feaa51a1e4c58cf18eb30c))

### Breaking Changes

- Remove rag-mcp ingest --workers/-w, INGEST_WORKERS, and the workers parameter from
  ingest_path_async(). Use EMBED_CONCURRENCY and EMBED_BATCH_SIZE for ingestion throughput tuning.


## v0.1.1 (2026-05-21)

### Bug Fixes

- **ci**: Disable ANSI colour codes in test runner
  ([`bf2a275`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/bf2a2754e6106b090773cc6eebf67b1330c43980))

- **ci**: Skip build in release action (no uv in Docker container)
  ([`03d6754`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/03d67545536fda8d63c034bc1f080ef8d467225c))


## v0.1.0 (2026-05-21)

### Features

- make ingest path async end-to-end
- add document deletion, multi-collection support, and metadata extraction
- add file watcher for automatic document ingestion
- add per-file tracking, concurrent embedding, reports, and benchmark
- add Typer CLI with ingest, search, list commands and parallel ingestion
- shared config module, threshold scaling, reranker flatten fix
- initial RAG MCP server with testing framework

### Bug Fixes

- correct metadata extraction degradation ladder and strip LLM output noise
- replace real user paths with generic placeholders in README
