## Why

The pluggable-reranker-backend change (PR #37) introduced a torch reranker backend behind an opt-in extra, opening the only untested route to Apple Silicon's GPU hardware for this project's reranker: MPS (Metal Performance Shaders) via PyTorch's MPS backend. Experiment 16 (2026-08-03) already settled CoreML — it accelerated nothing because ONNX Runtime partitions the graph and most operations fall back to CPU. MPS has never been measured because the project had no PyTorch path at all. Now it does, behind the extra, and the question recurs every time someone asks why the reranker is CPU-only on a machine with a GPU.

MPS is an Apple framework — a collection of GPU-accelerated primitives built on Metal — not a PyTorch feature. It is accessible through multiple paths: the native MPSGraph framework (Swift/Objective-C), Core ML, TensorFlow's Metal plugin, MLX, and PyTorch's MPS backend. For this project's reranker, the torch backend is the path that makes MPS reachable, because we have no Swift/Metal, MLX, or TensorFlow-Metal integration. The ADR states this accurately.

This change runs Experiment 17 to close the question with numbers and records the verdict in ADR-043, so it stops recurring regardless of the outcome.

## What Changes

- Run `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/` with three cells on the **default MiniLM model** (Experiment 16 used ModernBERT, so its numbers are not a valid baseline here):
  - **17A**: ONNX int8 on CPU (current default)
  - **17B**: torch on CPU
  - **17C**: torch on MPS
- Record latency P50/P95/mean, cold start, and peak RSS per cell, matching Experiment 16's results table columns so the two are comparable.
- Write `docs/adr/043-apple-acceleration-for-the-reranker.md` recording all three acceleration routes and their verdicts: CoreML closed by Exp 16, CPU as current default, MPS decided by Exp 17.
- If MPS wins: do NOT change the default in this change. Open a follow-up change for torch device selection, and note it in the ADR's consequences.

Out of scope: changing the default backend, changing the default model, re-testing CoreML, and any code change to the reranker backends. This is research + an ADR, not a code change.

## Capabilities

### Modified Capabilities

- `reranking`: the ADR records the Apple-acceleration verdict for all three routes (CoreML, CPU, MPS), closing the open question from ADR-029's deferred items. No spec requirement changes — the default execution provider stays CPU.

## Impact

**Experiments**

- New: `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/`.
- Reuses Experiment 16's separate-process-per-cell runner shape. Its finding 4 recorded that loading int8 first corrupts ONNX Runtime's global optimiser state and poisons later cells in the same process.

**Docs**

- New ADR-043 recording all three routes and their verdicts.
- `experiments/EXP_README.md` gains the Exp 17 row.

**Branching**

- Targets `v3` (same as the pluggable-reranker-backend change it was split from). No code change, so no release impact.

**Risk**

- MPS may not be available on all CI runners (GitHub Actions macOS runners have Apple Silicon but MPS support varies by runner generation). The experiment is run locally on the developer's machine, not in CI — matching Experiment 16's approach.
- A benchmark of the default MiniLM model may show MPS overhead exceeds its benefit for small models (kernel launch latency dominates). This is a valid finding, not a failure — the ADR records it plainly.
