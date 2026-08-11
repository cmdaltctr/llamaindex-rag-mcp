## 9. Experiment 17 — Apple acceleration, settled

> Run this AFTER the pluggable-reranker-backend change has merged, so a
> working torch backend exists to measure. Load the `s-experiment` skill
> first. Do NOT run this before the backend works — a benchmark of
> broken code is worse than no benchmark.
>
> Scope note: CoreML is NOT re-tested. Experiment 16 (2026-08-03) already
> measured it and found no acceleration. MPS (Metal Performance Shaders)
> is the only untested route. MPS is an Apple framework built on Metal,
> not a PyTorch feature — it is accessible through MPSGraph, Core ML,
> TensorFlow's Metal plugin, MLX, and PyTorch's MPS backend. For this
> project's reranker, the torch backend is the path that makes MPS
> reachable, and the pluggable-reranker-backend change is what opened it.

- [ ] 9.1 Create `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/` from `experiments/EXP_PROTOCOL_TEMPLATE.md`
- [ ] 9.2 Write `protocol.md` with three cells, all on the **default MiniLM model** — Experiment 16's numbers are for ModernBERT and are not a valid baseline here: (17A) ONNX int8 on CPU, (17B) torch on CPU, (17C) torch on MPS
- [ ] 9.3 State the pass gates before running: H1 — torch on MPS loads without error; H2 — 17C P50 latency beats 17A P50 by at least 20%; H3 — 17C cold start no worse than 3× 17A; H4 — 17C top-ranked document matches 17A on every workload query
- [ ] 9.4 Reuse the Experiment 16 runner shape: each cell in a **separate process**. Experiment 16 finding 4 recorded that loading int8 first corrupts ORT global optimiser state and poisons later cells in the same process
- [ ] 9.5 Write `run_eval.py` with checkpoint and `--resume`, `print(..., flush=True)`, and atomic writes to `output/` (`.tmp` then rename), per the experiment discipline in `CLAUDE.md`
- [ ] 9.6 Record latency P50/P95/mean, cold start, and peak RSS per cell, matching Experiment 16's results table columns so the two are comparable
- [ ] 9.7 Run 5 warm iterations × 5 queries × 20 docs, matching Experiment 16's shape
- [ ] 9.8 Write `results.md` with the cell table, the pass-gate outcomes, and a plain recommendation
- [ ] 9.9 Write `docs/adr/039-apple-acceleration-for-the-reranker.md` recording all three routes and their verdicts: CoreML closed by Exp 16, CPU as current default, MPS decided by Exp 17. State plainly that CoreML did not fail because PyTorch was absent, and give the evidence. State accurately that MPS is an Apple framework (not a PyTorch feature) and that PyTorch's MPS backend is the route this project uses to reach it
- [ ] 9.10 Add the Exp 17 row to `experiments/EXP_README.md`
- [ ] 9.11 If MPS wins: do NOT change the default in this change. Open a follow-up change for torch device selection, and note it in the ADR's consequences
