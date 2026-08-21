## 1. Protocol and immutable inputs

- [x] 1.1 Create `experiments/5b-persistent-mps-reranker-worker-2026-08-20/` and commit `protocol.md` before any measured run. It MUST contain W1–W5, G1–G9, all deadlines, restart limits, memory windows/estimators, workload strata and invalidation rules from the design/spec without placeholders.
- [x] 1.2 Record SHA-256 identities for the reused Experiment 5 workload and the heterogeneous longevity schedule; do not modify the Experiment 5 directory or verdict.
- [x] 1.3 Write `plan.json` with five cells, controlled variables, lifetime order, request counts, backend/device/model assertions and every numeric gate; load it through `ExperimentPlan.from_json`.
- [x] 1.4 Add a pre-run plan validator that enumerates each gate's exact cells, backend, precision, model revision, row population, estimator and threshold; it MUST reject ONNX-versus-Torch equality gates.

## 2. Protocol and worker prototype

- [x] 2.1 Implement the experiment-owned versioned JSON-lines worker with stdout reserved for bounded protocol frames, concurrently drained stderr, request-ID correlation, maximum frame/candidate/token sizes, malformed-frame errors and monotonic deadlines.
- [x] 2.2 Set `PYTORCH_ENABLE_MPS_FALLBACK=0` before any Torch-capable import. Handshake MUST report exact model revision/file hashes, stack versions, requested/effective device and fallback state.
- [x] 2.3 Construct the production `SentenceTransformerReranker` unmodified. Every response MUST report route, model identity, cardinality and reranked status; the first unrereanked/wrong-route/wrong-generation response aborts the cell and is never admitted to aggregates.
- [x] 2.4 Prove the parent has not imported `torch`, `transformers` or `sentence_transformers` after the worker and fallback probes.

## 3. Parent harness and lifecycle supervision

- [x] 3.1 Implement W1–W5 with whole-lifetime counterbalancing and one declared W1 parent state. Record parent-observed latency around serialisation, queueing, IPC, inference and response validation.
- [x] 3.2 Implement current-RSS sampling at least every second and every ten requests. If the sampler is unavailable, emit `NOT_EVALUABLE` for plateau/growth and block promotion; never substitute peak RSS.
- [x] 3.3 Implement D5 exactly: 200-request burn-in, request-801–1000 RSS p95 plateau, Theil-Sen slope over requests 201–1000, seeded block-bootstrap one-sided 95% bound, and separate worker/parent/tree/MPS-current/MPS-driver fields.
- [x] 3.4 Implement complete-lifetime atomic checkpoints. `--resume` MAY reuse complete lifetimes only; every incomplete lifetime restarts from request zero and no statistic crosses PIDs.
- [x] 3.5 Add external-supervisor probes for worker SIGKILL, worker SIGSTOP/hang, parent SIGKILL idle and in-flight, stdout backpressure, stderr flooding, malformed frames, EOF, idle expiry and orderly shutdown. Assert bounded TERM/KILL, reaping and absence of descendants.
- [x] 3.6 Register and test idle expiry, worker generation, restart backoff, maximum restart attempts and rejection of late responses.

## 4. Fast harness validation

- [x] 4.1 Add no-model/no-network tests for plan/runner/gate agreement, handshake identity, per-response route admission, malformed/oversized frames, deadline fallback, pipe draining, complete-lifetime resume and warm-up exclusion.
- [x] 4.2 Place tests under the configured pytest collection tree or invoke their exact path in CI; record the collection command and expected test count.
- [x] 4.3 Generate the canonical correctness projection twice from one frozen raw fixture and assert byte identity; separately test tolerance-based inference comparison semantics.

## 5. Untimed preflight

- [x] 5.1 Install the existing `torch` extra without changing `pyproject.toml` or `uv.lock`; prove MPS availability and record exact host, macOS, Python, lock and model-file identities.
- [x] 5.2 Run every W1–W5 route untimed. Abort before measurement on requested/effective mismatch, fallback-policy mismatch, missing model identity, unrereanked output or parent Torch-stack import.
- [x] 5.3 Run all lifecycle probes with a stub worker and then one untimed real-model request; do not begin measured work until every bounded-failure assertion passes.

## 6. Measured campaign

- [ ] 6.1 Run at least three complete fresh lifetimes for W3 and W4, each with at least 1,000 measured primary-workload requests plus the registered heterogeneous longevity schedule. Run on mains power and retain thermal/interference evidence.
- [ ] 6.2 Pair W2/W3, W3/W4, W4/W5 and W3/W1 rows exactly as the plan declares. Preserve ONNX/Torch divergence as descriptive raw evidence, not G1 input.
- [ ] 6.3 Calculate cumulative break-even including startup/load/warm-up, every lifetime N*, median and one-sided 95% upper bound; also report candidate-count/token-length strata and normalised candidate-token work.
- [ ] 6.4 Calculate and adjudicate all G1–G9 gates. Every lifetime must meet memory ceilings; do not average a failing lifetime into a pass.

## 7. Evidence and decision boundary

- [ ] 7.1 Write `results.md` with per-gate verdicts, absolute and ratio memory views, every invalid/not-evaluable cell, and an honest overall verdict; append the execution record to `protocol.md` and commit raw TDR-014 artefacts.
- [ ] 7.2 Record Experiment 5b in `experiments/example/README.md` without editing the Experiment 5 record or claiming H3 was rehabilitated.
- [ ] 7.3 A full pass MAY recommend a production-worker OpenSpec and ADR. Any failed or not-evaluable gate retains ONNX CPU and rejects promotion.
- [ ] 7.4 Run scoped Ruff checks/format, the explicitly collected harness tests, the full fast suite, and `openspec validate evaluate-persistent-mps-reranker-worker --strict`; record exact commands and counts.
