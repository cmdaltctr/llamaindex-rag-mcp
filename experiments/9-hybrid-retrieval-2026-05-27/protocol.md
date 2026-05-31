# Experiment 9: Hybrid Retrieval Quality (Dense + BM25 + RRF)

**ID**: `hybrid-retrieval-2026-05-27`
**Date**: 2026-05-27
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent (for automation)
**Status**: PLANNED
**Related OpenSpec change**: `rag-hybrid-retrieval` (Tier 3)

---

## What this experiment is for

The Tier 3 OpenSpec change adds hybrid retrieval: dense vector search and
sparse BM25 search run in parallel, fused with Reciprocal Rank Fusion
(RRF), then handed to the existing reranker. The change ships behind a
feature flag (`HYBRID_ENABLED=false`) so default behaviour is unchanged.

This experiment is mandated by
`openspec/changes/rag-hybrid-retrieval/design.md` (Migration Plan, step 2)
and asks four questions:

1. Does hybrid retrieval **fix the documented Colosseum failure case** —
   the rare-term query that vector-only retrieval ranked at score 0.015
   in `experiments/1-reranker-threshold-calibration-2026-05-12/`?
2. Does hybrid **improve recall on rare-term / exact-match queries**
   broadly, not just the one Colosseum case?
3. Does hybrid **avoid regressing on semantic queries** where dense
   retrieval is the canonical winner (paraphrased queries with no
   keyword overlap)?
4. Is the **latency increase acceptable** — is hybrid + reranker still
   under a reasonable user-facing P95?

The result is the recommendation for whether a follow-up change should
flip `HYBRID_ENABLED` to `true` and/or promote `HYBRID_SPARSE_BACKEND`
from `bm25` to `auto`.

---

## Hypothesis

With hybrid retrieval enabled (BM25 + dense fused via RRF k=60) and the
existing reranker on top:

- **The Colosseum query** is retrieved at top-1 (regression target).
- **Rare-term Hit@1** improves by at least 10 percentage points vs
  dense-only.
- **Semantic Hit@1** stays within −2 percentage points of dense-only
  (no quiet regression).
- **End-to-end P95 latency** stays under 1.5 × dense-only P95 on the
  same hardware.

---

## Background

Pure dense vector search has a documented weakness on rare-term and
exact-match queries: product codes, legal citations, gene names, library
identifiers, error messages. The dense embedding for "Colosseum" is
similar to many embeddings about Roman architecture in general, so the
chunk that *literally mentions* the Colosseum can rank below chunks that
are semantically about Rome but contain no exact match.

The reranker is supposed to fix this — but only if it sees the gold
chunk in its candidate pool. If dense retrieval ranks the gold chunk
below the fetch cut-off, the reranker never gets a chance.

Hybrid retrieval addresses both failure modes by running BM25 in
parallel. BM25 is exact-keyword-friendly: it ranks documents by how
many query terms they contain, weighted by inverse document frequency.
The two rankings are fused with RRF, which is a parameter-free,
score-scale-agnostic fusion function:

```
score_fused(d) = Σ_r 1 / (k + rank_r(d))      with k = 60
```

The fused candidate list then feeds the existing reranker, whose
`÷30` threshold scaling is unchanged because the reranker still scores
`(query, chunk)` pairs the same way.

Recent literature converges on hybrid retrieval as the highest-payoff,
lowest-risk addition to a dense-only baseline:

- Cormack, G.V., Clarke, C.L.A. & Buettcher, S. (2009). *Reciprocal
  rank fusion outperforms Condorcet and individual rank learning
  methods*. SIGIR. — original RRF paper, source of `k=60`.
- Mala, S., Gezici, B. & Giannotti, F. (2025). *Weighted RRF on
  HaluBench*. — highest accuracy, lowest hallucination.
- Airy, R. & Baranwal, A. (2025). *Hybrid RAG hallucination
  reduction*. — 93.3 % hallucination reduction.
- Akarsu, M. et al. (2026). *BM25 vs dense retrieval on financial
  documents*. — BM25 wins on exact-match domains.
- Abirami, S. et al. (2025). *Hybrid RRF lifts Recall@100 to 0.997*.

The Tier 3 design doc (Decision 1) chooses RRF over weighted convex
combination because RRF needs no per-corpus tuning and is robust to
score-scale mismatch between the dense and sparse retrievers.

