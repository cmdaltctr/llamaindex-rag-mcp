# Experiment 9 Results: Hybrid Retrieval Quality

**Date run**: 2026-05-30  
**Operator**: Dr Muhammad Aizat Bin Md Hawari  
**Status**: PARTIAL — implementation works; default-promotion criteria not met.  
**Outcome**: Ship hybrid retrieval as **opt-in only**. Do **not** flip defaults yet.

---

## Summary table

| Config / Category | n | Hit@1 | Hit@5 | MRR@10 | Recall@10 | P95 |
| ----------------- | -: | :---: | :---: | :----: | :-------: | --: |
| **dense-only + rerank** / rare-term | 9 | 100.0% | 100.0% | 1.000 | 100.0% | 1493.8 ms |
| **dense-only + rerank** / semantic | 6 | 83.3% | 100.0% | 0.917 | 100.0% | 1493.8 ms |
| **dense-only + rerank** / mixed | 5 | 100.0% | 100.0% | 1.000 | 100.0% | 1493.8 ms |
| **hybrid BM25 + rerank** / rare-term | 9 | 100.0% | 100.0% | 1.000 | 100.0% | 1314.4 ms |
| **hybrid BM25 + rerank** / semantic | 6 | 83.3% | 100.0% | 0.917 | 100.0% | 1314.4 ms |
| **hybrid BM25 + rerank** / mixed | 5 | 100.0% | 100.0% | 1.000 | 100.0% | 1314.4 ms |
| dense-only, no rerank / rare-term | 9 | 100.0% | 100.0% | 1.000 | 100.0% | 13.7 ms |
| hybrid BM25, no rerank / rare-term | 9 | 100.0% | 100.0% | 1.000 | 100.0% | 11.2 ms |

Named cases:

| Case | Dense-only | Hybrid BM25 | Result |
| ---- | :--------: | :---------: | ------ |
| Colosseum | rank 1 | rank 1 | Hybrid succeeds, but dense already succeeds |
| MCP-1138 BM25-only case | rank 1 | rank 1 | Hybrid succeeds, but dense already succeeds |
| ZZQJ-9097 dense-trap case | rank 1 | rank 1 | Trap did not work; dense still wins |

---

## Pass criteria

| Criterion | Threshold | Measured | Pass |
| :-------- | :-------: | :------: | :--: |
| Colosseum top-1 under hybrid | must pass | rank 1 | ✅ |
| Rare-term Hit@1 lift vs dense-only + rerank | ≥ +10 pp | +0.0 pp | ❌ |
| Semantic Hit@1 regression | no worse than −2 pp | 0.0 pp | ✅ |
| Mixed Hit@1 regression | no worse than 0 pp | 0.0 pp | ✅ |
| Hybrid + rerank P95 latency | ≤ 1.5× dense + rerank | 0.88× | ✅ |

The experiment fails only one criterion: **rare-term lift**.

The reason is simple: **dense-only already scored 100% Hit@1 on rare-term
queries**, so hybrid had no room to improve.

---

## Decision

**Ship hybrid retrieval, but keep it opt-in.**

Do **not** flip:

```env
HYBRID_ENABLED=true
```

Do **not** promote:

```env
HYBRID_SPARSE_BACKEND=auto
```

Keep the defaults as:

```env
HYBRID_ENABLED=false
HYBRID_SPARSE_BACKEND=bm25
```

Rationale:

1. **Implementation works.** The hybrid path runs end-to-end, writes fusion
   diagnostics, and does not regress the tested semantic or mixed queries.
2. **Colosseum is recovered under hybrid.** The named regression case hits rank 1.
3. **But the experiment does not prove a recall lift.** Dense-only already hits
   every rare-term query at rank 1.
4. **The native ChromaDB sparse path is still not validated.** BM25 is the safe
   v1 backend.
5. **Default promotion needs a harder benchmark.** We need a corpus where dense
   retrieval actually misses rare-token chunks before hybrid can prove value.

---

## Why the corpus saturates

The corpus is too small and too easy for this question.

The run indexed only **55 chunks**. With reranking enabled, dense-only uses:

```env
RERANK_MAX_FETCH=50
RERANK_FETCH_MULTIPLIER=10
```

So dense-only + rerank effectively sees almost the whole corpus. That makes the
rare-term task too easy: even if dense retrieval is imperfect, the gold chunk is
still likely to enter the reranker pool.

This is the same kind of ceiling effect seen in earlier experiments:

- Experiment 5: small corpus made every fetch-pool size score 100%.
- Experiment 6: baseline already hit 100%, so markdown chunking could not show lift.

Experiment 9 has the same problem: **baseline saturation**.

---

## What to do next

To properly test hybrid retrieval, rerun Experiment 9 with a larger and harder
corpus:

1. Reuse Experiment 6 or other corpora as **background distractors**.
2. Grow the corpus to at least several hundred chunks, preferably more than 500.
3. Keep `RERANK_MAX_FETCH=50`, so dense-only cannot see almost everything.
4. Add rare-token documents where the natural-language query points to a decoy,
   but the exact identifier points to the gold chunk.
5. Rerun the same grid:

```text
dense-only + rerank
hybrid BM25 + rerank
dense-only without rerank
hybrid BM25 without rerank
```

Only consider flipping `HYBRID_ENABLED=true` if rare-term Hit@1 improves by at
least 10 percentage points without semantic regression.

---

## Reproduction

```bash
EXP9_WARMUP_QUERIES=0   uv run python experiments/9-hybrid-retrieval-2026-05-27/run_eval.py     --modes dense-only,hybrid_bm25     --rerank-cross
```

The run writes raw per-query results to:

```text
experiments/9-hybrid-retrieval-2026-05-27/eval_results.json
```

A console log may also be kept under:

```text
experiments/9-hybrid-retrieval-2026-05-27/output/run_eval_latest.log
```

---

## References

- `protocol.md` — hypothesis, pass criteria, and method.
- `ground-truth.json` — query set and expected sources.
- `eval_results.json` — raw per-query results and aggregate metrics.
- `run_eval.py` — evaluation runner.
- `docs/adr/017-hybrid-retrieval-rrf.md` — architectural decision record.
- `openspec/changes/rag-hybrid-retrieval/tasks.md` — implementation checklist.
