# Experiment 3 — Hybrid metadata-filter and threshold semantics

**Template ID:** `example/experiment-3-hybrid-filter-and-threshold-semantics`  
**Status:** PLANNED  
**Role:** deterministic hybrid-retrieval correctness gate

## 1. Research question

Does hybrid retrieval enforce the caller's metadata filter on every candidate branch, and are dense similarity thresholds applied only to compatible dense/reranker score kinds rather than directly to RRF scores?

## 2. Pre-registered hypotheses

- **H1 — filter closure:** no final hybrid result violates the metadata filter, even when the forbidden row is the strongest BM25 match.
- **H2 — branch parity:** dense and sparse branches see the same logical eligible set before fusion.
- **H3 — zero-threshold sparse recovery:** at `similarity_threshold=0`, a sparse-only relevant row can participate in RRF.
- **H4 — positive-threshold semantics:** with positive dense similarity threshold and no reranker, sparse-only rows without qualifying dense evidence are excluded; the numeric RRF score is never compared directly with the dense threshold.
- **H5 — reranked semantics:** when reranking succeeds, final thresholding uses reranker score semantics; when reranking fails, the correct pre-rerank rule is restored.

## 3. Experimental unit

One query against a tiny synthetic collection with deliberately engineered dense and keyword rankings.

Construct at least these rows:

- A: allowed metadata, strong dense + weak sparse;
- B: allowed metadata, weak dense + strongest sparse;
- C: forbidden metadata, medium dense + strongest or second-strongest sparse;
- D: allowed metadata, below positive dense threshold but keyword-only recovery candidate;
- E: allowed metadata, strong on both.

Use precomputed embeddings so dense ordering is deterministic.

## 4. Manipulated / independent variables

Factor A — retrieval mode:
- `dense`
- `hybrid_bm25`

Factor B — metadata filter:
- none
- `category=allowed`

Factor C — similarity threshold:
- `0.0`
- one positive canonical dense threshold chosen from the fixture geometry

Factor D — rerank state for targeted threshold checks:
- off
- deterministic fake-success reranker with known scores
- deterministic fake-failure reranker

Do not run a heavy model; use a test double for H5.

## 5. Controlled variables

- same store and collection contents;
- same precomputed embeddings;
- same BM25 tokenizer/settings;
- same query text/vector;
- fixed `rrf_k=60`;
- fixed top_k/fetch_k;
- no native sparse backend;
- deterministic reranker double for H5.

## 6. Blocking / stratification variables

Each filter/threshold condition is a deterministic block. Compare dense and hybrid within the same block.

## 7. Dependent variables

- dense candidate IDs and canonical scores;
- sparse candidate IDs/ranks;
- fused IDs, RRF scores and dense/sparse ranks;
- final returned IDs;
- effective threshold score kind/value;
- filter-violation count;
- reranker fallback reason where applicable.

## 8. Cell matrix

Minimum cells:

| Cell | Mode | Filter | Threshold | Rerank | Purpose |
|---|---|---|---:|---|---|
| 1 | dense | allowed | 0 | off | dense filter control |
| 2 | hybrid | allowed | 0 | off | filter leak test |
| 3 | hybrid | none | 0 | off | sparse recovery control |
| 4 | hybrid | allowed | positive | off | positive-threshold semantics |
| 5 | hybrid | allowed | positive | success fake | reranker score semantics |
| 6 | hybrid | allowed | positive | failing fake | failure fallback semantics |

Additional nested/operator metadata filters may be parameterised over Cells 1-2.

## 9. Corpus / ground truth

Commit a fixture manifest with expected:

- allowed/forbidden metadata membership;
- dense ordering and threshold membership;
- BM25 ordering;
- RRF ordering for `rrf_k=60`;
- fake reranker scores.

The expected RRF values should be analytically calculated in the fixture.

## 10. Randomisation / counterbalancing

None required; this is deterministic correctness testing.

## 11. Repetitions and warm-up

One deterministic run + exact rerun. No latency inference.

## 12. Preflight assertions

- effective sparse backend is BM25;
- store contains exact fixture IDs;
- canonical dense score kind matches plan;
- RRF `k` is 60;
- fake reranker success/failure mode is active in the intended cells.

## 13. Abort / invalid-cell criteria

- native sparse or real reranker is accidentally selected;
- fixture dense ordering does not match the precomputed expectation;
- treatment values differ from the plan.

## 14. Success gates

- H1: **zero** forbidden final results under filtered hybrid cells.
- H2: every sparse candidate entering RRF satisfies the active metadata filter.
- H3: the labelled sparse-only row participates/returns as expected at threshold 0.
- H4: no code path compares the positive dense threshold with `fused_score`; sparse-only below-threshold row is excluded according to the declared semantics.
- H5: successful fake reranker uses its score kind; failing fake reranker returns to the declared pre-rerank rule.

Any failure is a pipeline correctness blocker.

## 15. Analysis plan

Use exact assertions rather than statistical summaries. Save branch-level candidate traces so a leaked row can be attributed to dense, sparse or fusion.

## 16. Threats to validity

- BM25 filtering implementation may be correct but inefficient; performance is explicitly not tested here.
- Fake reranker validates orchestration semantics, not model quality.
- Native sparse requires its own contract experiment after implementation.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/run_eval.py
```

## 18. Required raw artefacts

- fixture manifest;
- branch candidate traces;
- canonical/fused score trace;
- runtime manifest;
- exact assertion summary.

## 19. Interpretation rules

PASS establishes hybrid contract correctness for BM25 on the fixture; it does not justify enabling hybrid by default. FAIL blocks calibration experiments using hybrid.

## 20. Cleanup

Delete temporary fixture store after results are committed.
