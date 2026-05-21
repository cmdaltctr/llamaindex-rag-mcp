# CHANGELOG

<!-- version list -->

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
