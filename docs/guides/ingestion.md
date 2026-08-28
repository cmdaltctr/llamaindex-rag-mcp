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
      |                      +-- local:      chat model via METADATA_LLM_PROVIDER (~2s/file)
      |                      +-- llamaindex: per-chunk pipeline (~5–30s/file)
      |
      v
[2] Split into chunks (SentenceSplitter)
      |  chunk_size = 512 chars (default)
      |  chunk_overlap = 100 chars
      |
      v
[3] Embed each chunk --> Ollama embedding model (EMBED_MODEL)
      |                     Produces a fixed-dimension vector (768, 1024, etc.)
      |
      v
[4] Store in the selected vector store
      |  LanceDB is the base-install default
      |  collection = "documents" (or --collection value)
      |  Each record: vector + text + metadata + file_path
      v
[Done] Collection ready for search
```

Re-ingesting a file is an **upsert** — old chunks are removed before new ones are written. There is no duplication.

## Embedding write contract

Stage 4 is fail-closed
([ADR-051](../adr/051-fail-closed-embedding-write-contract.md)): the store
adapter validates the complete embedding batch before any backend
mutation. The shared validator rejects a batch that contains:

- no identifiers or no vectors (empty batch)
- a count of identifiers that differs from the count of vectors
- a value that is not a sized vector, or an empty vector
- a non-numeric element (booleans are rejected)
- a non-finite element (NaN or infinity)
- mixed vector dimensions within one batch
- a dimension that conflicts with the existing collection

A rejected batch writes nothing: no rows, no collection recreation, and no
generation change. The error names the collection, the embedding
provider/model, and each affected node or row identifier. Vectors are
never normalised, truncated, or repaired — the validator reports the
fault and stops the write. Norm policy is a separate decision.

## Source and chunk lineage

Every production-ingested chunk carries stable identity metadata
([ADR-052](../adr/052-stable-source-chunk-lineage.md)). The identifiers are
deterministic hashes: the same inputs always produce the same value.
`core/ingestion/source_state.py` owns the formulas and stamps them after
parsing, chunking, and metadata extraction but before embedding, so no
identifier ever changes a vector or the text an LLM sees.

### The identity hierarchy

| Field                | Formula                                                                                                                                                    | Stability                                                                                   |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `file_path`          | canonical absolute path                                                                                                                                     | Human-readable locator for display and diagnostics                                          |
| `source_id`          | `"src_" + SHA-256("file\0" + canonical path)`                                                                                                               | Stable while the file is edited in place; new after a move or copy; identical across collections |
| `source_content_hash` | SHA-256 of the original file bytes                                                                                                                        | New when bytes change; shared by equal bytes at two paths                                    |
| `source_version`     | SHA-256 of `source_content_hash` + NUL + `source_index_identity`                                                                                            | New when bytes or any index-shaping setting (parser, chunker, metadata, embedding) changes   |
| `source_chunk_index` | zero-based ordinal within the version                                                                                                                       | Orders membership in the chunk set                                                           |
| `source_chunk_count` | N, the chunk total for the version                                                                                                                          | Declares the size of the complete set                                                        |
| `chunk_id`           | `"chk_" + SHA-256(source_id + NUL + source_version + NUL + decimal index + NUL + chunk text hash)`                                                          | Stable for the same text at the same ordinal in one version                                  |
| vector row ID        | SHA-256 of `source_id` + NUL + `source_attempt` + NUL + `chunk_id`                                                                                          | Attempt-specific; never a store primary key                                                  |

All digests are lower-case hexadecimal over UTF-8 input joined with NUL
separators. `source_id` excludes the collection name, so one file indexed
into two collections carries one identity. The vector row ID stays internal:
a forced re-ingestion reproduces the same `chunk_id` values but writes fresh
row IDs, so candidate and durable attempts coexist until verification
([ADR-048](../adr/048-bounded-failure-safe-ingestion.md)). Ordinary public
results never expose the row ID.

### Ordered reconstruction

One `source_id` plus one `source_version` is a complete ordered chunk set:

```text
rows    = all rows with source_id = "src_…" and source_version = "…"
assert  every row has source_chunk_count == N and N == len(rows)
ordered = rows sorted by source_chunk_index   # indices are 0, 1, …, N-1
```

Sorting by `source_chunk_index` rebuilds the indexed chunk sequence. This
reconstructs the INDEXED representation only. It does not recover the
original file bytes, PDF layout, or parser input. The source file and
`source_content_hash` remain authoritative for the original content.

### Moving or copying a file

Identity follows the path. A new canonical path is a new logical source, so:

1. Delete the old path from the collection.
2. Ingest the destination path.

The system does not track moves or renames. Equal bytes at two paths share
`source_content_hash` but keep different `source_id` values; content is never
deduplicated.

### Pre-lineage rows fail before mutation

If a collection holds rows for a canonical path that lack, or disagree on,
the derived `source_id`, ingestion stops before any parse, embedding, or
store write. The error names the path and instructs you to rebuild the
affected data by deleting the source or collection and re-ingesting it. The
stored rows are never migrated, upgraded, or deleted. This is a deliberate
clean boundary: no production documents predate this change.

## PDF reader configuration

The PDF parser is a pluggable factory controlled by the `PDF_READER`
environment variable. Accepted values:

| Value           | Description                                                              | Install                        |
| --------------- | ------------------------------------------------------------------------ | ------------------------------ |
| `pdf_inspector` | Default. Rust markdown extractor. Emits one document per PDF.            | Base dependency                |
| `pypdf`         | Always available via `llama-index-readers-file`. Terminal fallback.      | Base (transitive)              |
| `liteparse`     | Column-aware reading order + bounding-box metadata.                      | Base dependency                |
| `pypdfium2`     | Same PDFium engine as LiteParse, no bbox. Fallback tier.                 | `[pdf-pypdfium2]` extra        |
| `auto`          | Probes in order: liteparse → pypdfium2 → pypdf.                          | Depends on what is installed   |

The packaged default is `pdf_inspector`, a base dependency selected through
configuration after Experiment 14
([ADR-050](../adr/050-configure-pdf-inspector-as-default-reader.md)).
`auto` keeps the LiteParse-first capability policy. Set `PDF_READER` to any
registered name to override the default. A configured reader that is not
importable logs an error and falls back to pypdf.

`pdf_inspector` emits one document per PDF, where pypdf and LiteParse emit
per-page documents. Markdown chunking then splits that single document, so
source-document boundaries change with this reader.

LiteParse captures bounding-box metadata (`page`, `column`,
`section_bbox`, `bbox_schema_version`) on every emitted Document for
future spatial RAG capabilities. OCR is disabled by default
(`LITEPARSE_OCR_ENABLED=false`) — enable it only for scanned PDFs.

See [ADR-020](../adr/020-use-liteparse-as-pdf-reader.md) for the factory
adoption rationale and [ADR-050](../adr/050-configure-pdf-inspector-as-default-reader.md)
for the default-selection decision and Experiment 14 results.

## Document backends

Document reading dispatches through a registry selected by `DOCUMENT_BACKEND`.

| Value   | Reads                             | Install                 |
| ------- | --------------------------------- | ----------------------- |
| `local` | All supported formats (default)   | Base dependency         |
| `azure` | `.pdf`, `.docx`, and `.doc` only  | `uv sync --extra azure` |

Files outside azure's list read through the local backend even when
`DOCUMENT_BACKEND=azure`. An unknown value fails server start-up and
lists the registered names.

Azure needs credentials (`AZURE_DOC_INTELLIGENCE_ENDPOINT`,
`AZURE_DOC_INTELLIGENCE_KEY`) and the optional package. Either piece
missing degrades azure to local before any file is read; each warning
names what is missing. At read time a failed azure attempt retries once
after a 5-second delay, then falls back to local exactly once. Every
step logs a diagnostic naming what happened, so a local-served file is
never silent.

Both backends run their blocking parser work in worker threads, so a
long parse never blocks the MCP event loop.

## Supported file formats

`.pdf` `.docx` `.pptx` `.txt` `.md` `.html` `.csv`

For directories, the server recursively finds all supported files.

## Embedding models

Set `EMBED_MODEL` in `.env` to any Ollama embedding model:

| Model                    | Params | Dims  | Context | MTEB | Pull command                       | Notes                                                                    |
| ------------------------ | ------ | ----- | ------- | ---- | ---------------------------------- | ------------------------------------------------------------------------ |
| **qwen3-embedding:0.6b** | ~600M  | 1,024 | 32,768  | —    | `ollama pull qwen3-embedding:0.6b` | **Default** — 100% Hit@1 in experiments, practical ingest times          |
| nomic-embed-text         | 137M   | 768   | 8,192   | 62.4 | `ollama pull nomic-embed-text`     | Fastest query latency (~36ms), but lower retrieval quality (94.1% Hit@1) |
| mxbai-embed-large        | 334M   | 1,024 | 512     | 64.7 | `ollama pull mxbai-embed-large`    | Highest MTEB score for short chunks                                      |
| all-minilm               | 23M    | 384   | 256     | ~58  | `ollama pull all-minilm`           | Blazing fast, tiny footprint                                             |

See [ADR-009](../adr/009-switch-to-qwen3-embedding-0-6b.md) for the full evidence behind the default model choice.

> **llama.cpp provider:** When `EMBED_PROVIDER=local` and `LOCAL_BACKEND=llamacpp`, set `LLAMACPP_EMBED_MODEL` to the GGUF filename instead of `EMBED_MODEL`. The same models are available in GGUF format from HuggingFace. When `EMBED_PROVIDER=cloud` and `CLOUD_BACKEND=openrouter`, set `OPENROUTER_EMBED_MODEL` to a cloud embedding model (e.g., `text-embedding-3-small`). See [Providers](providers.md) for setup.

### How long will ingestion take?

Practical timings on Apple Silicon (M-series) with `qwen3-embedding:0.6b`, default settings (`INGESTION__EMBED_CONCURRENCY=2`, `INGESTION__EMBED_BATCH_SIZE=100`, `CHUNKING__CHUNK_SIZE=512`):

| Scenario                                     | Time        |
| -------------------------------------------- | ----------- |
| 1 PDF (~117 chunks)                          | ~14 seconds |
| 5 PDFs (~585 chunks)                         | ~70 seconds |
| 20 PDFs (~2,340 chunks)                      | ~5 minutes  |
| Full Zotero library (57 PDFs, ~6,600 chunks) | ~13 minutes |

For comparison, the larger `qwen3-embedding:8b` model (4,096-dim vectors) takes ~3 hours for the same Zotero library — the 0.6b model is **13× faster** with identical retrieval quality in our tests.

> **Apple Silicon note:** Ollama serialises `/api/embed` requests internally on Apple Silicon, so `INGESTION__EMBED_CONCURRENCY > 2` yields diminishing returns. Setting it to 2 overlaps network round-trips with embedding computation; beyond that, requests queue up in Ollama's internal pipeline.

File reading is sequential. Tune throughput with `INGESTION__EMBED_BATCH_SIZE` and `INGESTION__EMBED_CONCURRENCY` rather than file-reader worker settings.

Run `uv run rag-mcp benchmark` to measure throughput on your own hardware.

### Switching models

```bash
# 1. Pull the new model
ollama pull mxbai-embed-large

