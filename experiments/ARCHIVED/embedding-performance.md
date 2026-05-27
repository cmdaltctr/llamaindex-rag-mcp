# Embedding Performance Report

**Date**: 2026-05-19
**Machine**: Apple Silicon Mac (macOS, Darwin)
**Test file**: `ScientificAdvertising.pdf` (117 chunks, CHUNK_SIZE=512, CHUNK_OVERLAP=64)

## Benchmark Results

| Model | Chunks | Avg Time (s) | Chunks/sec | Vector Dim | Speedup |
|-------|--------|-------------|------------|------------|---------|
| `qwen3-embedding:0.6b` | 117 | 14.0 | **8.35** | 1024 | **13.2×** |
| `qwen3-embedding:8b` | 117 | 185.8 | **0.63** | 4096 | 1.0× (baseline) |

## Configuration Used

| Setting | Value |
|---------|-------|
| `EMBED_BATCH_SIZE` | 100 |
| `EMBED_CONCURRENCY` | 2 |
| `CHUNK_SIZE` | 512 |
| `CHUNK_OVERLAP` | 64 |

## Recommendations

### Use `qwen3-embedding:0.6b` as the default model

The 0.6b model delivers a **13.2× speedup** over the 8b model while producing
1024-dimensional embeddings (vs 4096 for 8b). For a local RAG system targeting
personal knowledge management (Zotero libraries, document collections), the
smaller model is the clear choice:

- **Fast enough for interactive use**: A 117-chunk PDF embeds in ~14 seconds.
- **Smaller vector index**: 1024-dim vectors consume 4× less storage than 4096-dim.
- **Lower VRAM**: ~639 MB vs ~4.7 GB model download.

### When to consider `qwen3-embedding:8b`

- Research requiring maximum retrieval precision
- Very large document collections (>10K chunks) where retrieval accuracy matters
- When disk space and time are not constraints

### Concurrency findings

Ollama's `/api/embed` endpoint serialises requests internally on Apple Silicon,
so `EMBED_CONCURRENCY > 2` provides diminishing returns. Setting it to 2
provides a modest benefit for overlapping network round-trips with embedding
computation.

## Historical Context

The original bottleneck was measured at ~0.45 chunks/sec with `qwen3-embedding:8b`
before the concurrent embedding and batching improvements were implemented.
After implementation of batch embedding (`EMBED_BATCH_SIZE=100`) and concurrent
dispatch (`EMBED_CONCURRENCY=2`), throughput improved to ~0.63 chunks/sec.
Switching to `qwen3-embedding:0.6b` then delivered the 13.2× speedup to reach
8.35 chunks/sec.

## Practical Impact

| Scenario | 8b Model | 0.6b Model |
|----------|---------|-----------|
| 1 PDF (117 chunks) | ~3 min | ~14 sec |
| 5 PDFs (~585 chunks) | ~15 min | ~70 sec |
| 20 PDFs (~2,340 chunks) | ~62 min | ~5 min |
| Full Zotero (57 PDFs, ~6,600 chunks) | ~3 hr | ~13 min |
