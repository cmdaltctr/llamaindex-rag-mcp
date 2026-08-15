# Experiment 17: Reranker MPS vs ONNX CPU latency

**ID**: `17-reranker-mps-vs-onnx-cpu-2026-08-11`
**Date**: 2026-08-11
**Operator**: Dr Muhammad Aizat Md Hawari with AI build agent
**Status**: FAIL
**Relation**: OpenSpec change `apple-acceleration-for-reranker`; ADR-043; follows Experiment 16

---

## Executive summary

MPS is 4.5x faster than the production ONNX CPU path (54.9 ms vs 245.3 ms P50). It passes every speed and cost gate (H1 to H4). Adoption is blocked by H5: ONNX int8 and torch fp32 produce different document rankings on 2 of 5 queries.

The H5 failure is not an MPS device issue. Torch CPU (17B) and torch MPS (17C) produce identical rankings on all queries. The divergence is between ONNX int8 (`model_qint8_arm64.onnx`) and torch fp32 weights. When documents have sub-1% score margins, the quantization precision difference flips their order.

**Decision: keep ONNX CPU as the default.** The torch backend retains Sentence Transformers' automatic MPS selection for opt-in use (`RETRIEVAL__RERANK_BACKEND=torch`). ADR-043 records the full verdict.

## Preflight (untimed, automatic device selection)

- **Loaded**: True
- **Selected device**: `mps`

## Cell metrics (median of 3 repetitions)

| Cell | Backend | Device | P50 (ms) | P95 (ms) | Cold start (s) | Peak RSS (MB) | MPS current (MB) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 17A | onnx | cpu | 245.3 | 497.9 | 1.4 | 368.6 | — |
| 17B | torch | cpu | 243.3 | 475.9 | 3.7 | 590.5 | — |
| 17C | torch | mps | 54.9 | 193.4 | 3.9 | 568.4 | 86.7 |

## Pass gates

| Gate | Result | Threshold | Raw values |
| --- | :---: | --- | --- |
| H1 | **PASS** | MPS loads, selects MPS, no fallback | loaded=True, device=mps |
| H2 | **PASS** | 17C P50 <= 0.8 x 17B P50 | 54.9 <= 194.6 |
| H3 | **PASS** | 17C P50 <= 0.8 x 17A P50 and P95 <= 17A P95 | 54.9 <= 196.2, 193.4 <= 497.9 |
| H4 | **PASS** | cold <= 3x 17A and RSS <= 2x 17A | 3.9 <= 4.1, 568.4 <= 737.2 |
| H5 | **FAIL** | 17B==17C rankings and 17A==17C rankings | see diagnostic table |
| **Overall** | **FAIL** | All gates required | 4 of 5 pass |

## Per-repetition P50 latencies (ms)

| Repetition | 17A | 17B | 17C |
| ---: | ---: | ---: | ---: |
| 1 | 247.88 | 234.16 | 54.92 |
| 2 | 245.3 | 243.3 | 61.64 |
| 3 | 238.49 | 344.52 | 50.02 |

## Ranking consistency (H5 diagnostic)

| Query | 17A vs 17C | 17B vs 17C |
| ---: | :---: | :---: |
| 1 | DIFFER | match |
| 2 | match | match |
| 3 | match | match |
| 4 | match | match |
| 5 | DIFFER | match |

17B (torch CPU) and 17C (torch MPS) produce identical rankings on all queries. The MPS device does not alter model outputs. The divergence is ONNX int8 vs torch fp32 backend precision.

## Environment

| Item | Value |
| --- | --- |
| Model | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| ONNX variant | `onnx/model_qint8_arm64.onnx` |
| Workload | 5 queries x 20 docs |
| Repetitions | 3 (fresh child process each) |
| Iterations | 5 measured, 1 discarded warm-up |
| Batch size | 32 |
| onnxruntime | 1.28.0 |
| sentence_transformers | 5.7.0 |
| tokenizers | 0.22.2 |
| torch | 2.13.0 |
| chip | Apple M1 Pro |
| machine | arm64 |
| macos_version | 26.5.1 |
| memory_gb | 32 |
| platform | macOS-26.5.1-arm64-arm-64bit |
| python_version | 3.12.10 |

## Test environment note

Installing the `torch` optional extra (`uv sync --extra torch`) to run this experiment causes 2 pre-existing tests in `tests/test_reranker_backend_selection.py` to fail: `test_torch_missing_falls_back_to_onnx` and `test_torch_missing_and_onnx_fails_degrades`.

These tests verify that the backend selector falls back to ONNX when torch is absent. Their source code explicitly states: "No mocking needed — sentence_transformers is not installed in the fast suite, so `_is_torch_extra_available()` naturally returns False." Once torch is installed, the probe returns True and the fallback assertion fails.

These tests pass in CI (which does not install the torch extra) and are unrelated to this experiment's code changes. The experiment runner and gate logic do not modify production code.

## Analysis

### MPS acceleration is real and large

17C (torch MPS) achieves 54.9 ms P50 against 245.3 ms for 17A (ONNX CPU) and 243.3 ms for 17B (torch CPU). That is a 4.5x improvement over the production baseline and a 4.4x improvement over the torch control. P95 also improves: 193.4 ms vs 497.9 ms.

Cold start is 3.9 s (2.9x the 1.4 s ONNX baseline), within the 3x gate. Peak RSS is 568.4 MB (1.5x the 368.6 MB baseline), within the 2x gate.

### Why H5 fails

The two queries where rankings differ involve documents with near-identical relevance scores. The synthetic workload generates documents by repeating seed texts at different lengths, producing many candidates with very similar cross-encoder logits. When the score margin is sub-1%, the int8-to-fp32 precision difference flips the order.

The project's score-parity contract (ADR-038, design decision 7) requires that backends produce comparable scores. While the contract test enforces sigmoid-parity (scores in the same range), the MiniLM workload here shows that int8 quantization can reorder near-tied documents.

## Limitations

- Results apply to Apple M1 Pro (32 GB) with the locked package versions recorded above. Other Apple Silicon generations may differ.
- The synthetic workload amplifies ranking sensitivity: near-identical documents create sub-1% score margins where precision differences flip order. Production corpora with wider score margins may not exhibit H5 failure.
- Three repetitions provide median stability but not statistical power.
- ADR-043 records the bounded decision with re-test conditions.

## Artefacts

| File | Description |
| --- | --- |
| `protocol.md` | Experiment plan with H1 to H5 gates and interpretation rules |
| `workload.json` | Fixed 5-query x 20-document inference workload |
| `run_eval.py` | Coordinator + child-process runner (17A/17B/17C cells) |
| `test_gates.py` | 33 focused tests for gate logic, device assertions, checkpoint resume |
| `summarise_eval.py` | Aggregates JSON into this results.md |
| `analysis.py` | Jupytext percent format: latency and memory plots |
| `output/eval_results.json` | Raw per-cell, per-repetition data |
| `output/eval_results.summary.json` | Gate evaluation summary |
| `output/checkpoint/` | Per-repetition checkpoint files (atomic writes) |
| `output/run_eval.log` | Full run log |

## Cross-references

| Item | Link |
| --- | --- |
| ADR-043 | `docs/adr/043-apple-acceleration-for-the-reranker.md` |
| ADR-038 | `docs/adr/038-pluggable-reranker-backend.md` (torch backend) |
| Experiment 16 | `experiments/16-reranker-coreml-fp16-2026-08-03/` (CoreML evidence) |
| OpenSpec change | `openspec/changes/apple-acceleration-for-reranker/` |
