# Experiment 7: Chunk Overlap Sensitivity

**ID**: `chunk-overlap-sensitivity-2026-05-27`
**Date**: 2026-05-27
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent (for automation)
**Status**: PLANNED
**Related OpenSpec change**: `rag-retrieval-quality-improvements` (Tier 2)

---

## What this experiment is for

The Tier 2 OpenSpec change bumps the default `CHUNK_OVERLAP` from 64 to 100.
The justification is the empirical chunking benchmark by Stäbler et al.
(2025), which finds 100-token overlap to be the sweet spot for general
retrieval quality across document types.

The point of this experiment is to confirm the bump is at least as good as
the previous default on **our own corpus**, not just the benchmark corpus.
Storage and embedding cost go up modestly with larger overlap, so we also
record those numbers.

---

## Hypothesis

`CHUNK_OVERLAP=100` matches or beats `CHUNK_OVERLAP=64` on Hit@1 and MRR
against the existing e2e-smoke-test corpus, while keeping total chunk count
within 15 % of the 64 baseline.

---

## Background

Overlap exists to prevent answers being split across chunk boundaries. With
zero overlap, an answer that straddles a chunk break is unrecoverable: half
goes into chunk N, half into chunk N+1, neither chunk contains a complete
answer, and the embedding for each half points away from the query.

With more overlap, you increase the chance that *some* chunk contains the
full answer, but you also pay:

- More chunks per document (storage + embedding wall-clock).
- Some redundancy in the top-K (two near-duplicate chunks compete for slots).

64 was an old default chosen before recent benchmarks. 100 is the value
Stäbler et al. converged on. We sweep four values to bracket the decision:

| Value | Why include it                                                |
| ----- | ------------------------------------------------------------- |
| 32    | Lower-bound stress test — does aggressive trimming hurt?      |
| 64    | Current baseline. Anchors the comparison.                      |
| 100   | Proposed new default (Stäbler et al. 2025 sweet spot).         |
| 128   | Upper-bound stress test — diminishing returns territory.       |

This experiment runs after Tier 2 tasks 3.1–3.3 (the default change and
test). It connects the documentation change to actual numbers from our
corpus.

---

## Variables

| Type        | Variable                          | Values                                              |
| ----------- | --------------------------------- | --------------------------------------------------- |
| Independent | `CHUNK_OVERLAP`                   | 32 / 64 / 100 / 128                                 |
| Dependent   | Hit@1, Hit@3, Hit@5, MRR          | —                                                   |
| Dependent   | Total chunk count                 | Storage proxy                                       |
| Dependent   | Ingest wall-clock (s)             | Embedding cost proxy                                |
| Dependent   | Mean / P95 chunk length           | Sanity                                              |
| Controlled  | Embedding model                   | `qwen3-embedding:0.6b`                              |
| Controlled  | Reranker                          | **Enabled** with Tier 2 `(50, 10)` pool defaults    |
| Controlled  | `CHUNK_SIZE`                      | 512                                                 |
| Controlled  | Similarity threshold              | 0.0 (no filtering, reranker handles precision)      |
| Controlled  | Corpus                            | Reuse `experiments/3-e2e-smoke-test-metadata-2026-05-20/corpus` |
| Controlled  | Queries                           | Reuse the 17 ground-truth queries from Exp 3        |
| Controlled  | Hardware                          | Apple Silicon Mac, 16 GB                            |

> **Why reuse Exp 3's corpus and queries?** Exp 3 already establishes a
> 100% Hit@1 baseline on this corpus with `CHUNK_OVERLAP=64`. We have a
> known anchor. If overlap=100 also reaches 100%, the bump is at minimum
> safe. If overlap=100 beats 64 on harder queries we have not yet
> identified, we may need a harder corpus to see it.

---

## Environment & Prerequisites

| Requirement   | Version / Value                                                    |
| ------------- | ------------------------------------------------------------------ |
| Python        | 3.12                                                               |
| Ollama models | `qwen3-embedding:0.6b`                                             |
| Reranker      | `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX                        |
| Hardware      | Apple Silicon Mac, 16 GB                                           |
| Code branch   | Post-Tier-2 with `RERANK_MAX_FETCH` / `RERANK_FETCH_MULTIPLIER` set per Exp 5 outcome |

```bash
# Verify prerequisites
ollama list   # qwen3-embedding:0.6b
uv sync
```

---

## Step 1: Reuse the Exp 3 corpus and queries

```bash
# Verify the Exp 3 corpus is still present
ls experiments/3-e2e-smoke-test-metadata-2026-05-20/corpus
# Expect 6 files: 4 PDFs + 2 Markdown READMEs.

# Use the same questions
cat experiments/3-e2e-smoke-test-metadata-2026-05-20/questions.md
```

If you no longer have the Exp 3 corpus (e.g. files moved), copy them back
into a local `corpus/` directory or create a symlink:

```bash
ln -s ../3-e2e-smoke-test-metadata-2026-05-20/corpus \
      experiments/7-chunk-overlap-sensitivity-2026-05-27/corpus
