## Context

Experiment 5 (`experiments/example/experiment-5-reranker-backend-device-parity/`,
commit `1a12249`) measured fresh-child ONNX CPU, ONNX CoreML, Torch CPU and
Torch MPS routes. Torch MPS versus Torch CPU passed device parity and speed:
360/360 rankings were equal, maximum score delta was `4.02e-07`, and median
latency was `0.677` times Torch CPU. The operational gate failed: Torch MPS
peak RSS was `2.370` times ONNX CPU and cold start was `13.826` times ONNX
CPU. The import/model stack, rather than the live MPS allocator alone,
dominated that cost.

Experiment 5 also proved that ONNX int8 and Torch fp32 are not interchangeable:
their rankings disagreed on 360/360 comparisons. Experiment 5b therefore must
not use ONNX/Torch equality as a worker correctness gate.

Production constraints remain unchanged: the `torch` extra is opt-in;
`PYTORCH_ENABLE_MPS_FALLBACK=0` must be set before Torch import; ONNX CPU is
the default; the production `SentenceTransformerReranker` remains unmodified;
and TDR-014 controls experiment admissibility.

## Goals / Non-Goals

**Goals:**

- Measure cumulative startup amortisation, end-to-end latency, total deployment
  memory and post-burn-in growth for a long-lived worker.
- Separate persistence effects, device effects and their interaction.
- Prove every measured request used the requested model/device and actually
  reranked its candidates.
- Exercise failure and orphan cases that are specific to process isolation.
- Keep all executable changes inside the experiment directory.

**Non-Goals:**

- No production worker, settings, default-backend or runtime-module change.
- No revision of Experiment 5, its gates or its FAIL verdict.
- No claim that passing an opt-in absolute memory budget makes Experiment 5 H3
  pass.
- No CoreML re-test.

## Decisions

### D1: Versioned bounded stdio protocol

The experiment-owned worker uses newline-delimited JSON over stdin/stdout.
Stdout is reserved exclusively for protocol frames; diagnostics go to stderr,
which the parent drains concurrently. Every frame carries a protocol version,
message type and request ID. The protocol registers a maximum frame size,
candidate count and token budget and rejects malformed, oversized, duplicate,
late or unknown frames.

The handshake is `hello` -> `ready`. It reports the exact model revision/file
identity, Torch and dependency versions, requested/effective device, MPS
availability and the value of `PYTORCH_ENABLE_MPS_FALLBACK`. The worker may
serve only after the parent validates that evidence.

EOF-on-stdin remains one orphan signal, not the complete orphan guarantee.
The parent spawns with unrelated descriptors closed, uses monotonic deadlines,
drains both output pipes, and owns bounded TERM-then-KILL and `waitpid`/reaping.
An external supervisor tests parent death because a parent cannot prove its own
post-mortem behaviour.

### D2: Production reranker with per-response route admission

The worker constructs and invokes the production
`SentenceTransformerReranker` without reproducing its scoring. The environment
sets `PYTORCH_ENABLE_MPS_FALLBACK=0` before any Torch-capable import.

Handshake evidence alone is insufficient: every response must report request
ID, model identity, effective backend/device, result cardinality and reranked
status. A response with `_reranked=False`, wrong cardinality, wrong route or a
late generation is retained as a failure row but excluded from latency and
correctness aggregates; the cell aborts immediately.

The parent process is tested to prove that neither `torch`, `transformers` nor
`sentence_transformers` was imported there.

### D3: Complete persistence-by-device matrix

- W1 `onnx_cpu` in-process: production-default deployment baseline.
- W2 `torch_mps` fresh child: one-shot MPS cost and correctness reference.
- W3 `torch_mps` persistent worker: at least three complete fresh lifetimes,
  each with at least 1,000 measured requests.
- W4 `torch_cpu` persistent worker: device-speed and persistent CPU control.
- W5 `torch_cpu` fresh child: completes the CPU/MPS by fresh/persistent matrix.

W2/W3 and W4/W5 estimate persistence effects within a device. W3/W4 estimates
the device effect within persistence. W2/W5 estimates the device effect in the
fresh-child shape. Lifetimes, not individual repeated requests, are the unit of
replication. Whole-lifetime order is counterbalanced.

W1 runs from a declared fixed parent state: either a new top-level parent per
replication or a preloaded fallback-ready ONNX parent for every replication.
The protocol chooses one state before measurement and never mixes it.

### D4: Parent-observed latency and empirical cumulative break-even

All primary latency is measured at the parent around serialisation, queueing,
pipe transfer, worker inference and response validation. Worker-only inference
time is diagnostic.

For lifetime `l`, cumulative persistent time at request count `n` is:

`startup_l + warmup_l + sum(parent_observed_latency_l[1:n])`.

The W1 comparator is the sum of the paired W1 request latencies for the same
ordered workload. `N*_l` is the first `n` for which persistent cumulative time
is no greater than W1 cumulative time and remains no greater through the end of
the registered horizon. The summary reports every lifetime value, the median
and a bootstrap one-sided 95% upper confidence bound.

The primary frozen-workload product gate retains `N* <= 150`, but it is now
labelled a deployment gate rather than a replication of Experiment 5. The
protocol also reports break-even by candidate-count/token-length stratum and
normalised candidate-token work. A production proposal must justify that its
idle policy normally retains a worker for more requests than the observed
conservative break-even; Experiment 5b alone cannot choose that policy.

### D5: Memory estimands and declared opt-in budget

