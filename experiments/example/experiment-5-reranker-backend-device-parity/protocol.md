# Experiment 5 — Reranker backend and execution-device parity

**Template ID:** `example/experiment-5-reranker-backend-device-parity`  
**Status:** PLANNED  
**Role:** bounded correctness/performance gate for ONNX vs Torch and CPU vs Apple acceleration

## 1. Research question

Which observed differences come from reranker **backend/precision** and which come from **execution device/provider**? In particular, does Torch MPS preserve Torch CPU outputs while accelerating inference, and how does that compare with the production ONNX path without falsely attributing ONNX-int8 vs Torch-fp32 ranking differences to MPS?

## 2. Pre-registered hypotheses

- **H1 — device parity within Torch:** Torch CPU and Torch MPS produce identical ranking for every fixed query/candidate set and score differences stay within a pre-registered numerical tolerance (default suggestion: absolute score delta <= 1e-4; adjust before running if library precision requires a justified value).
- **H2 — MPS speed:** on Apple Silicon, Torch MPS median steady-state latency is at least 20% lower than Torch CPU for the fixed workload.
- **H3 — operational bound:** MPS peak RSS <= 2x ONNX CPU and cold start <= 3x ONNX CPU unless the protocol is amended before execution.
- **H4 — backend attribution:** any ONNX-vs-Torch ranking difference that also exists between ONNX CPU and Torch CPU is classified as backend/model-precision divergence, not an MPS device divergence.
- **H5 — manifest truth:** every performance cell proves its actual execution device/provider before timing begins.

No hypothesis assumes ONNX and Torch must be score-identical: ONNX quantisation and Torch full precision are explicit backend differences.

## 3. Experimental unit

One fixed query with one fixed ordered candidate document pool presented to the reranker. Use a committed workload large enough to include easy margins and near ties, e.g. 20-50 queries × 50 candidate passages, while remaining a bounded inference-only benchmark.

Candidates are preselected and committed; dense retrieval is not timed.

## 4. Manipulated / independent variables

Nested execution cells:

1. `onnx_cpu` — ONNX backend, CPUExecutionProvider, production variant/precision recorded;
2. `torch_cpu` — Torch backend explicitly forced to CPU, fp precision recorded;
3. `torch_mps` — Torch backend explicitly forced/verified MPS on supported Apple Silicon;
4. optional `onnx_coreml` — only if CoreML is intentionally being re-tested; must be a separate declared cell with actual provider assertion.

Do not call this a complete backend × device factorial because not every backend supports every device identically.

## 5. Controlled variables

- same model ID across cells;
- same tokenizer/max-length policy;
- same query-document pairs in same order;
- same batch size unless batch size itself becomes a separately declared factor;
- same sigmoid normalisation contract;
- same machine, power source and background-load policy for performance comparisons;
- no vector DB, embedding, BM25 or network access during measured inference after models are cached;
- fresh child process per cell/repetition to control backend global state.

## 6. Blocking / stratification variables

Analyse query pools by pre-labelled score-margin class where possible:

- wide-margin/easy;
- medium;
- near-tie/adversarial.

This helps distinguish precision-sensitive reordering from ordinary device divergence.

## 7. Dependent variables

### Correctness/parity

- per-candidate raw/logit-derived score after the shared normalisation;
- ranking IDs;
- Kendall tau/top-k exact overlap;
- maximum absolute Torch CPU vs MPS score delta;
- number of ranking inversions by pair of cells.

### Performance

- cold-start seconds;
- steady-state latency per workload/query batch: median/P50/P95;
- peak RSS;
- MPS allocated/current memory where available;
- effective device/execution provider and model variant.

## 8. Cell matrix

| Cell | Backend | Effective device/provider | Precision | Required? |
|---|---|---|---|---|
| A | ONNX | CPUExecutionProvider | actual selected variant (likely int8 on ARM) | yes |
| B | Torch | CPU | actual dtype | yes |
| C | Torch | MPS | actual dtype | Apple Silicon yes |
| D | ONNX | CoreMLExecutionProvider | actual variant | optional, only if explicitly re-tested |

## 9. Workload identity

Commit the complete query/candidate text workload and SHA-256. Do not regenerate candidates between cells. Include deliberately near-tied examples, but also ordinary natural passages so the workload does not consist only of pathological ties.

## 10. Randomisation / counterbalancing

Use fresh process per `(cell, repetition)`. Counterbalance cell order across repetitions (Latin-square or rotated order) so thermal/cache/time drift does not always favour one backend.

## 11. Repetitions and warm-up

Suggested minimum:

- 3 fresh-process repetitions per cell;
- one untimed model-load/device preflight;
- one untimed inference warm-up inside each child process;
- >=5 measured steady-state passes per repetition.

Increase repetitions if latency variability is high; do not invent precision by averaging interrupted cells.

## 12. Preflight assertions

- model ID identical in A/B/C;
- tokenizer max length identical;
- A reports ONNX CPU provider;
- B reports Torch CPU;
- C reports Torch MPS;
- optional D reports CoreML provider and does not silently fall back to CPU-only;
- selected ONNX variant/precision is recorded;
- no network/model download occurs inside measured region;
- workload checksum identical.

## 13. Abort / invalid-cell criteria

- requested device/provider differs from effective device/provider;
- production graceful fallback occurs in a manipulated cell;
- model/tokenizer differs between cells;
- model download contaminates measured steady-state timing;
- thermal/power event or process failure prevents the declared repetitions from completing -> mark repetition/cell incomplete, not slow.

## 14. Success gates

- H1: 100% Torch CPU/MPS ranking equality + numerical tolerance gate.
- H2: `median_latency_mps <= 0.8 * median_latency_torch_cpu`.
- H3: resource bounds as pre-registered above.
- H4: every ONNX/Torch ranking disagreement is compared against B vs C before attribution.
- H5: every completed cell has valid effective execution fields.

A backend/device may be fast but fail promotion on H1 correctness.

## 15. Analysis plan

Primary correctness comparison: B vs C.  
Backend comparison: A vs B, then A vs C interpreted conditional on B/C parity.  
Use per-query ranking disagreement table and score-margin diagnostics. For latency report raw child-process repetitions, median and P95; avoid significance tests on tiny repetition counts unless increased prospectively.

## 16. Threats to validity

- Apple Silicon generations vary;
- synthetic near ties can overstate quantisation sensitivity;
- installing Torch changes dependency environment, so record a separate lock/environment identity;
- MPS tests GPU acceleration, not Apple Neural Engine; CoreML is a distinct execution route.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/run_eval.py --cells onnx_cpu torch_cpu torch_mps
```

## 18. Required raw artefacts

- fixed workload JSON;
- per-child runtime manifest;
- per-query scores/rankings;
- raw timing/memory repetitions;
- checkpoint files;
- results summary with H1-H5.

## 19. Interpretation rules

- B==C and C faster -> MPS is a valid Torch execution acceleration for this workload.
- B!=C -> do not promote MPS; investigate device numerical behaviour.
- A differs from B and B==C -> classify as backend/precision difference, not MPS defect.
- resource gate fails -> keep correctness finding but do not recommend that execution route as default.

## 20. Cleanup

Keep workload/results; remove only transient process logs/model copies not part of the normal model cache.
