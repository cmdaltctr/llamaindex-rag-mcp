# Experiment 7a Results: Chunk Overlap Sensitivity on Qasper

**ID**: `7a-chunk-overlap-evidence-2026-05-29`  
**Date run**: 2026-05-29  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent support  
**Status**: **INCONCLUSIVE for global default; FAIL on Qasper at production `top_k=5`**  
**Raw data**: external artifact; see [`artifacts.md`](./artifacts.md). Summary data is tracked in [`eval_results.summary.json`](./eval_results.summary.json).

---

## Hypothesis

We wanted to check whether the current production default,
`CHUNK_OVERLAP=100`, is still safe on a harder evidence-level corpus.

In plain terms: chunk overlap controls how much text is repeated between
neighbouring chunks. More overlap can prevent evidence from being split across
chunk boundaries, but it also creates more chunks and more near-duplicates.

The test was:

> Does overlap 100 perform at least about as well as the previous default,
> overlap 64, on Qasper evidence retrieval?

The pass bar was deliberately tolerant:

- Evidence Recall@5 for overlap 100 should be no worse than overlap 64 by more
  than 2 percentage points.
- Evidence MRR should be no worse by more than 0.01.
- Chunk count should stay within 15% of overlap 64.

---

## Variables

| Type | Variable | Values |
| --- | --- | --- |
| Independent | `CHUNK_OVERLAP` | 32, 64, 100, 128 |
| Independent | `top_k` | 5, 10, 20 |
| Independent | Pass | A = reranker off, B = reranker on |
| Dependent | Evidence Recall@1/@5/@10 | Whether the retrieved chunks contain the labelled evidence |
| Dependent | Evidence MRR | How high the first correct evidence chunk appears |
| Dependent | nDCG@5 | Ranking quality with graded relevance |
| Dependent | Chunk count | Storage / embedding-cost proxy |
| Controlled | Corpus | Qasper dev, 20 papers, 53 evidence-bearing QA records |
| Controlled | Chunker | Bare `SentenceSplitter`, `CHUNK_SIZE=512` |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | Reranker pool | `RERANK_MAX_FETCH=50`, `RERANK_FETCH_MULTIPLIER=10` |

This experiment intentionally used the bare sentence splitter for every file.
That isolates overlap only. Markdown-aware chunking and the 6c
`MARKDOWN_CHUNK_SIZE=1024` decision are separate.

---

## Method

The experiment used the self-contained copied Qasper corpus in this directory.
No symlinks were used.

Commands used:

```bash
cd experiments/7a-chunk-overlap-evidence-2026-05-29

uv run python ingest_overlap.py --overlaps 32
uv run python ingest_overlap.py --overlaps 64
uv run python ingest_overlap.py --overlaps 100
uv run python ingest_overlap.py --overlaps 128

uv run python run_eval.py \
  --overlaps 32,64,100,128 \
  --top-ks 5,10,20 \
  --rerank both
```

Each overlap value got its own isolated ChromaDB:

- `chroma_overlap_32/`
- `chroma_overlap_64/`
- `chroma_overlap_100/`
- `chroma_overlap_128/`

---

## Results

### Main production-shaped result

The most important cell is:

- Pass B: reranker on
- `top_k=5`: current production-style retrieval depth

| Overlap | Evidence Recall@5 | Evidence MRR | nDCG@5 | Chunks | P95 latency |
| ------: | ----------------: | -----------: | -----: | -----: | ----------: |
| 32 | 56.60% | 0.3758 | 0.7387 | 242 | 1,789 ms |
| **64** | **62.26%** | **0.3849** | 0.7288 | 259 | 1,428 ms |
| 100 | 58.49% | 0.3827 | 0.7243 | 283 | 1,468 ms |
| 128 | 58.49% | **0.4107** | **0.7601** | 302 | 1,746 ms |

*Evidence Recall@5 = percentage of queries where at least one of the top 5 retrieved chunks contains the labelled evidence; Evidence MRR = Mean Reciprocal Rank for evidence chunks (1.0 = evidence always at rank 1, 0.5 = average rank 2); nDCG@5 = normalized Discounted Cumulative Gain at 5, measures ranking quality with graded relevance (1.0 = perfect ranking); P95 latency = 95th percentile response time in milliseconds.*

Simple reading:

- Overlap 64 retrieved labelled evidence most often at the default `top_k=5`.
- Overlap 100 was close, but worse by **3.77 percentage points** on
  Evidence Recall@5.
- Overlap 100's MRR was almost identical to 64, meaning when it did find the
  evidence, the first correct chunk was ranked about as high.
- Overlap 128 improved MRR and nDCG@5 but failed the chunk-budget criterion
  because it created 16.6% more chunks than overlap 64.

### Overlap 100 vs overlap 64

| Pass | top_k | Recall@5 delta | MRR delta | Chunk ratio | Verdict |
| --- | ---: | --------------: | --------: | ----------: | --- |
| A / rerank off | 5 | -3.78 pp | -0.0403 | 1.093× | Fail |
| A / rerank off | 10 | -3.78 pp | -0.0353 | 1.093× | Fail |
| A / rerank off | 20 | -3.78 pp | -0.0326 | 1.093× | Fail |
| B / rerank on | 5 | -3.77 pp | -0.0022 | 1.093× | Fail on Recall@5 |
| B / rerank on | 10 | +1.88 pp | -0.0135 | 1.093× | Mixed |
| B / rerank on | 20 | -1.88 pp | -0.0096 | 1.093× | Pass |

