## Why

Experiment 5 proved that Torch MPS preserves Torch CPU rankings and improves
steady-state latency, but it failed the registered memory and cold-start gates.
A persistent optional worker could amortise import and model-load cost while
keeping Torch out of the base process. A new experiment is required because
that deployment shape was not measured by Experiment 5.

The new experiment does not reopen Experiment 5. Its H3 result remains FAIL.
Experiment 5b asks a narrower product question: whether a long-lived,
process-isolated worker fits a separately declared opt-in memory budget and
recovers safely from lifecycle failures.

## What Changes

- Create Experiment 5b with a committed, identity-hashed workload and a
  pre-registered TDR-014 protocol.
- Evaluate five cells: in-process ONNX CPU; fresh and persistent Torch MPS;
  and fresh and persistent Torch CPU.
- Gate Torch-route correctness only between compatible Torch fp32 routes.
  ONNX-int8 versus Torch-fp32 ranking and score divergence is reported, not
  treated as an IPC or MPS correctness failure.
- Separate the device-speed gate (persistent MPS versus persistent CPU) from
  the production-deployment comparison (persistent MPS versus ONNX CPU).
- Measure parent-observed end-to-end latency, cumulative startup break-even,
  worker and complete process-tree memory, MPS allocator/driver metrics,
  post-burn-in growth, heterogeneous-shape longevity, and thermal/order drift.
- Exercise parent death, worker death, worker hang, pipe backpressure,
  deadline, idle restart, bounded termination, reaping, and orphan behaviour.
- Prove the selected model revision, effective device, fallback policy and
  successful reranking on every admitted response.
- Keep Torch in its existing optional extra and keep ONNX CPU as the
  production default throughout the experiment.
- Require a separate follow-up OpenSpec and decision record before any
  production worker is introduced.
- Correct the canonical reranker contract so it does not promise cross-backend
  ranking or threshold interchangeability contradicted by Experiment 5.

## Capabilities

### New Capabilities

- `persistent-mps-worker-evaluation`: Defines the worker experiment, runtime
  truth, estimands, lifecycle probes, raw evidence, and promotion gates.

### Modified Capabilities

- `reranker-backend-selection`: Preserves the common public score range while
  distinguishing same-backend device parity from ONNX/Torch quantisation
  divergence and backend-specific calibration.

## Impact

- Adds an Experiment 5b protocol, harness, worker prototype, fixed workload,
  plan, raw-output contract, tests, and summariser under `experiments/`.
- Uses the production Torch reranker only inside optional-extra experiment
  children; the parent remains Torch-free.
- Changes one canonical specification to match already-committed empirical
  evidence; it does not change production reranker behaviour.
- Adds no base dependency and makes no production configuration or API change.
