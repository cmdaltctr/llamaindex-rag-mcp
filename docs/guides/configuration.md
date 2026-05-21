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

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB on-disk storage path |
| `COLLECTION_NAME` | `documents` | Default ChromaDB collection name |
| `CHUNK_SIZE` | `512` | Text splitter chunk size (characters) |
| `CHUNK_OVERLAP` | `64` | Chunk overlap (characters) |
| `EMBED_BATCH_SIZE` | `100` | Embedding batch size per Ollama API call |
| `INGEST_WORKERS` | `4` | Parallel file readers for directory ingestion |
| `EMBED_CONCURRENCY` | `2` | Max concurrent Ollama embedding requests |
| `TOP_K` | `5` | Default number of search results |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | ONNX reranker model ID |
| `RERANK_ENABLED` | `false` | Default rerank behaviour |
| `SIMILARITY_THRESHOLD` | `0.0` | Minimum score to include a result |
| `METADATA_EXTRACTION_MODE` | `keyword` | Metadata extraction mode: `disabled`, `keyword`, `ollama`, or `llamaindex` |
| `METADATA_KEYWORD_RULES` | *(built-in)* | Optional JSON string of `[{"pattern": "regex", "category": "name"}, ...]` overriding default keyword rules |
| `OLLAMA_CLASSIFY_MODEL` | `qwen3:0.6b` | Chat model for Ollama-based classification (only when `METADATA_EXTRACTION_MODE=ollama`) |

## Architecture note

All configuration is centralised in `src/rag_mcp/config.py` — the single source of truth for `Settings.embed_model` and all constants. Never set `Settings.embed_model` directly in `ingestion.py`, `retrieval.py`, or `server.py`.