*pp = percentage points (e.g., -3.78 pp means overlap 100 is 3.78 percentage points worse than overlap 64); MRR delta = change in Mean Reciprocal Rank (negative means worse); Chunk ratio = ratio of chunk counts (overlap 100 / overlap 64).*

Simple reading:

- Without reranking, overlap 100 is consistently worse than overlap 64.
- With reranking, overlap 100 becomes acceptable only when the retrieval window
  is widened, especially at `top_k=20`.
- At the current production-style `top_k=5`, overlap 100 misses the pass bar on
  Qasper.

### Full summary table

| Overlap | Pass | top_k | Recall@1 | Recall@5 | Recall@10 | MRR | nDCG@5 | Chunks |
| ------: | :--: | ----: | -------: | -------: | --------: | ---: | -----: | -----: |
| 32 | A | 5 | 20.75% | 47.17% | 47.17% | 0.3047 | 0.6371 | 242 |
| 32 | A | 10 | 20.75% | 47.17% | 66.04% | 0.3315 | 0.4774 | 242 |
| 32 | A | 20 | 20.75% | 47.17% | 66.04% | 0.3392 | 0.4249 | 242 |
| 32 | B | 5 | 24.53% | 56.60% | 56.60% | 0.3758 | 0.7387 | 242 |
| 32 | B | 10 | 24.53% | 56.60% | 62.26% | 0.3744 | 0.6299 | 242 |
| 32 | B | 20 | 24.53% | 56.60% | 64.15% | 0.3847 | 0.5451 | 242 |
| 64 | A | 5 | 22.64% | 54.72% | 54.72% | 0.3239 | 0.6835 | 259 |
| 64 | A | 10 | 22.64% | 54.72% | 62.26% | 0.3340 | 0.5594 | 259 |
| 64 | A | 20 | 22.64% | 54.72% | 62.26% | 0.3446 | 0.4824 | 259 |
| 64 | B | 5 | 22.64% | **62.26%** | 62.26% | 0.3849 | 0.7288 | 259 |
| 64 | B | 10 | 24.53% | 60.38% | **73.58%** | 0.4040 | 0.6092 | 259 |
| 64 | B | 20 | 22.64% | **62.26%** | 71.70% | 0.4024 | 0.5639 | 259 |
| 100 | A | 5 | 15.09% | 50.94% | 50.94% | 0.2836 | 0.6754 | 283 |
| 100 | A | 10 | 15.09% | 50.94% | 62.26% | 0.2987 | 0.5228 | 283 |
| 100 | A | 20 | 15.09% | 50.94% | 62.26% | 0.3120 | 0.4494 | 283 |
| 100 | B | 5 | 26.42% | 58.49% | 58.49% | 0.3827 | 0.7243 | 283 |
| 100 | B | 10 | 24.53% | **62.26%** | 67.92% | 0.3905 | 0.6026 | 283 |
| 100 | B | 20 | 22.64% | 60.38% | 67.92% | 0.3928 | 0.5187 | 283 |
| 128 | A | 5 | 18.87% | 50.94% | 50.94% | 0.2940 | 0.7239 | 302 |
| 128 | A | 10 | 18.87% | 50.94% | 64.15% | 0.3117 | 0.5612 | 302 |
| 128 | A | 20 | 18.87% | 50.94% | 64.15% | 0.3213 | 0.4946 | 302 |
| 128 | B | 5 | **32.08%** | 58.49% | 58.49% | **0.4107** | **0.7601** | 302 |
| 128 | B | 10 | **30.19%** | 56.60% | **73.58%** | **0.4216** | 0.5992 | 302 |
| 128 | B | 20 | **30.19%** | 56.60% | 66.04% | **0.4144** | 0.5613 | 302 |

*Pass = A (reranker off) or B (reranker on); top_k = number of chunks retrieved; Recall@k = percentage of queries where at least one of the top k retrieved chunks contains the labelled evidence; MRR = Mean Reciprocal Rank for evidence chunks; nDCG@5 = normalized Discounted Cumulative Gain at 5, measures ranking quality with graded relevance.*

---

## Conclusion

### Decision

Do **not** change the global default based on this experiment alone.

Keep:

```text
CHUNK_OVERLAP=100
```

But document this caveat:

> Qasper-like academic evidence QA is a known stress case where
> `CHUNK_OVERLAP=64` performs better than `CHUNK_OVERLAP=100` at the current
> production-style `top_k=5`.

### Why not revert the default to 64?

Because this experiment measures one hard corpus. The earlier smoke corpus did
not show a regression, and the literature-backed reason for overlap 100 still
stands for general prose. Qasper is a specialised evidence-level academic QA
workload where smaller overlap appears to reduce chunk crowding.

### Practical recommendation

For Qasper-like academic QA:

1. Prefer `CHUNK_OVERLAP=64` if using `top_k=5`.
2. If staying with `CHUNK_OVERLAP=100`, use reranking and consider `top_k=20`.
3. Do not use overlap 128 as a default; it creates too many chunks, even though
   it improves some rank-sensitive metrics.

### What changed in the codebase?

No production code changed. This experiment only records a corpus-specific
configuration finding.

---

## Cleanup

To remove generated indexes:

```bash
rm -rf chroma_overlap_32 chroma_overlap_64 chroma_overlap_100 chroma_overlap_128
```
