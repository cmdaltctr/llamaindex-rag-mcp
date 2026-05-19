## Why

Document ingestion with `qwen3-embedding:8b` takes ~6 minutes to embed 166 chunks (~2.2 seconds per chunk). Models like `qwen3-embedding:0.6b` (already pulled) and proper GPU/Metal acceleration could reduce this to seconds instead of minutes. We need to understand where the bottleneck lives — Ollama's batching, GPU utilisation, or our own pipeline — and fix it so that ingesting a full Zotero library of ~57 PDFs is practical.

## What Changes

- **Investigate** whether Metal/GPU acceleration is active on this Apple Silicon Mac
- **Measure** embedding throughput with `qwen3-embedding:0.6b` vs `qwen3-embedding:8b`
- **Explore** whether Ollama's `/api/embed` supports concurrent requests or if LlamaIndex can dispatch batches in parallel
- **Optionally** switch to a smaller model or tune batch/concurrency settings based on findings
- **Add** structured logging via `RichHandler` for all future performance investigations
- **Document** the optimal settings in `.env.example`

## Capabilities

### New Capabilities
- `embedding-performance-benchmark`: A repeatable benchmark that measures embedding throughput (chunks/second) for a given model, batch size, and concurrency setting. Outputs a table of results to stderr.
- `metal-gpu-verification`: Run-time check that logs whether Ollama is using Metal GPU or CPU-only inference, so we can detect acceleration regressions.
- `concurrent-embedding`: If Ollama supports it, parallelise embedding batches across multiple concurrent `/api/embed` requests instead of one-at-a-time.

### Modified Capabilities
- (none — no existing specs change behaviour at the requirement level)

## Impact

- `src/rag_mcp/ingestion.py`: Potential changes to how `_embed_and_write` dispatches embedding work
- `src/rag_mcp/config.py`: May add `EMBED_CONCURRENCY` tuning or GPU-detection flags
- `src/rag_mcp/cli.py`: Add `RichHandler` logging, benchmark subcommand
- `.env` / `.env.example`: Updated defaults for the chosen optimal model
- `pyproject.toml`: No new dependencies unless we add `structlog` (optional)
