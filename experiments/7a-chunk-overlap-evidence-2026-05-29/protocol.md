# Experiment 7a: Chunk Overlap Sensitivity on Evidence-Level Qasper

**ID**: `7a-chunk-overlap-evidence-2026-05-29`  
**Status**: READY TO RUN  
**Relation**: Follow-up to Experiment 7 and informed by Experiments 6b/6c.

## Why this experiment exists

Experiment 7 confirmed that raising `CHUNK_OVERLAP` from 64 to 100 is safe on
the small Exp 3 corpus, but that corpus is too easy: source-level Hit@1
saturates. Experiments 6b and 6c showed that Qasper-dev is a harder,
evidence-bearing corpus where chunk boundaries and top-k pressure matter.

Experiment 7a asks whether the overlap default remains safe under the harder
Qasper evidence-level evaluation.

## Key policy from prior learning

We keep `CHUNK_OVERLAP=100` as the production default unless there is a broad,
multi-corpus reason to change it. If Qasper shows a regression, record Qasper
as a known stress case / corpus-specific exception rather than reverting the
default for prose-heavy general corpora.

## Hypothesis

On Qasper-dev, overlap 100 should be within 2 percentage points of overlap 64
on Evidence Recall@5 at the same `(rerank, top_k)` cell, while keeping chunk
count within 15% of overlap 64.

If overlap 100 underperforms beyond this tolerance, the expected action is:

1. document the Qasper-specific regression;
2. keep the production default at 100;
3. recommend corpus-specific override guidance for Qasper-like academic QA.

## Corpus and ground truth

- Corpus: Qasper dev split, 20 NLP papers, rendered as Markdown.
- Ground truth: 53 evidence-bearing QA records.
- Source: copied from `experiments/6b-qasper-markdown-chunking-2026-05-28`.
- No symlinks: `corpus/` and `ground-truth.json` are local copies.
- `prepare_dataset.py` is also copied into 7a, so the local corpus and
  ground-truth can be regenerated without depending on 6b.

## Variables

| Type | Variable | Values |
| --- | --- | --- |
| Independent | `CHUNK_OVERLAP` | 32, 64, 100, 128 |
| Independent | Pass | A = reranker off, B = reranker on |
| Independent | `top_k` | 5, 10, 20 |
| Controlled | Chunker | Bare `SentenceSplitter`, forced for every file |
| Controlled | `CHUNK_SIZE` | 512 |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | Reranker pool | `RERANK_MAX_FETCH=50`, `RERANK_FETCH_MULTIPLIER=10` |

The bare splitter is intentional. We isolate overlap, not Markdown-aware
chunking. The Markdown chunk-size promotion from 6c is a separate finding.

No dedicated synthetic boundary-recovery query partition is added here. Qasper
already supplies long, evidence-bearing snippets from real papers, and those
snippets naturally stress sentence and chunk boundaries. Adding synthetic
boundary probes would introduce a second variable; this experiment keeps the
canonical 53-record Qasper set unchanged.

## Metrics

- Evidence Recall@1/@3/@5/@10
- Evidence MRR
- nDCG@5 and nDCG@10
- Section Match@1 diagnostic
- Chunk count, mean/P95/max token estimate
- Mean/P95 latency

## Procedure

```bash
cd experiments/7a-chunk-overlap-evidence-2026-05-29
uv run python ingest_overlap.py --overlaps 32,64,100,128
uv run python run_eval.py --overlaps 32,64,100,128 --top-ks 5,10,20 --rerank both
```

## Pass criteria

For each `(rerank, top_k)` cell, compare overlap 100 to overlap 64:

1. Evidence Recall@5 delta ≥ -2 pp.
2. Evidence MRR delta ≥ -0.01.
3. Chunk count ratio ≤ 1.15×.

## Interpretation

- If overlap 100 passes: ADR-016's default is reinforced on a harder corpus.
- If overlap 100 fails only on Qasper: keep default 100; record Qasper as a
  known stress case where users may choose `CHUNK_OVERLAP=64` or compensate
  with larger `top_k` / reranking.
- If overlap 128 beats 100 without excess chunk growth: consider a future
  corpus-specific tuning experiment, not a default change.