---

## Variables

| Type        | Variable                                                      | Values                                                                |
| ----------- | ------------------------------------------------------------- | --------------------------------------------------------------------- |
| Independent | Retrieval mode                                                | `dense-only` (control) / `hybrid + bm25` / `hybrid + native` (if pinned ChromaDB supports it) |
| Independent | Reranker                                                      | Off / On (cross-product with retrieval mode)                          |
| Dependent   | Colosseum query rank (named regression case)                  | Must be 1 under hybrid                                                |
| Dependent   | Hit@1, Hit@5, MRR@10, Recall@10                                | Per query category (rare-term / semantic / mixed)                     |
| Dependent   | End-to-end search latency (mean / P95)                        | —                                                                     |
| Dependent   | Fusion source counts (rank from dense vs sparse)              | Diagnostic — what is BM25 actually contributing?                      |
| Controlled  | Embedding model                                               | `qwen3-embedding:0.6b`                                                |
| Controlled  | RRF `k`                                                       | 60                                                                    |
| Controlled  | Reranker pool defaults                                        | `(RERANK_MAX_FETCH, RERANK_FETCH_MULTIPLIER)` chosen in Exp 5         |
| Controlled  | Calibrated `÷30` threshold scaling                            | Active                                                                |
| Controlled  | `CHUNK_SIZE` / `CHUNK_OVERLAP`                                | 512 / 100                                                             |
| Controlled  | Hardware                                                      | Apple Silicon Mac, 16 GB                                              |
| Controlled  | `HYBRID_RRF_K`                                                | 60 (RRF default)                                                      |

> **Why rerank cross-product?** Hybrid changes which candidates enter
> the reranker. We measure both `hybrid + no rerank` (pure fusion
> effect) and `hybrid + rerank` (production effect). The interesting
> question is whether hybrid earns its keep when the reranker is also
> on — if the reranker alone catches everything, hybrid adds latency
> for no gain.

---

## Environment & Prerequisites

| Requirement   | Version / Value                                                          |
| ------------- | ------------------------------------------------------------------------ |
| Python        | 3.12                                                                     |
| Ollama models | `qwen3-embedding:0.6b`                                                   |
| Reranker      | `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX                              |
| Dependency    | `rank_bm25` installed via the optional `hybrid` extra                    |
| Hardware      | Apple Silicon Mac, 16 GB                                                 |
| Code branch   | Post-Tier-3 with `HYBRID_ENABLED=true` available and BM25 path wired in |

```bash
ollama list   # qwen3-embedding:0.6b
uv sync --extra hybrid   # or whatever the Tier 3 extras name resolves to
uv run python -c "import rank_bm25; print(rank_bm25.__name__)"   # sanity
```

---

## Step 1: Build the corpus (most important step)

The corpus has three deliberately-designed packs:

```
experiments/9-hybrid-retrieval-2026-05-27/corpus/
├── exp1-fixtures/        ← copies of the 5 Exp 1 docs (Colosseum continuity)
├── rare-term-pack/       ← 5–10 short docs with exact-match identifiers
└── semantic-pack/        ← 5 docs where queries diverge from chunk wording
```

### Pack 1: Exp 1 fixtures (continuity)

Copy the 5 fixture documents from `tests/fixtures/` (the same ones used
in `experiments/1-reranker-threshold-calibration-2026-05-12/`):

```bash
cp tests/fixtures/{sample.txt,sample.md,python.txt,...} \
   experiments/9-hybrid-retrieval-2026-05-27/corpus/exp1-fixtures/
