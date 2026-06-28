# Configuration

All configuration lives in a `.env` file at the project root. Copy the example to get started:

```bash
cp .env.example .env
```

Environment variables from your shell override `.env` values, so you can also set them inline for a single run:

```bash
METADATA_EXTRACTION_MODE=disabled uv run rag-mcp ingest /path/to/docs/
```

## Environment variables

| Variable                          | Default                                           | Description                                                                                                      |
| --------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `EMBED_MODEL`                     | _(required; example uses `qwen3-embedding:0.6b`)_ | Ollama embedding model name                                                                                      |
| `OLLAMA_BASE_URL`                 | `http://localhost:11434`                          | Ollama server URL                                                                                                |
| `CHROMA_PERSIST_DIR`              | `./chroma_db`                                     | ChromaDB on-disk storage path                                                                                    |
| `COLLECTION_NAME`                 | `documents`                                       | Default ChromaDB collection name                                                                                 |
| `CHROMA_SCAN_PAGE_SIZE`           | `10000`                                           | Page size for collection metadata scans                                                                          |
| `CHUNK_SIZE`                      | `512`                                             | Text splitter chunk size (characters)                                                                            |
| `CHUNK_OVERLAP`                   | `100`                                             | Chunk overlap (characters)                                                                                       |
| `EMBED_BATCH_SIZE`                | `100`                                             | Embedding batch size per Ollama API call                                                                         |
| `EMBED_CONCURRENCY`               | `2`                                               | Max concurrent Ollama embedding requests                                                                         |
| `MARKDOWN_CHUNK_SIZE`             | `1024`                                            | Markdown-only chunk size                                                                                         |
| `MARKDOWN_HEADING_PREPEND`        | `false`                                           | Experimental Markdown heading-context prepend                                                                    |
| `MARKDOWN_MIN_CHUNK_FRACTION`     | `0.0`                                             | Experimental Markdown small-chunk floor                                                                          |
| `TOP_K`                           | `10`                                              | Default number of search results                                                                                 |
| `RERANK_MODEL`                    | `cross-encoder/ms-marco-MiniLM-L-6-v2`            | ONNX reranker model ID                                                                                           |
| `RERANK_ENABLED`                  | `true`                                            | Default rerank behaviour                                                                                         |
| `RERANK_FETCH_MULTIPLIER`         | `10`                                              | Candidate-pool multiplier when reranking                                                                         |
| `RERANK_MAX_FETCH`                | `50`                                              | Candidate-pool floor when reranking                                                                              |
| `SIMILARITY_THRESHOLD`            | `0.0`                                             | Minimum score to include a result                                                                                |
| `HYBRID_ENABLED`                  | `false`                                           | Default hybrid retrieval behaviour for callers using config defaults                                             |
| `HYBRID_RRF_K`                    | `60`                                              | Reciprocal Rank Fusion constant                                                                                  |
| `HYBRID_SPARSE_BACKEND`           | `bm25`                                            | Sparse backend: `bm25`, `auto`, or `native`. V1 default stays `bm25`; promoting to `auto` is a follow-up change. |
| `METADATA_EXTRACTION_MODE`        | `keyword`                                         | Metadata extraction mode: `disabled`, `keyword`, `ollama`, or `llamaindex`                                       |
| `METADATA_KEYWORD_RULES`          | _(built-in)_                                      | Optional JSON string of `[{"pattern": "regex", "category": "name"}, ...]` overriding default keyword rules       |
| `OLLAMA_CLASSIFY_MODEL`           | `qwen3:0.6b`                                      | Chat model for Ollama-based classification (only when `METADATA_EXTRACTION_MODE=ollama`)                         |
| `OLLAMA_CLASSIFY_MAX_ATTEMPTS`    | `3`                                               | Bounded retry attempts for Ollama metadata extraction                                                            |
| `OLLAMA_CLASSIFY_TIMEOUT`         | `30.0`                                            | Per-attempt timeout for Ollama metadata extraction                                                               |
| `MAGIKA_BINARY`                   | `magika`                                          | Path to Magika CLI binary for file-type detection. Falls back to suffix detection if not found.                  |
| `DOC_SIMILARITY_THRESHOLD`        | `0.85`                                            | Cosine similarity threshold for document graph edges                                                             |
| `CODEBASE_MAP_CACHE_DIR`          | `.opencode`                                       | Per-project cache directory for codebase map (keyed by git commit)                                               |
| `DOCUMENT_BACKEND`                | `local`                                           | Document parsing backend: `local` (default) or `azure`                                                           |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | _(empty)_                                         | Azure Document Intelligence endpoint URL (only when `DOCUMENT_BACKEND=azure`)                                    |
| `AZURE_DOC_INTELLIGENCE_KEY`      | _(empty)_                                         | Azure Document Intelligence API key (only when `DOCUMENT_BACKEND=azure`)                                         |
| `AZURE_DOC_INTELLIGENCE_MODEL`    | `prebuilt-layout`                                 | Azure Document Intelligence model ID                                                                             |

## Architecture note

All configuration is centralised in `src/rag_mcp/config.py` — the single source of truth for `Settings.embed_model` and all constants. Never set `Settings.embed_model` directly in `ingestion.py`, `retrieval.py`, or `server.py`.