Current worker RSS is mandatory and sampled with `psutil` at least once per
second and every ten completed requests. Peak-only `ru_maxrss` is retained as a
diagnostic but cannot satisfy a plateau or growth gate. If current RSS cannot
be sampled, the affected gates are `NOT_EVALUABLE` and promotion is blocked.

The opt-in target profile is Apple Silicon macOS with at least 16 GiB physical
memory. This is a new product budget for a different deployment shape, not a
replacement for Experiment 5 H3:

- worker steady-state RSS ceiling: 750 MiB;
- fallback-ready parent plus worker steady-state process-tree ceiling:
  1,250 MiB;
- fallback-ready parent plus worker process-tree peak ceiling: 1,500 MiB.

For each lifetime, burn-in is the first 200 measured requests. The plateau
estimate is the 95th percentile of current-RSS samples over requests 801–1000.
Each lifetime must meet the ceilings; values are not averaged across a failing
lifetime.

Growth uses the ordered current-RSS samples from requests 201–1000. The
estimator is Theil-Sen slope converted to MiB per 1,000 requests. A seeded
block bootstrap supplies a one-sided 95% upper confidence bound; both every
lifetime and the pooled bound must be below 20 MiB per 1,000 requests.

The manifest and summary separately retain worker RSS, parent RSS, process-tree
RSS, MPS current allocation, MPS driver allocation and all ratios to W1.

### D6: Compatible correctness and performance gates

The registered gates are:

- G1a: W3 versus paired W2 Torch-MPS responses has 100% ranking equality and
  maximum score delta at most `1e-4`.
- G1b: W3 versus paired W4 Torch-MPS/Torch-CPU responses has 100% ranking
  equality and maximum score delta at most `1e-4`.
- G1c: every admitted response proves the requested route and successful
  reranking; one violation fails the cell.
- G2: parent-observed W3 median latency is at most `0.8` times paired W4
  persistent-Torch-CPU latency. This is the device-speed gate corresponding to
  Experiment 5 H2.
- G3: parent-observed W3 median latency is at most `0.8` times paired W1 ONNX
  CPU latency. This is a separate deployment-value gate.
- G4: the cumulative break-even one-sided 95% upper bound is at most 150
  requests on the frozen primary workload.
- G5: every lifetime meets the worker, process-tree plateau and process-tree
  peak ceilings in D5.
- G6: every lifetime and the pooled growth upper bound are below 20 MiB per
  1,000 requests.
- G7: worker death, worker hang and pipe-pressure probes complete through ONNX
  or the existing un-reranked fallback within their registered deadlines,
  with loud route/failure diagnostics and no late response admitted.
- G8: requested shutdown, stdin EOF, idle expiry and externally induced parent
  death leave no worker or descendant after bounded TERM/KILL and reaping.
- G9: all TDR-014 plan, manifest, row, checkpoint and completion requirements
  pass.

ONNX/Torch rankings, score deltas and threshold decisions are reported as
backend-divergence diagnostics and are not part of G1.

### D7: Heterogeneous longevity and interference controls

The immutable Experiment 5 workload is retained for paired parity and primary
break-even. A second pre-registered longevity schedule varies candidate count
and token length while preserving fixed seeds and immutable hashes. It includes
bounded bursts sufficient to expose queue/backpressure behaviour; the worker
remains single-inference-at-a-time unless a later production proposal states
otherwise.

Every lifetime records power source, macOS version, hardware identity, memory
pressure, thermal state when observable, foreground-interference declaration,
start/end wall time and cell order. A registered thermal or system-interference
breach invalidates and repeats the complete lifetime; it is never edited out at
the request-row level.

### D8: Failure, restart and checkpoint semantics

Lifecycle probes cover worker SIGKILL, worker SIGSTOP/native hang, parent
SIGKILL while idle and in-flight, stdout backpressure, stderr flooding,
malformed frames, idle expiry and orderly shutdown. The protocol fixes request
deadlines, drain deadline, TERM grace, KILL grace, restart backoff, maximum
restart attempts and generation rules before execution.

Checkpoints are atomic, but resume occurs only at complete-lifetime boundaries.
Partial lifetime rows remain as invalid evidence with a reason; a new PID must
restart that lifetime from request zero. A memory slope or correctness pairing
is never continued across worker generations.

### D9: TDR-014 identity and deterministic projections

Every cell records repo commit, lock hash, plan hash, workload hashes, exact
model revision and relevant cached-file hashes, Python/dependency versions,
effective backend/device and fallback environment. `HF_HUB_OFFLINE=1` is
required after cache identity is established.

Raw inference reruns use the registered numerical tolerance. “Byte-identical”
applies only to regenerating the canonical correctness projection twice from
the same frozen raw rows after timing/process fields are removed.

## Risks / Trade-offs

- The target memory ceilings are deliberately product budgets rather than a
  statistical restatement of Experiment 5. They may reject otherwise fast
  hardware and do not rehabilitate H3.
- Five cells and heterogeneous longevity increase machine time. Complete
  lifetime checkpointing sacrifices more work on failure but prevents invalid
  cross-PID evidence.
- An experiment-local protocol can recommend a production architecture but
  cannot prove production restart policy, packaging or real-traffic retention.

## Migration Plan

None. This is experiment-only. Rollback removes the Experiment 5b directory and
its unarchived change; completed Experiment 5 evidence is untouched.

## Open Questions

None may be deferred into measured execution. Any change to workload, sampler,
deadlines, restart policy, batch size, estimators or gates after the first
measured row invalidates the campaign and requires a new protocol version.
