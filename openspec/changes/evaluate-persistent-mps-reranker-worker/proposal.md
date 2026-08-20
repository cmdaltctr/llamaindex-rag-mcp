## Why

Experiment 5 proved that Torch MPS preserves Torch CPU rankings and improves steady-state latency, but it failed the memory and cold-start gates. A persistent optional worker may amortise startup while isolating Torch from the base process, so a new experiment must measure that deployment shape before production work is considered.

## What Changes

- Create Experiment 5b with a committed, identity-hashed workload and a pre-registered protocol.
- Evaluate a persistent Torch MPS worker that loads one model and serves repeated rerank requests across a bounded local IPC boundary.
- Compare in-process ONNX CPU, fresh-child Torch MPS, persistent-worker Torch MPS, and an optional persistent Torch CPU control.
- Measure startup amortisation, steady-state latency and throughput, process RSS, MPS allocator memory, memory growth, shutdown reclamation, and induced-failure fallback.
- Keep Torch in its existing optional extra and keep ONNX CPU as the production default throughout the experiment.
- Require a separate follow-up OpenSpec and decision record before any production worker is introduced.
- Preserve Experiment 5 as a valid FAIL record; Experiment 5b SHALL use new gates and artefacts.

## Capabilities

### New Capabilities

- `persistent-mps-worker-evaluation`: Defines the worker experiment, runtime truth, lifecycle probes, raw evidence, and promotion gates.

### Modified Capabilities

- None. This change produces experimental evidence and does not alter production reranker behaviour.

## Impact

- Adds an Experiment 5b protocol, harness, fixed workload, plan, raw-output contract, and summariser under `experiments/`.
- Uses the production Torch reranker only inside optional-extra experiment children.
- Exercises process lifecycle, local IPC, timeout, fallback, and memory instrumentation in the harness.
- Adds no base dependency and makes no production configuration or API change.
