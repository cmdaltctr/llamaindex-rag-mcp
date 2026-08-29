# Experiment 19: Native FTS vs BM25 sparse backend

**Number:** 19
**Slug:** `19-native-fts-vs-bm25-sparse-2026-08-29`
**Status:** FAIL (G3 latency; G1 quality parity, G2 determinism, G4 memory pass) — decision: **KEEP `bm25` DEFAULT**. See [results.md](./results.md).
**Operator:** @a-build agent (session 2026-08-29), for OpenSpec change
`implement-native-sparse-backend-strategy` (task 4.1)
**Question owner:** Dr Muhammad Aizat Bin Md Hawari

## Motivation

Archived Stage 6 records D17 as complete: hybrid beats dense with
reranking disabled on this corpus family. That justifies hybrid's
existence — NOT native FTS over the in-memory BM25 sparse backend.
`implement-native-sparse-backend-strategy` ships both backends behind
one registry with the default pinned to `bm25`. This experiment is
the comparative evidence the change requires before any default
promotion is even discussable.

## Question

On a representative mixed corpus (rare-term / semantic / general),
does the LanceDB native FTS sparse backend (`native`) match or beat
the in-memory BM25 backend (`bm25`) on ranking quality, and what are
the latency, determinism, and memory trade-offs?

**Decision this informs:** whether `RETRIEVAL__HYBRID_SPARSE_BACKEND`
should ever move off `bm25` (default promotion requires explicit
user sign-off IN ADDITION to this evidence).

## Design

Single variable: the sparse backend (`bm25` | `native`). Everything
else is held constant — same store instance type (LanceDB, one
pre-built index), same corpus, same embedding model for the dense
side (Ollama `qwen3-embedding:0.6b`), same RRF k (60), reranker off,
same ground truth (Experiment 9's 20-query set and corpus packs,
which were designed for exactly this kind of sparse evaluation).

Cells (each runs in its own subprocess for cache and RSS isolation):

| Cell    | Sparse-only ranking | Hybrid fused ranking | Cold pass | Warm passes | Determinism |
| ------- | ------------------- | -------------------- | --------- | ----------- | ----------- |
| `bm25`  | `BM25SparseRetriever` | `search(hybrid=True, backend=bm25)` | timed (incl. BM25 cache build) | 2× timed | pass 2 vs pass 3 |
| `native`| `NativeSparseRetriever` | `search(hybrid=True, backend=native)` | timed (incl. FTS create + refresh) | 2× timed | pass 2 vs pass 3 |

### Corpus

Reused verbatim from Experiment 9 (committed):
`experiments/9-hybrid-retrieval-2026-05-27/corpus/` — exp1 fixtures
(5 docs, Colosseum continuity), rare-term pack (exact-match
identifiers), semantic pack (paraphrase negative control).
Ground truth: Experiment 9's `ground-truth.json` (20 queries:
9 rare-term incl. 3 named cases, 6 semantic, 5 mixed).

### Metrics

- **Quality (sparse-only and hybrid-fused):** Recall@5, Recall@10,
  MRR@10 — overall and per category (rare-term / semantic / mixed).
- **Latency:** per-query wall-clock; cold pass (first query set,
  includes index construction/refresh) and warm passes (steady
  state); report p50/p95 per backend.
- **Determinism:** identical doc-id rank sequences between warm pass
  2 and pass 3 for every query (exact match required).
- **Memory:** peak process RSS (`ru_maxrss`) per cell subprocess
  after loading the store and running all passes; plus in-process
  `tracemalloc` peak around the first (index-building) query.

## Pass gates (written before running)

- **G1 (quality floor):** native sparse-only Recall@10 ≥ BM25
  sparse-only Recall@10 − 2 percentage points.
- **G2 (determinism):** zero ordering mismatches between repeated
  warm passes for BOTH backends.
- **G3 (latency budget, informational):** native warm p50 ≤ 10× BM25
  warm p50. Exceeding it records a FAIL against promotion but does
  not fail the change (the default stays `bm25` regardless).
- **G4 (memory budget):** native cell peak RSS ≤ BM25 cell peak RSS
  × 1.10 (BM25 retains the tokenised corpus in-process; native's index
  is on-disk — a ≤10% overhead is the tolerated ceiling).

## Promotion rule (pre-registered)

Default promotion away from `bm25` requires ALL of: native wins
sparse-only Recall@10 by ≥ 2 pp, G2–G4 pass, AND explicit user
sign-off. Otherwise the default stays `bm25` and this experiment is
recorded as the standing evidence.

## Reproduction

```bash
# 1. Build the store (real Ollama embeddings; Ollama must be up)
uv run python experiments/19-native-fts-vs-bm25-sparse-2026-08-29/build_index.py

# 2. Run both cells (isolated subprocesses)
uv run python experiments/19-native-fts-vs-bm25-sparse-2026-08-29/run_eval.py --cell bm25
uv run python experiments/19-native-fts-vs-bm25-sparse-2026-08-29/run_eval.py --cell native

# 3. Aggregate + gates + results.md
uv run python experiments/19-native-fts-vs-bm25-sparse-2026-08-29/summarise_eval.py
```

Cleanup: `output/lancedb/` (the experiment store) is disposable;
raw cell JSON and results.md are kept.

## Threats to validity

- Corpus scale is small (tens of documents); BM25's in-memory
  advantage grows with corpus size while native FTS amortises its
  disk index — recorded as a scale caveat, not measured.
- The dense side is constant across cells by construction, so hybrid
  deltas are attributable to the sparse ranking alone.
- Latency on one machine (Apple Silicon) — relative comparison only.
