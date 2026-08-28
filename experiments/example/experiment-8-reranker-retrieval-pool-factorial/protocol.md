# Experiment 8 — Reranker × retrieval mode × candidate-pool factorial

**Template ID:** `example/experiment-8-reranker-retrieval-pool-factorial`  
**Status:** PLANNED  
**Role:** repaired large calibration replacing/superseding overlapping 9a-rerun + 10b and providing the Exp 12 reranker-off hybrid contrast

## 1. Research question

On the frozen FreshStack technical workload, what are the independent/interactive effects of retrieval mode (dense vs BM25 hybrid), reranking, and reranker candidate-pool size on retrieval quality and latency? In particular:

1. is reranking still harmful at the current post-ADR-021 effective pool of 150?;
2. does pool size causally change the reranker conclusion?;
3. with reranking off, is BM25 hybrid materially better than dense-only and therefore a candidate for default promotion?

## 2. Pre-registered hypotheses and primary contrasts

### Reranker policy

- **H1a — current dense policy:** at `fetch_k=150`, reranker-on does not improve Coverage@20 over dense reranker-off by the practical promotion margin (pre-register margin; suggested +1pp for “worth routing” and report CI).
- **H1b — current hybrid policy:** same contrast for hybrid BM25.
- **H2 — reranker-off ceiling:** if the best reranker-on pool does not exceed reranker-off by the pre-registered practical margin, keep reranker off for this workload.

### Pool-size causality

- **H3 — pool sensitivity:** for reranker-on hybrid, Coverage@20(500) - Coverage@20(50) is at least 3pp if candidate-pool size materially matters (legacy 10b question).
- **H4 — diminishing returns:** Coverage@20(500) - Coverage@20(200) <= 2pp supports a ~200 upper practical pool.

### Hybrid default contrast

- **H5 — hybrid reranker-off lift:** Coverage@20(hybrid_off) - Coverage@20(dense_off) >= 3pp, semantic/non-technical guardrail does not regress >2pp where such a labelled subset exists, and paired 95% bootstrap CI excludes zero.

These are pre-registered contrasts; do not choose a different “primary” contrast after seeing results.

## 3. Experimental unit

Primary unit: one labelled FreshStack query evaluated in every applicable cell. This is a repeated-measures/paired design.

Use the same frozen full corpus and exact query/qrel set for all cells. Retrieval-only treatments reuse one immutable index because retrieval mode/reranker/fetch_k do not change embeddings or indexed text.

## 4. Manipulated / independent variables

Factor A — retrieval mode:
- `dense`
- `hybrid_bm25`

Factor B — reranker:
- `off`
- `on`

Factor C — `fetch_k`, **nested within reranker=on**:
- 50
- 100
- 150 (current post-ADR-021 production-equivalent at top_k=50)
- 200
- 500

`fetch_k` has no meaningful level when reranker is off; do not duplicate the same off control five times.

## 5. Controlled variables

- repository commit / dependency lock;
- corpus bytes and preparation seed;
- query/qrel set and query order;
- embedding provider/model and query embedder identity;
- immutable vector index;
- vector-store backend/mode;
- sparse backend fixed to BM25 (no native sparse);
- reranker model/backend/device fixed for the **quality** campaign;
- top_k=50 for experiment-scale metrics unless protocol is amended before execution;
- RRF k;
- similarity threshold = 0.0 for the quality comparison to avoid threshold-policy confounding;
- metadata filters absent unless the entire experiment explicitly studies one;
- no query-policy auto rerank: cells set rerank explicitly because rerank itself is a manipulated factor.

If Torch/MPS is used to reduce compute time, it becomes part of the frozen experiment implementation and MUST be justified by Experiment 5 parity; do not mix ONNX and Torch cells inside this quality factorial.

## 6. Blocking / stratification variables

Pre-register query strata available in ground truth, e.g.:

- identifier-heavy/technical;
- less-technical/semantic-like subset if valid labels exist;
- query category/topic.

Every stratum contains exactly the same queries across treatment cells.

## 7. Dependent variables

### Primary quality

- Coverage@20.

### Secondary quality

- Recall@50;
- alpha-nDCG@10;
- Hit@5/10;
- MRR@10;
- per-stratum Coverage@20.

### Systems

- per-query latency;
- P50/P95 by cell;
- reranker invocation success/backend/device from runtime manifest.

Latency is analysed separately from quality. One deterministic quality pass per query/cell is sufficient if retrieval/reranker outputs are deterministic; use a smaller stratified performance subset with repetitions for stable latency rather than rerunning all quality cells unnecessarily.

## 8. Cell matrix

### Shared controls

| Cell | Retrieval | Rerank | fetch_k |
|---|---|---|---|
| D0 | dense | off | n/a |
| H0 | hybrid_bm25 | off | n/a |

### Reranker-on treatments