```

This keeps the Colosseum query alive as a regression target.

### Pack 2: Rare-term pack (the new contribution)

5–10 short documents (200–800 words each) containing **exact-match
identifiers** that dense embeddings struggle with:

| Identifier type        | Example documents to write or source                                 |
| ---------------------- | ------------------------------------------------------------------- |
| Product codes          | Short README mentioning `XK-2034b` or `MCP-1138` repeatedly         |
| Library identifiers    | Short doc using `numpy.fft.rfft2` or `torch.nn.LayerNorm`           |
| Legal citations        | Short summary citing `42 U.S.C. § 1983` or `EU Reg. 2016/679`       |
| Gene / drug names      | Short bio note mentioning `BRCA1` / `rs6265` / `ipilimumab`         |
| Error / version codes  | Short troubleshooting doc with `ECONNREFUSED` or `Python 3.12.0a3`  |

Hand-write these or extract paragraphs from real documentation. Each
document should be unambiguously about its identifier — a query
containing the identifier verbatim should obviously match this document
and obviously not match any other.

### Pack 3: Semantic pack (negative control)

5 documents where the query phrasing **deliberately diverges** from the
document phrasing. The point is to confirm hybrid does not silently
hurt the queries dense retrieval is supposed to win.

Examples:

- Document talks about "transformers process sequences in parallel"
  → query asks about "neural networks that handle long-range
  dependencies without recurrence" (paraphrase, no keyword overlap).
- Document talks about "the Colosseum was a Flavian amphitheatre"
  → query asks about "a famous Roman entertainment venue" (semantic).

Aim for queries with **zero exact-token overlap** with the gold chunk
(after lowercasing and stop-word removal). BM25 should fail on these;
dense embeddings should succeed; hybrid should match dense.

---

## Step 2: Write ground-truth queries

This is the second-most important step. Pre-write **18–25 queries**
partitioned roughly evenly:

| Partition          | Count    | Goal                                                  |
| ------------------ | -------- | ----------------------------------------------------- |
| Rare-term          | 6–8      | Hybrid should beat dense-only by 10+ pp               |
| Semantic           | 6–8      | Hybrid should match dense-only within −2 pp           |
| Mixed (general)    | 4–6      | Sanity — no regression                                |
| **Named cases**    | 2        | The Colosseum query (must hit) and one BM25-only case |

Format (`ground-truth.json`):

```json
{
  "queries": [
    {
      "query": "Where was the Colosseum built?",
      "expected_source": "sample.md",
      "expected_answer": "Rome",
      "category": "rare-term",
      "named_case": "colosseum"
    },
    {
      "query": "How does numpy.fft.rfft2 differ from fft2?",
      "expected_source": "numpy-fft-readme.md",
      "expected_answer": "real-input",
      "category": "rare-term"
    },
    {
      "query": "What architecture handles long-range dependencies without recurrence?",
      "expected_source": "transformers.md",
      "expected_answer": "self-attention",
      "category": "semantic"
    }
  ]
}
```

**Write all 18–25 queries before running anything.** Confirmation bias
is the biggest threat to a hybrid-vs-dense comparison.

---

## Step 3: Probe ChromaDB for native sparse capability (optional)

Before running the experiment, check whether the pinned ChromaDB version
supports native sparse vectors. This decides whether you run the
two-arm experiment (`dense-only` vs `hybrid + bm25`) or the three-arm
experiment (also adds `hybrid + native`).

```bash
uv run python - <<'PY'
import chromadb
print("chromadb version:", chromadb.__version__)
# Try to construct a collection with sparse-vector config — record what happens.
PY
```

Current implementation-time probe: the project has `chromadb 1.5.9`
installed, but the local `PersistentClient` runtime does not expose native
sparse retrieval for this project configuration. In the v1 default (`bm25`),
the native path is **not** used; this probe is informational only and tells
the next-change author whether to promote `HYBRID_SPARSE_BACKEND=auto`.

---

## Step 4: Ingest under each retrieval mode

Each mode gets its own ChromaDB. Ingestion is the same for `dense-only`
and `hybrid + bm25` (BM25 is built lazily at query time over the dense
chunks). The native mode (if supported) needs sparse-vector ingestion.

```bash
# Dense-only baseline
CHROMA_PERSIST_DIR=./chroma_dense \
  HYBRID_ENABLED=false \
  uv run rag-mcp ingest experiments/9-hybrid-retrieval-2026-05-27/corpus

# Hybrid + BM25 (uses the same ChromaDB shape; BM25 index is in-memory)
CHROMA_PERSIST_DIR=./chroma_hybrid_bm25 \
  HYBRID_ENABLED=true HYBRID_SPARSE_BACKEND=bm25 \
  uv run rag-mcp ingest experiments/9-hybrid-retrieval-2026-05-27/corpus

# Hybrid + native (only if Step 3 probe says ChromaDB supports it)
CHROMA_PERSIST_DIR=./chroma_hybrid_native \
  HYBRID_ENABLED=true HYBRID_SPARSE_BACKEND=native \
  uv run rag-mcp ingest experiments/9-hybrid-retrieval-2026-05-27/corpus
