## Context

The current ingestion pipeline sends all nodes to `VectorStoreIndex(...)` which internally calls `Settings.embed_model.get_text_embedding_batch(...)`. This calls Ollama's `/api/embed` endpoint with one batch at a time — even though `EMBED_CONCURRENCY=2` is configured, the `_embed_semaphore` and the single `VectorStoreIndex` call means batches are processed sequentially.

A 166-chunk PDF takes ~6 minutes with `qwen3-embedding:8b`. With `qwen3-embedding:0.6b` (already pulled) we expect ~10× faster, but we still lack:
- Visibility into whether Metal GPU is being used
- A repeatable way to compare model/batch-size/concurrency combinations
- Confidence that concurrent embedding requests won't overload Ollama

## Goals / Non-Goals

**Goals:**
- Measure and document embedding throughput across model variants
- Verify Metal GPU acceleration is active
- Expose a benchmark mode so future model changes are data-driven
- Switch `.env` default to the fastest acceptable model

**Non-Goals:**
- Rewriting OllamaEmbedding or LlamaIndex internals
- Adding cloud-based embedding providers (OpenAI, etc.)
- Modifying the MCP server protocol or tool signatures

## Decisions

1. **Benchmark as a CLI subcommand, not a script.** `rag-mcp benchmark` can be run standalone without touching ChromaDB state. Uses the same `Settings.embed_model` pipeline so results are representative.

2. **GPU check via `ollama ps` at start-up.** Run `ollama ps --format json` in a subprocess when `LOG_LEVEL=DEBUG` is set, parse the runner info, and log whether Metal appears. No new dependencies.

3. **Concurrent embedding via multiple `VectorStoreIndex` calls is risky.** Ollama's `/api/embed` is designed for batched inputs (one request, many texts). Firing N concurrent requests may exhaust VRAM or cause queueing. Start with single-request benchmarking and only explore concurrency if single-batch throughput is still too slow.

4. **RichHandler for interactive output, plain logging for server.** The CLI should use `RichHandler` for coloured progress. The MCP server stays at WARNING with plain format to avoid flooding the host's stderr capture.

## Risks / Trade-offs

- **Risk: `ollama ps` output format may change** → Mitigation: wrap in try/except, log warning on failure
- **Risk: Concurrent embedding triggers OOM on 16GB Mac** → Mitigation: benchmark single-batch first, cap concurrency at 2
- **Risk: `qwen3-embedding:0.6b` quality is too low** → Mitigation: benchmark results include chunk count / vector dimension so quality-vs-speed trade-off is visible. Keep 8b as commented alternative in `.env`.
