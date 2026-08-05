# CHANGELOG

<!-- version list -->

## v2.0.0 (2026-08-05)

### Bug Fixes

- Address all a-review blocking findings
  ([#16](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/16),
  [`37dcf90`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/37dcf90b5f1a3730639ce95c343df8d2728a8674))

- Address Phase 4 review findings (HIGH + MEDIUM)
  ([#16](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/16),
  [`37dcf90`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/37dcf90b5f1a3730639ce95c343df8d2728a8674))

- Address Phase 4 review findings (HIGH + MEDIUM)
  ([#15](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/15),
  [`239a634`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/239a6345da5c742d911346c585d8a634d980d3a0))

- Resolve all SonarQube code quality issues and security hotspots
  ([#11](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/11),
  [`44d116b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/44d116b7afbb7ce104546e7d00cdecf6602c4ce2))

- **ci**: Remove --no-build flag incompatible with editable installs
  ([#11](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/11),
  [`44d116b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/44d116b7afbb7ce104546e7d00cdecf6602c4ce2))

- **ci**: Set OLLAMA_BASE_URL env var for test collection
  ([#12](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/12),
  [`1a09887`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1a0988735cbd5178d6d8366e6812b260ee99da6b))

- **ci**: Strip ANSI codes in CLI help tests, remove pdf-liteparse matrix
  ([#10](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/10),
  [`cf6734f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/cf6734f40d0807ff42e7e7b85ac74feca7669d58))

- **doc-graph**: Use explicit len check for empty embeddings list
  ([`75b0925`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/75b092548513e3a571aab342d6baf4a727b8e336))

- **reranker**: Disable CoreML provider, fix silent inference failure
  ([#12](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/12),
  [`1a09887`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1a0988735cbd5178d6d8366e6812b260ee99da6b))

- **sonar**: Make _detect_native_sparse_capability runtime-dynamic
  ([#12](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/12),
  [`1a09887`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1a0988735cbd5178d6d8366e6812b260ee99da6b))

### Features

- Add profiles system for dual use cases (Phase 4)
  ([#16](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/16),
  [`37dcf90`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/37dcf90b5f1a3730639ce95c343df8d2728a8674))

- Add profiles system for dual use cases (Phase 4)
  ([#15](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/15),
  [`239a634`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/239a6345da5c742d911346c585d8a634d980d3a0))

- Codebase map, Azure reader, type-aware ingestion, SonarCloud security gate
  ([#10](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/10),
  [`cf6734f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/cf6734f40d0807ff42e7e7b85ac74feca7669d58))

- Provider registry pattern with OpenRouter cloud provider
  ([`8703165`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/870316500ae0f8bbf5df18383f4f61d806d34498))

- **azure**: Add Azure Document Intelligence reader and type-aware ingestion
  ([#10](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/10),
  [`cf6734f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/cf6734f40d0807ff42e7e7b85ac74feca7669d58))

- **codebase-map**: Add fast-context codebase map with boundary validation and graph fixes
  ([#10](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/10),
  [`cf6734f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/cf6734f40d0807ff42e7e7b85ac74feca7669d58))

- **experiments**: Add Jupytext analysis workflow for experiment evaluation
  ([`816da98`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/816da98a8884abb300bcc50f62d439f9cb399e52))

- **reranker**: Swap default model to Alibaba-NLP/gte-reranker-modernbert-base
  ([`8f4fed2`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/8f4fed2ddd07ab2d126cec3c53a57b03296db323))

- **retrieval**: Add fetch_k override for experiment pool sweeps
  ([`49b7bc8`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/49b7bc8ab91492cce51bd443e30927b461236897))

### Refactoring

- Architecture-v2 conformance (v2.0.0)
  ([#19](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/19),
  [`1b68d33`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/1b68d33188afdc14eadf5a3b0a044eb62ce3865b))

### Breaking Changes

- Subpackage environment variables are renamed to a nested schema (TOP_K -> RETRIEVAL__TOP_K,
  CHUNK_SIZE -> CHUNKING__CHUNK_SIZE, EMBED_CONCURRENCY -> INGESTION__EMBED_CONCURRENCY, and so on).
  Startup fails naming the replacement rather than silently ignoring an old name. The v1 import
  paths (rag_mcp.server, rag_mcp.cli, rag_mcp.ingestion, rag_mcp.readers and the rest) are removed.
  Custom profile YAML must be converted to nested blocks. ChromaDB collections, CLI commands and MCP
  tool signatures are unchanged; rollback is code-only. Migration table in
  docs/adr/037-architecture-v2-conformance.md.


## v1.8.0 (2026-06-23)

### Features

- Make liteparse a core dependency
  ([`7eec00e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/7eec00e918f875b48399689a84c842391e1b0ec4))


## v1.7.0 (2026-06-23)

### Features

- Flip PDF_READER default to auto (LiteParse when installed)
  ([`4fbff75`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/4fbff755473730d49cd4cec472563ce32929ad81))


## v1.6.0 (2026-06-23)

### Bug Fixes

- **exp11**: _parent_id reads dict source, not object metadata
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))

- **exp11**: JSON-encode section_bbox for ChromaDB compatibility
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))

### Features

- Add pluggable PDF reader factory with LiteParse adapter
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))

- Use LiteParse as pluggable PDF reader (gated by Experiment 11)
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))

### Performance Improvements

- **reranker**: 10x speedup via CoreML, batching, shorter sequences
  ([#9](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/9),
  [`96eec6b`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/96eec6b6d82ef8262024eb3c1c8ed014cf1973e9))


## v1.5.3 (2026-06-20)

### Bug Fixes

- **ci**: Fetch full history in release checkout to fix exit 128
  ([`f4d7a9e`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/f4d7a9e32a480f781ea8d802d5b49e7cd155717e))


## v1.5.2 (2026-06-20)

### Bug Fixes

- **graphify**: Remove echo banner injection from plugin
  ([`11b66d4`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/11b66d4c361c6f88c166dcc988163faea367ef75))


## v1.5.1 (2026-06-20)

### Bug Fixes

- **reranker**: Guard version regex against ReDoS on digit-only tokens
  ([#6](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/6),
  [`2e5cde9`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/2e5cde9ff64a10967191fffb6c3b648b9be193bf))


## v1.5.0 (2026-06-20)

### Bug Fixes

- **test**: Update chunk-overlap default test for ADR-019 reranker default-off
  ([#5](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/5),
  [`a0a5def`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a0a5def30cfb3aeee13391012156f706411a6975))

### Features

- **reranker**: Disable reranker by default after Experiment 10
  ([#5](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/5),
  [`a0a5def`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a0a5def30cfb3aeee13391012156f706411a6975))

- **reranker**: Implement semantic/technical reranker policy resolver
  ([#5](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/5),
  [`a0a5def`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/a0a5def30cfb3aeee13391012156f706411a6975))


## v1.4.0 (2026-05-31)

### Features

- **hybrid**: Ship opt-in hybrid retrieval and archive follow-up reranker work
  ([`e3a506f`](https://github.com/cmdaltctr/llamaindex-rag-mcp/commit/e3a506f6a6161f557a334d7e42f30a1b74b48006))


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
