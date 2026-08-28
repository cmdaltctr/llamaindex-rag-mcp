## Why

ADR-038 made Apple MPS reachable through the optional torch reranker, but the project has no measured evidence for its value. Experiment 16 ruled out ONNX CoreML for ModernBERT; it did not measure PyTorch MPS or the default MiniLM model.

This change measures the remaining route and records a hardware-specific verdict in ADR-043.

## What Changes

- Run `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/` on `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- Use one fixed workload and three controlled cells:
  - **17A**: production ONNX variant on CPU.
  - **17B**: Sentence Transformers torch backend forced to CPU.
  - **17C**: Sentence Transformers torch backend forced to MPS.
- Separate technical acceleration from project value. Compare 17C with both 17B and 17A.
- Record raw timings, latency summaries, cold start, process memory, MPS memory, resolved model variant, selected device, hardware, and package versions.
- Write ADR-043 with the CoreML, ONNX CPU, and MPS findings.
- Update the ADR index and Experiment 17 index entry.
- Propose a separate runtime change only if MPS passes every adoption gate.

Out of scope: runtime code changes, default changes, model changes, CoreML re-testing, and new project dependencies.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This research and documentation change does not alter a runtime requirement. The change therefore sets `skip_specs: true`.

## Impact

**Experiments**

- Adds `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/`.
- Reuses Experiment 16's fixed workload and separate-process isolation.
- Uses the existing `torch` optional extra. It adds no project dependency.

**Documentation**

- Adds `docs/adr/043-apple-acceleration-for-the-reranker.md`.
- Updates `docs/adr/ADR_README.md` and `experiments/EXP_README.md`.

**Runtime**

- No production code or configuration changes.
- The default remains the ONNX backend on CPU.
- The optional torch backend retains Sentence Transformers' automatic device selection.

**Branching**

- Targets `v3`, matching the archived pluggable-reranker-backend change.
- Has no release impact.

**Risk**

- Results apply to the recorded Apple Silicon machine and locked package versions.
- MiniLM can be too small to benefit from GPU dispatch costs. A negative result remains a valid decision outcome.
