# Stage 5 component experiments — pre-calibration hardening

Stage 5 executed the seven cheap component protocols in place on 2026-08-19. Each completed cell carries the TDR-014 runtime manifest, preflight evidence, raw rows, and atomic checkpoints required for decision evidence.

## Final status

| # | Experiment | Status | Gate evidence | Results and raw artefacts |
|---|---|---|---|---|
| 1 | `experiment-1-sentencesplitter-vs-codesplitter` | **PASS** | 18/18 code cells used `effective=code`; cut rate 0.233 versus 0.375; zero ceiling violations. Optional H4 arm was not run. | [`results.md`](experiment-1-sentencesplitter-vs-codesplitter/results.md); [`output/summary.json`](experiment-1-sentencesplitter-vs-codesplitter/output/summary.json); [`output/cells/`](experiment-1-sentencesplitter-vs-codesplitter/output/cells/) |
| 2 | `experiment-2-dense-cross-store-score-parity` | **PASS** after a preserved v1.0 **FAIL** | v1.0 found 110/300 H3 threshold mismatches in both stores. Commit `7bf16b3` corrected the shared adapter contract. v1.1 reused the same fixtures and ground truth and recorded 0/300 mismatches. | [`results.md`](experiment-2-dense-cross-store-score-parity/results.md); [`results.summary.json`](experiment-2-dense-cross-store-score-parity/results.summary.json); [`output/v1.1_run1/`](experiment-2-dense-cross-store-score-parity/output/v1.1_run1/) |
| 3 | `experiment-3-hybrid-filter-and-threshold-semantics` | **PASS** | Zero filter leaks; thresholds never used fused RRF scores; reranker success and failure paths preserved compatible score kinds. | [`results.md`](experiment-3-hybrid-filter-and-threshold-semantics/results.md); [`results.raw.json`](experiment-3-hybrid-filter-and-threshold-semantics/results.raw.json); [`output/cells/`](experiment-3-hybrid-filter-and-threshold-semantics/output/cells/) |
| 4 | `experiment-4-bm25-cache-isolation` | **PASS** | Zero cache contamination for both stores in forward and reversed order; all 36 mutations advanced generation exactly once. | [`results.md`](experiment-4-bm25-cache-isolation/results.md); [`output/run1/results.raw.json`](experiment-4-bm25-cache-isolation/output/run1/results.raw.json) |
| 5 | `experiment-5-reranker-backend-device-parity` | **FAIL** on performance H3; correctness gates passed | H1/H5 passed. MPS matched Torch CPU rankings and reached 0.677× median latency. H3 failed at 2.370× RSS and 13.826× cold start, so Torch and CoreML were not promoted. This performance failure does not block Stage 6 correctness work. | [`results.md`](experiment-5-reranker-backend-device-parity/results.md); [`output/eval_results.summary.json`](experiment-5-reranker-backend-device-parity/output/eval_results.summary.json); [`output/raw_rows.jsonl`](experiment-5-reranker-backend-device-parity/output/raw_rows.jsonl) |
| 6 | `experiment-6-ingestion-boundedness-and-atomicity` | **PASS** | H1-H5 passed. Phase B (real Ollama arm) reached 0.911× Experiment 18 Stage 3B, within the frozen 0.9 gate, with zero lock wait and 1.039× RSS. | [`results.md`](experiment-6-ingestion-boundedness-and-atomicity/results.md); [`output/results.raw.json`](experiment-6-ingestion-boundedness-and-atomicity/output/results.raw.json); [`output/results.summary.json`](experiment-6-ingestion-boundedness-and-atomicity/output/results.summary.json) |
| 7 | `experiment-7-metadata-cap-and-granularity` | **PASS** | The cap used exact chunk units; first-N hashes matched; file aggregates persisted on every chunk; call count was `2N+min(5,N)+1`. | [`results.md`](experiment-7-metadata-cap-and-granularity/results.md); [`output/summary.json`](experiment-7-metadata-cap-and-granularity/output/summary.json); [`output/cells/`](experiment-7-metadata-cap-and-granularity/output/cells/) |
| 5b | `5b-persistent-mps-reranker-worker` | **FAIL** on G4 break-even; correctness, speed, memory and lifecycle gates passed | Protocol v1.1 (2026-08-22, Apple Silicon MPS). G1a/G1b/G1c, G2, G3, G5, G6, G7, G8 passed. G4 failed: median break-even N* 156 > 150, one-sided 95 % upper bound 233–∞. G9 failed on a preflight-flag bookkeeping defect with all substantive requirements green. Promotion rejected; ONNX CPU stays the production default. Does not rehabilitate Experiment 5 H3. | [`results.md`](../5b-persistent-mps-reranker-worker-2026-08-20/results.md); [`protocol.md`](../5b-persistent-mps-reranker-worker-2026-08-20/protocol.md); [`output/eval_results.json`](../5b-persistent-mps-reranker-worker-2026-08-20/output/eval_results.json) |

## Experiment 2 defect and repair lineage

The v1.0 execution ran with repo HEAD `c475852` (worktree dirty at the time); its protocol record and raw artefacts are committed as `98449c3`. It failed H3 with 110 mismatches from 300 checks while both stores agreed with each other. The shared result exposed a production contract defect: both adapters passed native squared L2 into a transform documented for true L2.

Commit `7bf16b3` applied the square root at the ChromaDB and LanceDB adapter boundaries. Rankings stayed unchanged. Score magnitudes and threshold membership changed. The v1.1 execution committed at `4c29377` used the unchanged harness and the same pre-registered ground truth. H3 then passed with 0/300 mismatches. See the v1.0 and v1.1 execution records in [`protocol.md`](experiment-2-dense-cross-store-score-parity/protocol.md).

The divide-by-30 reranker threshold was fitted while production emitted the buggy squared-distance score distribution. TDR-015 records the Stage 6 obligation: the ÷30 operating point must be revalidated and numeric thresholds recalibrated before threshold evidence can change production policy.

## Remaining Stage 6 protocols

| # | Protocol | Status | Purpose |
|---|---|---|---|
| 8 | `experiment-8-reranker-retrieval-pool-factorial` | **PLANNED** | Paired reranker, retrieval-mode, and fetch-pool calibration. |
| 9 | `experiment-9-technical-threshold-policy` | **PLANNED** | Conditional technical routing calibration. |
| 10 | `experiment-10-real-pdf-parser-ab` | **PLANNED** | Real-PDF pypdf versus LiteParse comparison. |

Stage 6 has not started.

## Common scientific rules

1. Pre-register hypotheses and gates before measured work.
2. Record requested and effective runtime facts in each manifest.
3. Pair fixed workloads across comparable cells.
4. Keep warm-up rows separate from measured rows.
5. Abort manipulated cells on silent fallback.
6. Store incomplete work as `INCOMPLETE`, without invented numbers.
7. Commit raw rows and immutable content identities.
8. Change production defaults only through a later ADR or OpenSpec.
