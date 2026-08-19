# Experiment 5 results — reranker backend and execution-device parity

**Experiment ID:** `5-reranker-backend-device-parity` (protocol v1.0)  
**Run date:** 2026-08-19 · **Measured campaign, single quiet pass, machine reserved**  
**Repo commit (recorded in every manifest):** `4c29377c6ea3989d69eea439cf47d666368d0593`  
**Dependency lock hash:** `3a225230a6ebe0f7513a4b4191b6158e1435135158a22ee4a63844cec4c5f77d` (torch extra installed in `.venv`; `pyproject.toml`/`uv.lock` unchanged)  
**Workload identity:** `sha256:bb412ddcd1e3c855a6bd78e06e61ff6a5bf72592a1566602c3b769524d06e1dc` (24 queries × 50 candidates; 8 wide / 8 medium / 8 near-tie)  
**Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2`, ONNX variant `onnx/model_qint8_arm64.onnx`, cached, `HF_HUB_OFFLINE=1`

## Campaign shape

12 children (4 cells × 3 repetitions), fresh process each, counterbalanced
rotation (rep 0 starts `onnx_cpu`, rep 1 `onnx_coreml`, rep 2 `torch_cpu`).
Per child: untimed load + D14 preflight, 1 untimed warm-up pass, 5 measured
passes. 1,728 per-query rows total (12 × 144); 360 measured rows per cell.
All 12 children status `complete`; no invalid or incomplete cells; no
production fallback fired in any measured pass.

## Effective route proof (per child, from the D13 manifest)

| Cell | Rep | Effective route (manifest evidence) | Cold start s | Peak RSS MiB |
|---|---|---|---|---|
| onnx_cpu | 0/1/2 | providers `["CPUExecutionProvider"]`, variant `model_qint8_arm64.onnx` | 0.295 / 0.266 / 0.267 | 259.2 / 268.2 / 265.2 |
| onnx_coreml | 0/1/2 | providers `["CoreMLExecutionProvider", "CPUExecutionProvider"]` — CoreML first | 1.228 / 1.141 / 1.170 | 5560.9 / 5588.6 / 5549.9 |
| torch_cpu | 0/1/2 | `last_loaded_device = cpu`, predict batch 32 | 25.294 / 3.102 / 3.044 | 778.6 / 740.5 / 742.7 |
| torch_mps | 0/1/2 | `last_loaded_device = mps:0`, predict batch 32, MPS alloc 86.7 MiB | 3.907 / 3.717 / 3.829 | 635.6 / 629.8 / 632.4 |

Note: `torch_cpu` rep 0 cold start (25.3 s) paid the session's first
`torch` + `sentence-transformers` import. No gate consumes it: H3 uses
`torch_mps` cold starts, H2 uses steady-state latency after warm-up.

## Steady-state latency (measured rows only, warm-up excluded)

| Cell | n | Median ms | P95 ms |
|---|---|---|---|
| onnx_cpu | 360 | 68.45 | 145.54 |
| onnx_coreml | 360 | 440.44 | 1067.95 |
| torch_cpu | 360 | 58.72 | 114.87 |
| torch_mps | 360 | 39.74 | 60.33 |

## Hypothesis verdicts

### H1 — Torch device parity: PASS
360/360 paired passes (query × repetition × pass) ranking-identical
between `torch_cpu` and `torch_mps`; max absolute per-candidate score
delta **4.02e-07** ≤ 1e-4 tolerance.

### H2 — MPS speed: PASS
Median `torch_mps` 39.744 ms ≤ 0.8 × median `torch_cpu` 58.717 ms:
ratio **0.677**. Paired bootstrap 95% CI of (MPS − CPU) per-query
latency: [−27.047, −23.979] ms (n = 360, seed 20260819) — interval
entirely below zero.

### H3 — Operational bound: FAIL (measured, not inconclusive)
- Peak RSS: `torch_mps` max 666.5 MiB vs `onnx_cpu` max 281.2 MiB →
  ratio **2.370** > 2.0 gate.
- Cold start: `torch_mps` mean 3.818 s vs `onnx_cpu` mean 0.276 s →
  ratio **13.826** > 3.0 gate. The torch stack imports
  `torch` + `sentence-transformers` (~3.5 s) where ONNX Runtime imports
  in ~0.3 s; this is the real production trade the gate measures.

Protocol §19 rule applied: keep the correctness findings (H1, H2, H5),
do **not** recommend `torch_mps` as a default execution route under the
pre-registered resource bounds.

### H4 — Backend attribution: APPLIED
`onnx_cpu` vs `torch_cpu`: max score delta **0.050791**, ranking
disagreement on 360/360 passes (int8-quantised ONNX vs fp32 Torch — the
expected backend/precision divergence). All 360 disagreements
cross-checked against the `torch_cpu` vs `torch_mps` comparison first;
that comparison had **zero** disagreements (H1), so every ONNX-vs-Torch
disagreement is classified `backend_or_precision_divergence`. None is
attributable to MPS.

### H5 — Manifest truth: PASS
All 12 completed children proved their effective provider/device in the
manifest before any timing (`onnx_effective_providers` first-position
match for ONNX cells; `torch_effective_device` prefix match for torch
cells), recorded by the preflight that ran ahead of the measured region.

## Interpretation (protocol §19)

- B == C and C faster → MPS is a valid Torch execution acceleration for
  this workload (H1 + H2).
- A differs from B while B == C → the ONNX/Torch gap (max delta 0.051,
  360/360 ranking disagreements) is backend/quantisation divergence,
  not an MPS defect.
- Resource gate fails → do not promote `torch_mps` (or the torch
  backend generally) to the default route; the production default
  (ONNX CPU) stays.
- Optional `onnx_coreml` cell: no silent CPU-only fallback (provider
  proof on every repetition), but ~5.5 GiB peak RSS and 440 ms median
  latency (6.4× `onnx_cpu`) for this dynamic-shape cross-encoder
  workload. Consistent with ADR-029's caution; not a promotion
  candidate on this evidence.

## Raw artefacts (TDR-014, all committable)

- `output/children/<cell>__rep<N>.json` — 12 child results: full D13
  manifest + 144 per-query rows each (scores, rankings, latency, phase)
- `output/raw_rows.jsonl` — 1,728 per-query rows
- `output/eval_results.json` — campaign result with cell records
- `output/eval_results_checkpoint.json` — resume checkpoint (atomic
  `.tmp` → rename after every child)
- `output/eval_results.summary.json` — H1–H5 machine-readable summary
- `output/preflight_dryrun/` — Wave-1 untimed preflight dry-run
  artefacts (preparation evidence, kept)

## Judgement calls

1. H3 verdict recorded as FAIL with exact ratios; no gate was relaxed
   after the fact.
2. The `torch_cpu` rep-0 cold-start outlier is reported, not trimmed;
   no gate consumes it.
3. `mps_allocated_bytes` (86.7 MiB, MPS allocator) is recorded per
   torch_mps child alongside peak RSS (unified-memory process metric).
