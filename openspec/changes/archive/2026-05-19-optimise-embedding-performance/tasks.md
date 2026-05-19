## 1. Logging & Diagnostics

- [x] 1.1 Swap `_setup_logging()` to use `RichHandler` from `rich.logging` for coloured, timestamped output
- [x] 1.2 Add GPU detection via `ollama ps --format json` in `_setup_logging()` when `LOG_LEVEL=DEBUG`
- [x] 1.3 Log model name, vector dimension, and batch size at INFO on start-up

## 2. Benchmark Subcommand

- [x] 2.1 Add `rag-mcp benchmark` CLI subcommand in `cli.py` that accepts `--text`, `--file`, and `--iterations`
- [x] 2.2 Implement benchmark logic: read/chunk text → embed via `Settings.embed_model` → measure time → print results table
- [x] 2.3 Ensure benchmark is non-destructive (no ChromaDB writes)
- [x] 2.4 Verify benchmark works with both file input and inline text

## 3. Concurrent Embedding

- [x] 3.1 Modify `_embed_and_write()` in `ingestion.py` to split nodes into batches of `EMBED_BATCH_SIZE`
- [x] 3.2 Dispatch batches concurrently via `ThreadPoolExecutor` with `EMBED_CONCURRENCY` workers
- [x] 3.3 Implement all-or-nothing write: wait for all batches to complete before writing to ChromaDB
- [x] 3.4 Fall back to sequential dispatch when `EMBED_CONCURRENCY <= 1`

## 4. Benchmark & Tune

- [x] 4.1 Run `rag-mcp benchmark` with `qwen3-embedding:0.6b` and record chunks/sec
- [x] 4.2 Compare throughput against `qwen3-embedding:8b` (already measured: ~0.45 chunks/sec)
- [x] 4.3 Test concurrent embedding with `EMBED_CONCURRENCY=2` and `EMBED_CONCURRENCY=3`
- [x] 4.4 Update `.env.defaults` with optimal settings
- [x] 4.5 Document findings and recommendations in `docs/embedding-performance.md`

## 5. Clean-up

- [x] 5.1 Update `.env` with `qwen3-embedding:0.6b` as active model (done)
- [x] 5.2 Remove old chroma_db and re-index test document with new model
- [x] 5.3 Run full test suite: `uv run pytest -m "not slow" --cov=rag_mcp`
- [x] 5.4 Create ADR-009 documenting the embedding model decision with throughput and retrieval quality evidence
