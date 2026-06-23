# Ingestion Guide

## How ingestion works

Each file passes through a four-stage pipeline:

```
Source file (PDF, DOCX, TXT, ...)
      |
      v
[1] Load & parse  -----> Metadata extraction (optional)
      |                      |
      |                      +-- keyword:    regex (instant, no model)
      |                      +-- ollama:     chat model (~2s/file)
      |                      +-- llamaindex: per-chunk pipeline (~5–30s/file)
      |
      v
[2] Split into chunks (SentenceSplitter)
      |  chunk_size = 512 chars (default)
      |  chunk_overlap = 64 chars
      |
      v
[3] Embed each chunk --> Ollama embedding model (EMBED_MODEL)
      |                     Produces a fixed-dimension vector (768, 1024, etc.)
      |
      v
[4] Store in ChromaDB
      |  collection = "documents" (or --collection value)
      |  Each record: vector + text + metadata + file_path
      v
[Done] Collection ready for search
```

Re-ingesting a file is an **upsert** — old chunks are removed before new ones are written. There is no duplication.

## PDF reader configuration

The PDF parser is a pluggable factory controlled by the `PDF_READER`
environment variable. Accepted values:

| Value        | Description                                              | Extra required          |
| ------------ | -------------------------------------------------------- | ----------------------- |
| `pypdf`      | Default. Always available via `llama-index-readers-file`. | None                    |
| `liteparse`  | Column-aware reading order + bounding-box metadata.       | `[pdf-liteparse]`       |
| `pypdfium2`  | Same PDFium engine as LiteParse, no bbox. Fallback tier.  | `[pdf-pypdfium2]`       |
| `auto`       | Probes in order: liteparse → pypdfium2 → pypdf.            | Depends on what's installed |

The default is `pypdf` (not `auto`) until a follow-on change promotes it.
To use LiteParse:

```bash
uv sync --extra pdf-liteparse
# In .env: PDF_READER=liteparse
```

LiteParse captures bounding-box metadata (`page`, `column`,
`section_bbox`, `bbox_schema_version`) on every emitted Document for
future spatial RAG capabilities. OCR is disabled by default
(`LITEPARSE_OCR_ENABLED=false`) — enable it only for scanned PDFs.

See [ADR-020](../adr/020-use-liteparse-as-pdf-reader.md) for the adoption
rationale and Experiment 11 results.

## Supported file formats

`.pdf` `.docx` `.pptx` `.txt` `.md` `.html` `.csv`

For directories, the server recursively finds all supported files.

## Embedding models

Set `EMBED_MODEL` in `.env` to any Ollama embedding model:

| Model | Params | Dims | Context | MTEB | Pull command | Notes |
|-------|--------|------|---------|------|-------------|-------|
| **qwen3-embedding:0.6b** | ~600M | 1,024 | 32,768 | — | `ollama pull qwen3-embedding:0.6b` | **Default** — 100% Hit@1 in experiments, practical ingest times |
| nomic-embed-text | 137M | 768 | 8,192 | 62.4 | `ollama pull nomic-embed-text` | Fastest query latency (~36ms), but lower retrieval quality (94.1% Hit@1) |
| mxbai-embed-large | 334M | 1,024 | 512 | 64.7 | `ollama pull mxbai-embed-large` | Highest MTEB score for short chunks |
| all-minilm | 23M | 384 | 256 | ~58 | `ollama pull all-minilm` | Blazing fast, tiny footprint |

See [ADR-009](../adr/009-switch-to-qwen3-embedding-0-6b.md) for the full evidence behind the default model choice.

### How long will ingestion take?

Practical timings on Apple Silicon (M-series) with `qwen3-embedding:0.6b`, default settings (`EMBED_CONCURRENCY=2`, `EMBED_BATCH_SIZE=100`, `CHUNK_SIZE=512`):

| Scenario | Time |
|----------|------|
| 1 PDF (~117 chunks) | ~14 seconds |
| 5 PDFs (~585 chunks) | ~70 seconds |
| 20 PDFs (~2,340 chunks) | ~5 minutes |
| Full Zotero library (57 PDFs, ~6,600 chunks) | ~13 minutes |

For comparison, the larger `qwen3-embedding:8b` model (4,096-dim vectors) takes ~3 hours for the same Zotero library — the 0.6b model is **13× faster** with identical retrieval quality in our tests.

> **Apple Silicon note:** Ollama serialises `/api/embed` requests internally on Apple Silicon, so `EMBED_CONCURRENCY > 2` yields diminishing returns. Setting it to 2 overlaps network round-trips with embedding computation; beyond that, requests queue up in Ollama's internal pipeline.

File reading is sequential. Tune throughput with `EMBED_BATCH_SIZE` and `EMBED_CONCURRENCY` rather than file-reader worker settings.

Raw benchmark data: [`experiments/embedding-performance.md`](../../experiments/embedding-performance.md).

### Switching models

```bash
# 1. Pull the new model
ollama pull mxbai-embed-large

# 2. Update .env
EMBED_MODEL=mxbai-embed-large

# 3. Delete the old vector store (dimensions differ between models)
rm -rf chroma_db

# 4. Re-index your documents
rag-mcp ingest /path/to/docs/
```

> **Why delete chroma_db?** ChromaDB locks the vector dimension at collection creation time. Each model produces a different dimension (nomic=768, mxbai=1024, minilm=384). Switching models requires starting fresh.

## Chunk size guide

`--chunk-size` controls how many **characters** go into each chunk. The embedding model has a **context length** in **tokens**. A rough guide: ~4 characters ≈ 1 token for English.

| Model | Context (tokens) | Max safe chunk-size | Default 512 safe? |
|-------|-----------------|---------------------|-------------------|
| qwen3-embedding:0.6b | 32,768 | ~130,000 chars | Yes |
| nomic-embed-text | 8,192 | ~32,000 chars | Yes |
| mxbai-embed-large | 512 | ~1,500 chars | Yes |
| all-minilm | 256 | ~1,000 chars | Yes |

The default 512-character chunk size is safe for all models. For models with large context windows:

```bash
# 2048-char chunks are fine (2048 × 0.25 = 512 tokens)
rag-mcp ingest /path/to/docs/ --chunk-size 2048
```

## Progress and interruption

Progress bars appear automatically in TTY terminals (Rich). In non-TTY contexts (pipes, CI) plain text is emitted to stderr. Press Ctrl+C once for graceful shutdown (finishes the current file, skips the rest). Press again to force quit.

## Which model runs when

| Stage | Model type | What it does | Speed impact |
|-------|-----------|-------------|-------------|
| Metadata extraction (ollama mode) | Chat/LLM (e.g. qwen3:0.6b) | Classifies document category | ~2s per file |
| Metadata extraction (keyword mode) | None (regex) | Pattern matching | Instant |
| Embedding | Embedding model (e.g. qwen3-embedding:0.6b) | Converts text to vectors | ~50–500ms per chunk |
| Search (rerank) | Cross-encoder (ms-marco-MiniLM-L-6-v2) | Re-scores top results | ~10–50ms per query pair |

The embedding model and chat/classification model are **separate** — each pulled independently via Ollama.
