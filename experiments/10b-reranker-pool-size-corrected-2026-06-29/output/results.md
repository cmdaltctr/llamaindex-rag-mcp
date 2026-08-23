# Experiment 10b v2 Results: combined D17 factorial

All contrasts are paired by query_id on Coverage@20 with a 95%
bootstrap CI (10,000 resamples, seed 20260819). Warm-up rows are
excluded from every aggregate.

## Contrasts

| Hypothesis | A | B | Delta | CI low | CI high | n |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| H1a | dense_on_150 | dense_off | -0.0996 | -0.1483 | -0.0507 | 223 |
| H1b | hybrid_on_150 | hybrid_off | -0.1346 | -0.1865 | -0.0821 | 223 |
| H2_dense_best_vs_off (post-hoc pool) | dense_on_50 | dense_off | -0.0327 | -0.0714 | 0.0069 | 223 |
| H2_hybrid_best_vs_off (post-hoc pool) | hybrid_on_50 | hybrid_off | -0.0783 | -0.1142 | -0.0436 | 223 |
| H3 | hybrid_on_500 | hybrid_on_50 | -0.1380 | -0.1836 | -0.0924 | 223 |
| H4 | hybrid_on_500 | hybrid_on_200 | -0.0551 | -0.0858 | -0.0263 | 223 |
| H5 | hybrid_off | dense_off | 0.0457 | 0.0107 | 0.0811 | 223 |

## Per-cell aggregates (measured rows only)

| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | Mean ms | P95 ms | n |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dense_off | 0.6931 | 0.5178 | 0.3871 | 0.7758 | 0.5101 | 288.4 | 602.0 | 223 |
| dense_on_100 | 0.6215 | 0.4412 | 0.2918 | 0.6592 | 0.3875 | 3016.7 | 3814.8 | 223 |
| dense_on_150 | 0.5935 | 0.4157 | 0.2779 | 0.6323 | 0.3686 | 5297.4 | 7961.2 | 223 |
| dense_on_200 | 0.5794 | 0.3927 | 0.2805 | 0.6368 | 0.3769 | 5957.6 | 7921.1 | 223 |
| dense_on_50 | 0.6604 | 0.5178 | 0.3085 | 0.6996 | 0.4096 | 1692.4 | 2371.8 | 223 |
| dense_on_500 | 0.5127 | 0.3528 | 0.2593 | 0.5874 | 0.3493 | 12432.6 | 14269.8 | 223 |
| hybrid_off | 0.7388 | 0.5495 | 0.4268 | 0.8117 | 0.5742 | 318.6 | 644.0 | 223 |
| hybrid_on_100 | 0.6354 | 0.4677 | 0.2943 | 0.6726 | 0.3903 | 2768.7 | 3345.3 | 223 |
| hybrid_on_150 | 0.6042 | 0.4304 | 0.2804 | 0.6592 | 0.3667 | 4885.1 | 6882.5 | 223 |
| hybrid_on_200 | 0.5775 | 0.4011 | 0.2735 | 0.6323 | 0.3578 | 6664.6 | 10061.5 | 223 |
| hybrid_on_50 | 0.6605 | 0.5495 | 0.3189 | 0.7085 | 0.4253 | 1570.8 | 1949.1 | 223 |
| hybrid_on_500 | 0.5224 | 0.3538 | 0.2506 | 0.5740 | 0.3342 | 13276.9 | 15514.7 | 223 |

## Interpretation (plain English)

1. **The reranker makes results worse in every configuration tested.** At the
   production pool size (150) it costs about 10–13 coverage points on both
   retrieval modes. Shrinking the pool to 50 softens but does not remove the
   harm on hybrid, and larger pools make it worse, monotonically.
2. **There is no pool size worth calibrating a threshold for on this
   workload.** Task 6.2 (threshold campaign) is therefore skipped as not
   warranted; see the 6.2 disposition in the OpenSpec tasks file and the ÷30
   record under gate 6.GB.2.
3. **Hybrid BM25 beats dense with the reranker off** (H5). This is a new,
   separately-scoped observation — a candidate for a future defaults
   discussion, not adjudicated here.
4. **What this does NOT settle:** whether the reranker helps *semantic*
   workloads (the `documents` profile). This corpus is technical. Task 6.3
   (Qasper PDF A/B) is designated as that setting's first real test; until
   then the documents-profile reranker setting is provisional. See the
   evidence update in ADR-019.
5. **Latency columns are invalid** for the protocol guardrail — the machine
   ran under ambient load (27–43 on 8 cores at launch, easing later). Full
   record: `DEVIATION-2026-08-23-ambient-load.md`. Quality metrics are
   unaffected: rankings are deterministic for a frozen index, fixed query
   set, and ONNX reranker.