```

---

## Step 5: Run the eval

```bash
cd experiments/9-hybrid-retrieval-2026-05-27
uv run python run_eval.py \
  --modes dense-only,hybrid_bm25 \
  --rerank-cross   # runs each mode twice: once with reranker, once without
```

The script:

1. Loads `ground-truth.json` (18–25 queries) and the named regression cases.
2. For each (mode, reranker) cell:
   - Sets the appropriate env vars.
   - Resets the BM25 cache and the reranker singleton.
   - Fires 50 warm-up queries (discarded for latency).
   - Fires every ground-truth query and records:
     - `top_k` results, scores, fusion source ranks, latency.
     - Hit@1, Hit@5, MRR@10, Recall@10 per category.
     - Whether the named regression cases hit at top-1.
3. Prints a comparison table by category.
4. Saves raw data to `eval_results.json`.

Run cells:

| Cell | Mode             | Reranker |
| ---- | ---------------- | -------- |
| 1    | dense-only       | off      |
| 2    | dense-only       | on       |
| 3    | hybrid + bm25    | off      |
| 4    | hybrid + bm25    | on       |
| (5)  | hybrid + native  | on       | *(only if available)*

---

## Step 6: Interpret the results

Expected shape:

```
                        Rare-term        Semantic         Mixed       Latency
                        ────────────     ────────────     ───────     ──────────
Mode \ Reranker         Hit@1   MRR     Hit@1   MRR      Hit@1       P95 ms

