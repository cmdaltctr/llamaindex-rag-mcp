## 1. Protocol and workload

> Load `s-experiment` before implementation. ADR-038 already provides the
> torch backend. Experiment 16 supplies CoreML evidence only.

- [x] 1.1 Create `experiments/17-reranker-mps-vs-onnx-cpu-2026-08-11/` from `experiments/EXP_PROTOCOL_TEMPLATE.md`
- [x] 1.2 Copy Experiment 16's fixed five-query, 20-document workload into `workload.json`
- [x] 1.3 Write `protocol.md` with cells 17A, 17B, 17C, and the untimed automatic-device preflight
- [x] 1.4 Fix the model, effective maximum length, batch size, workload, warm-up, iterations, and three repetitions
- [x] 1.5 State H1 to H5 and the interpretation rules from `design.md` before running any cell
- [x] 1.6 Define cached model construction as cold start and exclude downloads from timing

## 2. Runner, tests, and analysis

- [x] 2.1 Write failing tests for gate calculations, device assertions, repetition keys, and checkpoint resume
- [x] 2.2 Write `run_eval.py` as a coordinator that starts one child process per cell repetition
- [x] 2.3 Implement 17A with the production ONNX reranker and record its resolved ONNX variant
- [x] 2.4 Implement an experiment-only torch adapter for 17B and 17C with explicit `cpu` and `mps` devices
- [x] 2.5 Match production torch scoring: effective length, batch size, identity activation, shared sigmoid, sorting, and truncation
- [x] 2.6 Set `PYTORCH_ENABLE_MPS_FALLBACK=0` before torch import and fail unavailable or unsupported MPS runs
- [x] 2.7 Synchronise MPS immediately before and after every timed inference
- [x] 2.8 Record requested and selected devices, package versions, hardware, OS, raw timings, rankings, scores, RSS, and MPS memory
- [x] 2.9 Checkpoint after every repetition with atomic writes and support `--resume`
- [x] 2.10 Write `summarise_eval.py` to produce `output/eval_results.summary.json` and `results.md`
- [x] 2.11 Create Jupytext `analysis.py` that reads saved JSON and plots latency and memory distributions
- [x] 2.12 Run the focused tests and confirm they now pass

## 3. Execute Experiment 17

- [x] 3.1 Confirm torch, pandas, and matplotlib availability; obtain approval before any required `uv` installation
- [x] 3.2 Prefetch both model formats and record the resolved model revision before starting timers
- [x] 3.3 Run the untimed production preflight and verify its selected device
- [x] 3.4 Run one smoke repetition into a separate output directory and inspect its checkpoint
- [x] 3.5 Run three repetitions per cell with five warm iterations, five queries, and 20 documents
- [x] 3.6 Generate the summary, run `analysis.py`, and update `protocol.md` to PASS, FAIL, or INCONCLUSIVE
- [x] 3.7 Complete `results.md` with raw values, H1 to H5 outcomes, limitations, and a direct recommendation

## 4. Record the decision

- [x] 4.1 Write accepted ADR-043 with Experiment 16 CoreML evidence and Experiment 17 CPU and MPS evidence
- [x] 4.2 Distinguish the technical MPS verdict from the project adoption verdict in ADR-043
- [x] 4.3 Record exact hardware, versions, fallback policy, and conditions that require re-testing
- [x] 4.4 Add ADR-043 to `docs/adr/ADR_README.md`
- [x] 4.5 Add Experiment 17 and its final status to `experiments/EXP_README.md`
- [x] 4.6 If H1 to H5 pass, propose a separate change for device configuration, backend policy, and device-aware cache keys
- [x] 4.7 If any adoption gate fails, record the reason and keep ONNX CPU as the default

## 5. Validate the completed change

- [x] 5.1 Run the Experiment 17 focused tests
- [x] 5.2 Run `openspec validate apple-acceleration-for-reranker --strict`
- [x] 5.3 Run `graphify update .`
- [x] 5.4 Obtain approval, then run `uv run pytest -m "not slow" --cov=rag_mcp` before committing
