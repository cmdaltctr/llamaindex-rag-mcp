## 1. Protocol and workload preparation

- [ ] 1.1 Create the dated experiment directory `experiments/5b-persistent-mps-reranker-worker-2026-08-20/` with protocol.md carrying the pre-registered hypotheses, cell matrix (W1–W4), lifecycle probes, and gates G1–G7 exactly as specified, before any harness code runs.
- [ ] 1.2 Record the reused Experiment 5 workload identity (SHA-256 of `experiments/example/experiment-5-reranker-backend-device-parity/workload.json`) in the protocol and plan; do not modify the Experiment 5 directory.
- [ ] 1.3 Write `plan.json` declaring the four cells, controlled variables, preflight assertions (backend/device/model/workload identity), and gate thresholds; verify it loads via the shared `ExperimentPlan.from_json`.

## 2. Worker prototype and harness

- [ ] 2.1 Implement the experiment-owned worker child script: stdio JSON-lines protocol with `hello`/`ready` handshake (torch version, model, effective device, MPS availability), `rerank` request/response, request deadlines, and EOF-on-stdin exit latch.
- [ ] 2.2 Verify the worker constructs the production `SentenceTransformerReranker` unmodified and applies no separate scoring logic (identity activation + shared sigmoid only).
- [ ] 2.3 Implement the parent harness: plan agreement check, per-cell D13 manifests via `experiments/_lib` observers, untimed load + warm-up separation, counterbalancing, sampled RSS/MPS memory capture, and induced-death and shutdown lifecycle probes.
- [ ] 2.4 Implement atomic `.tmp`→rename checkpoints per request batch with `--resume`; incomplete lifetimes recorded by status string with reason.
- [ ] 2.5 Add fast harness tests (no model load, no network): plan/runner agreement, handshake validation, deadline fallback routing, checkpoint resume, and warm-up exclusion from aggregates.

## 3. Preflight dry run (untimed)

- [ ] 3.1 Install the `torch` extra; confirm `pyproject.toml` and `uv.lock` are unchanged; confirm MPS availability and record it.
- [ ] 3.2 Run untimed preflight dry runs for all four cells; prove effective backend/device per cell before any measured work; abort (never record as slow) on any requested-vs-effective mismatch.

## 4. Measured campaign (quiet machine)

- [ ] 4.1 Run W1–W4 with the machine reserved: ≥3 fresh worker lifetimes per persistent cell, ≥1,000 measured requests per lifetime, `HF_HUB_OFFLINE=1`, warm-up excluded.
- [ ] 4.2 Execute the lifecycle probes inside W3: induced mid-serving worker death (deadline-bounded ONNX/un-reranked fallback) and idle-expiry restart with RSS reclamation check.
- [ ] 4.3 Run `summarise_eval.py`: G1–G7 verdicts, break-even N*, plateau RSS, MPS allocator plateau, growth slope per 1,000 requests, and both absolute and ratio memory reporting.
- [ ] 4.4 Produce a deterministic correctness rerun proof (two runs, byte-identical canonical projections with timing and process identifiers removed).

## 5. Evidence, documentation, and gates

- [ ] 5.1 Write `results.md` with per-gate verdicts and honest overall status; append the execution record to `protocol.md`; commit raw artefacts per TDR-014.
- [ ] 5.2 Record in `experiments/example/README.md` that Experiment 5b exists with its verdict and artefact links, without altering the Experiment 5 record.
- [ ] 5.3 If every gate passes: record that a production worker is recommended and that implementation requires a separate OpenSpec change and decision record. If any gate fails: record ONNX CPU as retained default and the worker as not promoted.
- [ ] 5.4 Run scoped ruff check/format on new Python files; run the full fast suite; run `openspec validate evaluate-persistent-mps-reranker-worker --strict`.
