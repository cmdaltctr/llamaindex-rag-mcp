# Experiment 5 — Reranker backend and execution-device parity

**Template ID:** `example/experiment-5-reranker-backend-device-parity`  
**Status:** FAIL — measured campaign 2026-08-19; correctness gates H1/H5 PASS, performance H2 PASS and H3 FAIL, H4 applied; H3 does not block Stage 6 correctness work; see section 22 and `results.md`  
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

## 21. Execution preparation (2026-08-19)

Setup only. **No measured cell has been executed**; this section records
preparation artefacts and untimed preflight evidence, not results.

### Artefacts committed beside this protocol

- `workload.json` — fixed workload, 24 queries x 50 candidates
  (8 wide / 8 medium / 8 near-tie per section 6), identity
  `sha256:bb412ddcd1e3c855a6bd78e06e61ff6a5bf72592a1566602c3b769524d06e1dc`
  (255,081 bytes). `make_workload.py --check` proves byte-identical
  regeneration.
- `plan.json` — the four execution-route cells (section 4) as a
  manipulable matrix (factors `backend` x `device` x `onnx_provider`),
  with universal preflight assertions and per-cell route assertions.
- `harness.py` — shared library: cell matrix, workload identity, route
  policy, production-reranker construction, D13 manifest builder, D14
  preflight, D16 pass runner with per-call fallback detection,
  cold-start probe, counterbalancing, atomic writes.
- `child_run.py` — fresh child process per `(cell, repetition)`:
  route environment first, untimed load + preflight, untimed warm-up,
  measured passes, peak RSS / MPS memory, atomic result write.
  `--dry-run` stops after preflight.
- `run_eval.py` — campaign orchestrator: D15 plan agreement,
  counterbalanced order, child spawning, checkpoint (`.tmp` -> rename)
  with `--resume`, cell-record rollup, `raw_rows.jsonl`.
- `summarise_eval.py` — H1-H5 evaluation over complete cells only.
- `tests/test_harness.py` — 17 fast tests (no model load, no network).

### Route-control mechanism (production classes only)

Both production reranker classes are used unmodified. The ONNX route
selects its provider through the production-read
`RERANK_ONNX_PROVIDER` environment variable. The `torch_cpu` cell
hides MPS availability before the model loads, so sentence-transformers'
own `get_device_name()` resolution lands the production
`SentenceTransformerReranker` on CPU and its `last_loaded_device` seam
records the truth; `torch_mps` uses default resolution (MPS) verified
by preflight.

### Untimed preflight dry-run evidence (2026-08-19, this machine)

All four routes loaded the cached `cross-encoder/ms-marco-MiniLM-L-6-v2`
with `HF_HUB_OFFLINE=1` and passed the full D14 preflight: the plan's
universal assertions, `assert_no_fallback`, and the per-cell route
proof (recorded in each child manifest):

| Cell | Effective route evidence |
|---|---|
| onnx_cpu | providers `["CPUExecutionProvider"]`; variant `onnx/model_qint8_arm64.onnx` |
| onnx_coreml | providers `["CoreMLExecutionProvider", "CPUExecutionProvider"]` — CoreML first, no silent CPU-only fallback |
| torch_cpu | `last_loaded_device = cpu` |
| torch_mps | `last_loaded_device = mps:0` |

Dry-run records are honestly `incomplete` ("dry-run preflight only");
`summarise_eval.py` reports every hypothesis `not_evaluable` until the
measured campaign completes.

### Environment note (TDR-014 threat: Torch changes the environment)

The `torch` extra is installed in `.venv` (torch 2.13.0, MPS available)
per user authorisation; `pyproject.toml` and `uv.lock` are unchanged.
Each child manifest records `dependency_lock_hash` plus the effective
route facts, so post-hoc analysis can separate torch-environment runs
from torch-free runs.

### Measured campaign command (for the later quiet run)

```bash
cd experiments/example/experiment-5-reranker-backend-device-parity
uv run --no-sync python run_eval.py --output-dir output          # 4 cells x 3 reps x (1 warmup + 5 measured)
uv run --no-sync python summarise_eval.py --output-dir output    # H1-H5 -> output/eval_results.summary.json
```

`--resume` continues an interrupted campaign without re-running
completed children. Admissible-evidence note: this benchmark is
inference-only, so the embedding / vector-store / sparse /
document-backend manifest sections are null with recorded reasons by
design; the plan's own preflight assertions and route proofs are the
admissibility contract here.

## 22. Execution record (measured campaign, 2026-08-19)

The pre-registered campaign ran as prepared, machine reserved, in one
uninterrupted pass: 12 fresh children (4 cells x 3 repetitions),
counterbalanced order, untimed load + preflight and 1 warm-up pass per
child, 5 measured passes per repetition, `HF_HUB_OFFLINE=1`,
checkpoint after every child. All 12 children completed; no invalid or
incomplete cells; no production fallback fired in any measured pass.
Full numbers: `results.md`; machine-readable artefacts under `output/`.

**Identities (every manifest):** repo commit `4c29377c6ea3989d`,
lock `3a225230a6eb`, workload `sha256:bb412ddc...4d06e1dc`.

**Verdicts (gates exactly as pre-registered in section 14):**

| Hypothesis | Verdict | Key numbers |
|---|---|---|
| H1 device parity | **PASS** | 360/360 ranking-identical; max score delta 4.02e-07 (<= 1e-4) |
| H2 MPS speed | **PASS** | median ratio 0.677 (<= 0.8); bootstrap CI [-27.05, -23.98] ms, n=360 |
| H3 operational bound | **FAIL** | RSS ratio 2.370 (> 2); cold-start ratio 13.826 (> 3) |
| H4 backend attribution | **APPLIED** | 360/360 ONNX-vs-Torch disagreements all `backend_or_precision_divergence` (B-vs-C had zero disagreements); max delta 0.0508 |
| H5 manifest truth | **PASS** | 12/12 children proved effective provider/device before timing |

**Interpretation (section 19 rules):** MPS preserves Torch CPU outputs
and is faster for this workload, but the resource gates fail, so the
torch route is not promoted to default; production stays on the ONNX
CPU path. The optional `onnx_coreml` cell ran without silent fallback
(CoreML provider first on every repetition) at ~5.5 GiB peak RSS and
440 ms median latency — not a promotion candidate on this evidence.

**Artefact policy correction:** the experiment-local `.gitignore` no
longer ignores `output/`; it ignores only `__pycache__/` and `*.tmp`,
and re-includes `output/eval_results.json` and
`output/eval_results_checkpoint.json` (hidden by repository-level name
patterns). Required TDR-014 artefacts are committable without
`git add -f` (verified with `git add --dry-run`). Wave-1 dry-run
artefacts are preserved under `output/preflight_dryrun/`.