| Cell family | Retrieval | Rerank | fetch_k |
|---|---|---|---|
| D50/D100/D150/D200/D500 | dense | on | 50/100/150/200/500 |
| H50/H100/H150/H200/H500 | hybrid_bm25 | on | 50/100/150/200/500 |

Total: **12 quality cells**, not 20 duplicated controls.

## 9. Corpus / query / qrel identity

Freeze and hash:

- FreshStack corpus manifest and generated source version;
- immutable index collection identity;
- exact ordered query list;
- qrels/nugget labels;
- any technical/semantic strata labels.

Ground truth must predate this run. Do not relabel queries based on retrieved outputs.

## 10. Randomisation / counterbalancing

### Quality

Because each query is evaluated in every cell, use a deterministic counterbalanced cell order rather than always D0 -> ... -> H500. A simple rotated/Latin-square schedule keyed by query index is acceptable. This reduces time/thermal/cache ordering correlations while preserving paired data.

### Performance subset

Use fresh or well-controlled process state per repetition where backend global state matters. Rotate cell order across repetitions.

## 11. Repetitions and warm-up

Quality: one measured pass per query/cell after preflight; rerun only invalid/interrupted query rows using checkpoint identity.  
Latency subset: one warm-up per cell/process + >=3 measured repetitions on a fixed stratified subset; report raw reps.

## 12. Preflight assertions

Before any measured query:

- corpus/query/qrel/index checksums match plan;
- effective embed model matches index identity;
- effective vector store/mode constant;
- effective sparse backend == BM25 in hybrid cells;
- effective reranker backend/model/device constant across all rerank-on cells;
- no reranker fallback;
- resolved fetch_k values for 50/100/150/200/500 are exactly those values (subject only to collection-size clamp, which MUST not collapse them on this corpus);
- D0/H0 do not invoke reranker;
- quality threshold is 0.0;
- runner-generated cells exactly equal the 12 declared cells.

## 13. Abort / invalid-cell criteria

- any fetch pool collapses to another effective value;
- reranker falls back or changes backend/device between quality cells;
- BM25 cache/index is contaminated by another store/index identity;
- query/corpus/qrel checksum changes;
- cell matrix differs from plan;
- cell/query execution is interrupted before raw row is durably checkpointed -> mark row/cell incomplete, not a zero metric.

## 14. Success / decision gates

Primary decisions use **paired per-query deltas** and 95% bootstrap CIs.

- H1 current-policy: report D150-D0 and H150-H0. A positive point estimate whose CI spans zero is not evidence for enabling reranking.
- H2 best reranker: select best pool only for the pre-registered “best-vs-off” secondary contrast; report optimism risk rather than pretending it was a priori.
- H3: H500-H50 >=3pp Coverage@20 and report CI.
- H4: H500-H200 <=2pp; if using an equivalence claim, pre-register an equivalence interval and calculate accordingly.
- H5: H0-D0 >=3pp, semantic guardrail >=-2pp, paired 95% CI excludes zero, and no secondary metric regresses >5pp.

## 15. Analysis plan

1. validate all cells/manifests;
2. compute raw per-query metrics;
3. compute paired primary contrasts H1/H3/H5;
4. bootstrap queries (not aggregate cell means) with a fixed seed, >=10,000 resamples suggested;
5. report strata without using post-hoc strata to redefine the global conclusion;
6. plot Coverage@20 and latency vs fetch_k separately for dense/hybrid reranker-on;
7. report reranker-off controls as horizontal references;
8. keep quality and latency conclusions separate.

## 16. Threats to validity

- one technical corpus may not generalise to academic/document retrieval;
- candidate-pool “best” is selected from multiple levels and is exploratory unless separately confirmed;
- reranker backend precision may affect quality; freeze one backend for this campaign;
- hardware variability matters for latency but not deterministic quality if execution is valid.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/build_indexes.py
uv run python experiments/<promoted-dir>/run_eval.py --resume
uv run python experiments/<promoted-dir>/summarise_eval.py
```

## 18. Required raw artefacts

- protocol + machine-readable 12-cell plan;
- corpus/query/qrel/index hashes;
- runtime manifest per cell (and changes if any);
- per-query raw metrics/results;
- checkpoint rows;
- paired bootstrap output;
- latency subset raw repetitions;
- results.md with H1-H5 tables.

## 19. Interpretation rules

- reranker harmful/neutral at all pools -> keep rerank off; skip threshold routing experiment unless another workload shows benefit.
- current 150 harmful but another pool materially beneficial -> ADR-019/pool policy needs a separate reviewed decision.
- H5 passes -> hybrid default promotion becomes an ADR/OpenSpec candidate; this experiment does not flip the default itself.
- H5 fails -> keep dense default irrespective of interesting reranker interactions.
- invalid runtime cell -> repair/rerun; never average it away.

## 20. Cleanup

Keep raw results/manifests. Delete only generated indexes that can be reproduced from the committed immutable identity metadata.