```

Do **not** write new queries — that would tangle two variables.

---

## Step 2: Run the sweep

The runner does four ingests, one per overlap value, into four isolated
ChromaDB directories:

```bash
cd experiments/7-chunk-overlap-sensitivity-2026-05-27
uv run python run_eval.py \
  --corpus ../3-e2e-smoke-test-metadata-2026-05-20/corpus \
  --questions ../3-e2e-smoke-test-metadata-2026-05-20/questions.md \
  --overlaps 32,64,100,128
```

The script:

1. For each `overlap` value:
   - Sets `CHUNK_OVERLAP=<value>` in the environment.
   - Creates a fresh ChromaDB at `./chroma_overlap_<value>`.
   - Runs the ingest, capturing wall-clock and chunk count.
   - Runs all 17 queries with reranking enabled.
   - Records Hit@1 / Hit@3 / Hit@5 / MRR.
2. Prints a comparison table.
3. Saves raw results to `eval_results.json`.

Reranker enabled here on purpose: this is the production retrieval path.
We are measuring user-visible retrieval quality, not chunker quality in
isolation (that was Exp 6's role).

---

## Step 3: Interpret the results

```
┌─────────┬───────┬───────┬───────┬───────┬────────┬─────────┐
│ Overlap │ Hit@1 │ Hit@3 │ Hit@5 │  MRR  │ Chunks │ Ingest  │
├─────────┼───────┼───────┼───────┼───────┼────────┼─────────┤
│   32    │ 94.1% │ 100%  │ 100%  │ 0.971 │   195  │  35.2 s │
│   64    │ 100%  │ 100%  │ 100%  │ 1.000 │   210  │  37.8 s │  ← anchor
│  100    │ 100%  │ 100%  │ 100%  │ 1.000 │   228  │  40.4 s │
│  128    │ 100%  │ 100%  │ 100%  │ 1.000 │   240  │  42.5 s │
└─────────┴───────┴───────┴───────┴───────┴────────┴─────────┘
```

Key questions:

1. **Quality non-regression**: 100 ≥ 64 on Hit@1 and MRR?
2. **Storage delta**: chunk-count delta between 100 and 64 within 15 %?
3. **Saturation**: does 128 beat 100? If not, 100 is the right pick.
4. **Lower bound sanity**: does 32 underperform 64? If yes, the overlap
   knob is meaningful for this corpus and the bump is justified.

If everything saturates at 100% Hit@1 from overlap=64 upward (which is
likely on this small corpus), the experiment cannot positively confirm a
benefit — but it can confirm the bump is **safe**, which is the bar Tier 2
needs.

For a stronger result, supplement the 17 easy queries with 5–8 deliberately
harder queries written specifically to probe boundary recovery (paraphrased
queries whose gold answer is known to span a chunk boundary in the
overlap=64 ChromaDB). This is optional and noted in `results.md` if done.

---

## Success Criteria

| Check                                   | Pass condition                                                                |
| --------------------------------------- | ----------------------------------------------------------------------------- |
| Quality non-regression                  | overlap=100 Hit@1 ≥ overlap=64 Hit@1; overlap=100 MRR ≥ overlap=64 MRR        |
| Storage delta acceptable                | overlap=100 chunk count ≤ overlap=64 chunk count × 1.15                       |
| Reranker pool defaults from Exp 5 used  | Run uses the `(RERANK_MAX_FETCH, RERANK_FETCH_MULTIPLIER)` chosen in Exp 5    |
| No saturation paradox                   | If overlap=128 also at 100%, document that the corpus is too easy to discriminate |

---

## What to do if the experiment fails

If overlap=100 underperforms overlap=64:

1. Inspect per-query failures. If just 1–2 queries flip, the result is
   probably noise on a small query set; rerun 3 times and look at the
   average.
2. If 3+ queries flip, the bump is genuinely worse on this corpus. Hold
   `CHUNK_OVERLAP=64` as the default (revert Tier 2 task 3.1) and document
   the corpus-specific result in `results.md`.

If overlap=100 chunk count is more than 15 % above overlap=64:

1. Check whether the corpus has many tiny files (where overlap is a larger
   fraction of the total content). If so, the percentage delta is
   misleading on tiny files; the absolute delta is what matters at scale.
2. If absolute delta is reasonable, document the trade-off and proceed.
3. If absolute delta is large enough to meaningfully affect storage, lower
   the bump (e.g. ship overlap=80 instead of 100).

---

## Cleanup

```bash
rm -rf ./chroma_overlap_*
```

---

## References

- `openspec/changes/rag-retrieval-quality-improvements/design.md` — Decision 3
- `openspec/changes/rag-retrieval-quality-improvements/tasks.md` — tasks 3.1–3.3
- `experiments/3-e2e-smoke-test-metadata-2026-05-20/` — corpus and queries reused
- `experiments/5-reranker-pool-sizing-2026-05-27/` — provides the reranker pool defaults this experiment uses
- Stäbler, F. et al. (2025). *Empirical chunking benchmarks at scale*.

---

## Artefacts

| File                | Description                                                              |
| ------------------- | ------------------------------------------------------------------------ |
| `protocol.md`       | This file — hypothesis, method, reproduction steps                       |
| `run_eval.py`       | Sweep runner across `CHUNK_OVERLAP ∈ {32, 64, 100, 128}`                 |
| `eval_results.json` | Raw per-overlap query results, chunk counts, ingest wall-clock           |
| `results.md`        | Comparison table, decision rationale                                     |