# 2. Update .env
EMBED_MODEL=mxbai-embed-large

# 3. Re-index your documents into a fresh collection
rag-mcp ingest /path/to/docs/
```

> **Why re-index?** The selected vector store locks the vector dimension at collection creation time. Each model produces a different dimension (nomic=768, mxbai=1024, minilm=384). Switching models requires a fresh collection.

## Chunk size guide

`--chunk-size` controls how many **characters** go into each chunk. The embedding model has a **context length** in **tokens**. A rough guide: ~4 characters ≈ 1 token for English.

| Model                | Context (tokens) | Max safe chunk-size | Default 512 safe? |
| -------------------- | ---------------- | ------------------- | ----------------- |
| qwen3-embedding:0.6b | 32,768           | ~130,000 chars      | Yes               |
| nomic-embed-text     | 8,192            | ~32,000 chars       | Yes               |
| mxbai-embed-large    | 512              | ~1,500 chars        | Yes               |
| all-minilm           | 256              | ~1,000 chars        | Yes               |

The default 512-character chunk size is safe for all models. For models with large context windows:

```bash
# 2048-char chunks are fine (2048 × 0.25 = 512 tokens)
rag-mcp ingest /path/to/docs/ --chunk-size 2048
```

## Progress and interruption

Progress bars appear automatically in TTY terminals (Rich). In non-TTY contexts (pipes, CI) plain text is emitted to stderr. Press Ctrl+C once for graceful shutdown (finishes the current file, skips the rest). Press again to force quit.

## Which model runs when

| Stage                              | Model type                                  | What it does                 | Speed impact            |
| ---------------------------------- | ------------------------------------------- | ---------------------------- | ----------------------- |
| Metadata extraction (local mode)   | Chat/LLM (e.g. qwen3:0.6b)                  | Classifies document category | ~2s per file            |
| Metadata extraction (keyword mode) | None (regex)                                | Pattern matching             | Instant                 |
| Embedding                          | Embedding model (e.g. qwen3-embedding:0.6b) | Converts text to vectors     | ~50–500ms per chunk     |
| Search (rerank)                    | Cross-encoder (ms-marco-MiniLM-L-6-v2)      | Re-scores top results        | ~10–50ms per query pair |

The embedding model and chat/classification model are **separate** — each pulled independently via Ollama.
