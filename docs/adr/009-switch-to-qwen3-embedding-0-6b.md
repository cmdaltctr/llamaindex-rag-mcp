# ADR-009: Switch to `qwen3-embedding:0.6b` as the Default Embedding Model

**Status**: Accepted
**Date**: 2026-05-19
**Change**: `optimise-embedding-performance`

## Context

The RAG pipeline originally used `nomic-embed-text` (768-dim) as the default embedding model. During initial development we temporarily switched to `qwen3-embedding:8b` (4096-dim) for evaluation, but this proved impractically slow — ingesting a single 117-chunk PDF took ~6 minutes (0.63 chunks/sec via the concurrent embedding pipeline, or 0.45 chunks/sec without it).

We needed to choose a default embedding model that balances three competing concerns:

1. **Ingestion throughput** — embedding a full Zotero library (~57 PDFs, ~6,600 chunks) should complete in minutes, not hours
2. **Query latency** — each user query must return results in under 200ms for interactive use
3. **Retrieval quality** — the model must reliably return the correct document in the top results, not just be fast

Three models were evaluated:

| Model                  | Dimensions | Size   |
| ---------------------- | ---------- | ------ |
| `nomic-embed-text`       | 768        | ~274 MB |
| `qwen3-embedding:0.6b`   | 1024       | ~639 MB |
| `qwen3-embedding:8b`     | 4096       | ~4.7 GB |

## Decision

**Use `qwen3-embedding:0.6b` as the default embedding model.**

### Evidence

#### Throughput benchmark (via `rag-mcp benchmark`)

Test file: `ScientificAdvertising.pdf` (117 chunks, CHUNK_SIZE=512, CHUNK_OVERLAP=64)

| Model                  | Chunks | Avg Time (s) | Chunks/sec | vs nomic | vs 8b |
| ---------------------- | ------ | ------------ | ---------- | -------- | ----- |
| `nomic-embed-text`       | —      | —            | **15.3**   | 1.0× (baseline) | — |
| `qwen3-embedding:0.6b`   | 117    | 14.0         | **8.35**   | 1.8× slower | **13.2×** |
| `qwen3-embedding:8b`     | 117    | 185.8        | 0.63       | 24× slower  | 1.0× (baseline) |

The 0.6b model is **13.2× faster** than the 8b model for embedding documents, reducing a full Zotero library ingestion from ~3 hours to ~13 minutes. nomic-embed-text is the fastest at 15.3 chunks/sec (1.8× faster than 0.6b), but this throughput advantage must be weighed against retrieval quality.

#### Retrieval quality experiment (Experiment 2)

Test corpus: 6 documents (3 PDFs, 2 READMEs, 1 text) — 207 chunks total
Test queries: 17 queries (3 per document, 2 for one document)
Reranking: disabled (isolating embedding model quality)

| Model                  | Hit@1  | Hit@3  | Hit@5  | MRR   | Avg Query Latency |
| ---------------------- | ------ | ------ | ------ | ----- | ----------------- |
| `nomic-embed-text`       | 94.1%  | 94.1%  | 94.1%  | 0.941 | **36.2 ms**       |
| **`qwen3-embedding:0.6b`** | **100.0%** | **100.0%** | **100.0%** | **1.000** | 104.3 ms |
| `qwen3-embedding:8b`     | 100.0% | 100.0% | 100.0% | 1.000 | 259.2 ms          |

Key findings:
- **Both qwen3 variants achieve 100% Hit@1** — the 8b model offers **no quality advantage** over the 0.6b model on this test set
- **nomic-embed-text missed 1 query** (a specific section lookup in a small README file)
- **qwen3-embedding:0.6b is 2.5× faster per query** than the 8b model (104ms vs 259ms)

#### Combined assessment

| Decision        | Throughput Evidence                           | Quality Evidence                                |
| --------------- | --------------------------------------------- | ----------------------------------------------- |
| 0.6b over 8b    | ✅ **13.2× faster** embedding (8.35 vs 0.63 chunks/sec) | ✅ **Neither has quality advantage** — both score 100% Hit@1 |
| 0.6b over nomic | ⚠️ nomic **1.8× faster** (15.3 vs 8.35 chunks/sec)  | ✅ **0.6b is better** — 100% vs 94.1% Hit@1 |

### Rationale

1. **The 8b model provides no retrieval quality benefit** over the 0.6b model at 3× the query latency and 13× the embedding time. The higher-dimensional (4096) embeddings do not meaningfully improve document discrimination for this application.

2. **The 0.6b model reliably outperforms nomic-embed-text** on retrieval quality (100% vs 94.1% Hit@1), and its ~104ms query latency is well within interactive-use requirements.

3. **The 0.6b model makes full-library ingestion practical** — a 57-PDF Zotero library would embed in ~13 minutes vs ~3 hours with the 8b model.

4. **The 0.6b model produces 4× smaller vectors** (1024-dim vs 4096-dim), reducing ChromaDB storage requirements proportionally.

## Consequences

### Positive
- **Practical ingestion times**: A typical document collection embeds in minutes, enabling users to index entire Zotero libraries
- **Better retrieval quality** than the original nomic-embed-text default (94.1% → 100% Hit@1 on our test set)
- **No quality sacrifice** compared to the larger 8b model — same perfect retrieval at a fraction of the cost
- **Smaller vector index** — 1024-dim embeddings consume 4× less storage than 4096-dim

### Neutral
- Query latency increased from ~36ms (nomic) to ~104ms (0.6b), but this remains under 200ms and is imperceptible in interactive use

### Risk
- A different, more challenging corpus (e.g., many closely related documents on the same topic) might expose quality differences between 0.6b and 8b that this experiment did not capture. The decision should be revisited if retrieval degrades on future, more diverse document collections.

## Alternatives Considered

1. **`nomic-embed-text`** — fastest query latency (36ms) but lowest retrieval quality (94.1% Hit@1). Acceptable if latency is the only concern.

2. **`qwen3-embedding:8b`** — same retrieval quality as 0.6b but 13.2× slower embedding and 2.5× slower query latency. No practical advantage for this application.

3. **`rerank=True`** — the cross-encoder reranker can improve results for any embedding model, but adds latency and model download size (~23 MB). The embedding model decision is independent of reranker usage.

## References

- Throughput benchmark data: `experiments/embedding-performance.md`
- Retrieval quality experiment: `experiments/embedding-model-comparison-2026-05-19/results.md`
- Raw experiment data: `experiments/embedding-model-comparison-2026-05-19/eval_results.json`
- OpenSpec change: `openspec/changes/optimise-embedding-performance/`
- Concurrent embedding implementation: `ADRs 007` (CLI and parallel ingestion)