dense-only / off         42%    0.51    78%    0.85      80%           48
dense-only / on          58%    0.65    78%    0.85      80%          425
hybrid_bm25 / off        85%    0.88    72%    0.81      82%           62
hybrid_bm25 / on         95%    0.96    78%    0.85      85%          485
```

Key questions:

1. **Colosseum**: did the named case hit top-1 under any hybrid cell?
   This is the regression target — if no cell hits it, hybrid did not
   solve the documented failure mode.
2. **Rare-term partition**: did hybrid Hit@1 lift by ≥ 10 pp vs
   dense-only with the **same** reranker setting? (Rerank-on vs
   rerank-on, rerank-off vs rerank-off.)
3. **Semantic partition**: did hybrid Hit@1 stay within −2 pp of
   dense-only on the same reranker setting?
4. **Mixed partition**: did hybrid Hit@1 stay ≥ dense-only? (Should
   be a non-event.)
5. **Latency**: did hybrid + rerank P95 stay under 1.5 × dense-only +
   rerank P95?
6. **Fusion contribution**: in the per-query JSON, look at `dense_rank`
   vs `sparse_rank` for the gold chunk. If the gold chunk's
   `sparse_rank` is consistently ≤ 5 while `dense_rank` is huge, that
   confirms BM25 is doing the work on rare-term queries.

---

## Success Criteria

| Check                                                | Pass condition                                                                    |
| ---------------------------------------------------- | --------------------------------------------------------------------------------- |
| Colosseum named case                                 | At least one hybrid cell returns the Colosseum chunk at top-1                     |
| Rare-term improvement                                | hybrid (rerank-on) Hit@1 (rare-term) ≥ dense-only (rerank-on) Hit@1 (rare-term) + 10 pp |
| Semantic non-regression                              | hybrid (rerank-on) Hit@1 (semantic) ≥ dense-only (rerank-on) Hit@1 (semantic) − 2 pp |
| Mixed non-regression                                 | hybrid (rerank-on) Hit@1 (mixed) ≥ dense-only (rerank-on) Hit@1 (mixed)            |
| Latency budget                                       | hybrid (rerank-on) P95 ≤ 1.5 × dense-only (rerank-on) P95                          |
| Calibrated `÷30` scaling unchanged                   | Same code path, same threshold scaling, no recalibration needed                    |
| Decision recorded                                    | `results.md` ends with a clear recommendation for `HYBRID_ENABLED` default flip   |

If **all five** primary criteria hold → recommend a follow-up change to
flip `HYBRID_ENABLED=true` by default. If criteria 1–4 hold but
latency criterion fails → recommend keeping `HYBRID_ENABLED=false` as
default but documenting hybrid as a recommended opt-in. If rare-term
fails to improve → record the negative result and keep the feature
opt-in only.

---

## What to do if the experiment fails

**Colosseum does not hit:**

1. Inspect the per-query JSON. Was the Colosseum chunk in the BM25
   ranking? If yes, RRF fusion may be miscalculated. Check Tier 3
   tasks 5.1–5.5 (RRF unit tests).
2. Was the Colosseum chunk absent from BM25? Then BM25 tokenisation
   is dropping it (likely a stop-word issue or unexpected lowercasing).
3. Loop back to Tier 3 task 2.3 (tokeniser) and re-run.

**Rare-term improvement < 10 pp:**

1. Inspect failing rare-term queries. If BM25 ranks the gold chunk in
   top-5 but RRF still doesn't land top-1, the dense ranker is
   actively ranking *wrong* chunks above the gold chunk. RRF can't
   help if both rankers have the gold chunk ≥ rank 5.
2. Check `RERANK_MAX_FETCH` from Exp 5 — too small a pool defeats the
   point of fusion.
3. If genuinely insufficient, expand the rare-term pack with more
   targeted documents and re-run. (Underpowered query partition is a
   common cause of weak results.)

**Semantic regression > 2 pp:**

1. RRF may be polluting good dense rankings with poor BM25 rankings.
   Inspect a regressing query: did BM25 inject an unrelated
   high-keyword-overlap chunk into the top of the fused list?
2. This is real. Document and consider lowering BM25's RRF weight via
   a follow-up experiment (the design rejected weighted convex
   combination but a `weight_dense=2.0, weight_sparse=1.0` RRF
   variant might be needed).

**Latency > 1.5 × baseline:**

1. Confirm BM25 index is being cached (Tier 3 task 3.x). If every
   query rebuilds the index, latency will be terrible on the first
   query of every test run. Check `cache_info` equivalent for the
   `BM25SparseRetriever`.
2. Confirm dense and sparse retrievers run concurrently (Tier 3 task
   6.2 — `asyncio.gather`), not sequentially.
3. Lower the reranker pool from Exp 5 if the bottleneck is rerank
   latency at the new larger fused pool.

---

## Cleanup

```bash
rm -rf ./chroma_dense ./chroma_hybrid_bm25 ./chroma_hybrid_native
```

---

## References

- `openspec/changes/rag-hybrid-retrieval/design.md` — Decisions 1–8
- `openspec/changes/rag-hybrid-retrieval/tasks.md` — task 9.x (this experiment), 5.x (RRF), 3.x (BM25 cache)
- `experiments/1-reranker-threshold-calibration-2026-05-12/results.md` —
  Colosseum failure case, original score 0.015
- `experiments/5-reranker-pool-sizing-2026-05-27/` — provides the
  reranker pool defaults this experiment uses
- Cormack, G.V., Clarke, C.L.A. & Buettcher, S. (2009). *Reciprocal
  rank fusion outperforms Condorcet and individual rank learning
  methods*. SIGIR.
- Mala, S., Gezici, B. & Giannotti, F. (2025). *Weighted RRF on
  HaluBench*.
- Airy, R. & Baranwal, A. (2025). *Hybrid RAG hallucination reduction*.
- Akarsu, M. et al. (2026). *BM25 vs dense retrieval on financial
  documents*.
- Abirami, S. et al. (2025). *Hybrid RRF lifts Recall@100 to 0.997*.
- `rank_bm25` library: https://github.com/dorianbrown/rank_bm25

---

## Artefacts

| File                       | Description                                                                  |
| -------------------------- | ---------------------------------------------------------------------------- |
| `protocol.md`              | This file — hypothesis, method, reproduction steps                           |
| `corpus/exp1-fixtures/`    | Copies of Exp 1 fixtures (Colosseum continuity)                              |
| `corpus/rare-term-pack/`   | 5–10 docs with exact-match identifiers (product codes, gene names, etc.)     |
| `corpus/semantic-pack/`    | 5 docs where queries diverge from chunk wording                              |
| `ground-truth.json`        | 18–25 pre-written queries, partitioned by category, named regression cases   |
| `questions.md`             | Human-readable companion to `ground-truth.json`                              |
| `run_eval.py`              | Cell runner (mode × reranker cross-product)                                  |
| `eval_results.json`        | Per-query results with fusion source ranks (dense / sparse / fused)          |
| `results.md`               | Comparison tables, named-case results, recommendation for default flip       |
