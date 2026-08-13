## Context

See `proposal.md` for the motivation. These constraints shape the experiment:

- ADR-038 added `SentenceTransformerReranker` behind the existing `torch` optional extra.
- The production class constructs `sentence_transformers.CrossEncoder` without a `device` argument.
- Sentence Transformers 5 selects the strongest available device when `device` is omitted. On a compatible Mac, this can select MPS.
- The model cache key is `(backend_name, model_id)`. It has no device axis.
- The ONNX default remains CPU. On Apple ARM, MiniLM prefers `onnx/model_qint8_arm64.onnx`.
- Experiment 16 measured ModernBERT. Its absolute timings cannot serve as the MiniLM baseline.
- Experiment 16 found process-level ONNX Runtime state contamination. Fresh child processes also isolate device memory and peak RSS.

MPS is an Apple framework built on Metal. PyTorch provides the route used by this project.

## Goals / Non-Goals

**Goals:**

- Measure the acceleration from torch CPU to torch MPS.
- Compare torch MPS with the production ONNX CPU path.
- Verify that the optional production torch path selects MPS on the test machine.
- Record a reproducible, hardware-specific verdict in ADR-043.

**Excluded:**

- Runtime code and configuration changes.
- Default backend or model changes.
- CoreML and ModernBERT re-testing.
- Claims about other Apple Silicon generations.

## Decisions

### 1. Use three controlled cells and one untimed production preflight

All cells use `cross-encoder/ms-marco-MiniLM-L-6-v2`, 20 fixed documents, and five fixed queries.

| Cell | Construction | Device | Purpose |
| --- | --- | --- | --- |
| 17A | Production `CrossEncoderReranker` | ONNX CPU | Current project baseline |
| 17B | Experiment adapter around `CrossEncoder` | `device="cpu"` | Torch control |
| 17C | Experiment adapter around `CrossEncoder` | `device="mps"` | MPS candidate |

The torch adapter must match production semantics. It uses the same effective maximum length and batch size. It requests identity activation, converts logits to NumPy, applies the shared sigmoid once, and sorts identically.

An untimed preflight uses `SentenceTransformerReranker` without a device override. It records the selected device and verifies the current automatic path.

Using automatic device selection for both timed torch cells was rejected. Both cells could select MPS and invalidate the comparison.

Changing the production constructor was rejected for this change. That would mix measurement with implementation.

### 2. Prefetch artefacts and isolate every repetition

Prefetch the ONNX and torch model artefacts before timing. Cold start measures cached model construction and session initialisation. It excludes network time.

A coordinator starts a fresh child process for each cell and repetition. Run three repetitions per cell. Each repetition performs one discarded warm-up, then five iterations across five queries and 20 documents.

The runner checkpoints after every repetition. `--resume` skips completed repetitions. Every JSON write uses a temporary file followed by an atomic rename.

This design limits cache order effects. It also produces three independent cold-start and peak-memory observations.

### 3. Make MPS timing and execution auditable

The runner must perform these checks:

- Evaluate `torch.backends.mps.is_built()` and `is_available()` before cell 17C.
- Set `PYTORCH_ENABLE_MPS_FALLBACK=0` before importing torch in child processes.
- Assert that cell 17B selected CPU and cell 17C selected MPS.
- Call `torch.mps.synchronize()` immediately before and after each timed MPS inference.
- Record the requested device, selected device, torch version, Sentence Transformers version, macOS version, chip, and memory.
- Record process peak RSS for every cell.
- Record MPS current and driver-allocated memory for cell 17C.

An unavailable MPS backend or unsupported MPS operation fails H1. The runner must not report a CPU fallback as MPS performance.

### 4. Separate acceleration gates from adoption gates

Use the median of the three repetition-level values.

| Gate | Criterion | Meaning |
| --- | --- | --- |
| H1 | 17C loads, selects MPS, and completes without CPU fallback | MPS is usable |
| H2 | 17C P50 is at least 20% lower than 17B P50 | MPS materially accelerates torch |
| H3 | 17C P50 is at least 20% lower than 17A P50, and 17C P95 does not exceed 17A P95 | MPS improves the project baseline |
| H4 | 17C cold start is at most 3 times 17A, and peak RSS is at most 2 times 17A | Operational cost is bounded |
| H5 | 17B and 17C return identical top-ranked documents; 17A and 17C also match for every query | Device and backend changes preserve the workload outcome |

Record full ranking correlation and score differences as diagnostics.

The 20% threshold represents practical significance for a new runtime path. It is not a claim about measurement noise.

### 5. Pre-commit the interpretation

- H1 failure: record MPS as unavailable or unsupported on the tested stack.
- H1 and H2 pass, H3 fails: record that MPS accelerates torch while ONNX CPU remains preferable.
- H1 to H4 pass, H5 fails: reject adoption because results change on the fixed workload.
- H1 to H5 pass: propose a separate OpenSpec change for explicit device configuration and backend policy.
- Any negative result keeps ONNX CPU as the default.

A follow-up device setting should consider `auto|cpu|mps`. It must also add the device to the torch model cache key.

### 6. ADR-043 records the bounded decision

ADR-043 records:

- CoreML evidence from Experiment 16.
- ONNX CPU as the current default.
- The technical MPS verdict from H1 and H2.
- The project adoption verdict from H3 to H5.
- Exact hardware and locked package versions.
- Conditions that require re-testing.

The ADR updates `docs/adr/ADR_README.md`. Experiment 17 updates `experiments/EXP_README.md`.

## Risks / Trade-offs

- **Asynchronous MPS execution can under-report latency.** Synchronise around timed calls.
- **MPS can fall back to CPU.** Disable fallback and assert the selected device.
- **Downloads can distort cold start.** Prefetch every artefact before measurement.
- **The direct torch adapter can drift from production semantics.** Reuse project constants and compare its output with the untimed production preflight.
- **One machine cannot represent every Apple Silicon generation.** Bind the ADR conclusion to recorded hardware and versions.
- **MiniLM may be too small for GPU dispatch.** Treat this as a model-specific decision.

## Migration Plan

No migration applies. This change creates experiment and documentation artefacts only.
