## Purpose

Defines an admissible Experiment 5b for a persistent optional Torch MPS worker,
including compatible correctness comparisons, reproducible latency and memory
estimands, lifecycle failure probes, and the Torch-free default boundary.

## ADDED Requirements

### Requirement: Experiment 5b SHALL preserve prior evidence and workload identity

Experiment 5b SHALL have its own protocol, plan, raw artefacts and verdict. It
SHALL reuse the immutable Experiment 5 parity workload by recorded SHA-256 and
SHALL NOT alter Experiment 5 or describe its failed H3 gate as passed.

#### Scenario: Prior evidence remains immutable

- **WHEN** Experiment 5b is prepared, executed or summarised
- **THEN** Experiment 5 protocol, raw rows, gates and verdict MUST remain unchanged
- **AND** Experiment 5b MUST identify the reused workload before measurement
- **AND** any absolute Experiment 5b memory budget MUST be described as a new opt-in deployment budget

### Requirement: The experiment SHALL use a complete persistence-by-device matrix

The plan SHALL include ONNX CPU in-process, fresh Torch MPS, persistent Torch
MPS, fresh Torch CPU and persistent Torch CPU. Every Torch cell SHALL use the
optional extra; the parent and base route SHALL remain free of Torch-stack
imports.

#### Scenario: Plan, runner and routes agree

- **WHEN** the experiment starts
- **THEN** the runner matrix MUST match the machine-readable plan
- **AND** every response admitted to evidence MUST prove its backend, device, model identity, cardinality and successful reranking
- **AND** `PYTORCH_ENABLE_MPS_FALLBACK=0` MUST have been set before Torch import

#### Scenario: Persistence and device effects are estimable

- **WHEN** the matrix is summarised
- **THEN** fresh versus persistent comparisons MUST be available within CPU and MPS
- **AND** CPU versus MPS comparisons MUST be available within fresh and persistent execution

### Requirement: Correctness gates SHALL compare compatible inference routes

Worker correctness SHALL be gated between Torch fp32 routes using the same
model revision. ONNX-int8 versus Torch-fp32 differences SHALL be reported as
backend/quantisation divergence and SHALL NOT be classified as an IPC or MPS
parity failure.

#### Scenario: Persistent MPS correctness

- **WHEN** paired persistent-MPS, fresh-MPS and persistent-CPU responses are compared
- **THEN** ranking equality MUST be 100%
- **AND** maximum score delta MUST be at most `1e-4`

#### Scenario: ONNX and Torch disagree

- **WHEN** paired ONNX and Torch responses produce different ranks or scores
- **THEN** raw divergence MUST be retained and reported
- **AND** the difference MUST NOT fail the compatible-route correctness gate

### Requirement: The worker protocol SHALL be bounded and observable

The JSON-lines protocol SHALL reserve stdout for bounded versioned frames,
drain stderr concurrently, correlate request IDs, use monotonic deadlines,
reject malformed/oversized/late frames and expose starting, ready, unhealthy
and stopped states.

#### Scenario: Ready handshake proves route identity

- **WHEN** model loading completes
- **THEN** the worker MUST report exact model identity, Torch/dependency versions, requested/effective device, MPS availability and fallback policy
- **AND** a claimed MPS worker MUST fail preflight on CPU fallback

#### Scenario: A measured request silently degrades

- **WHEN** a response is unrereanked, has wrong cardinality, wrong route or wrong generation
- **THEN** it MUST be retained as a failure row but excluded from aggregates
- **AND** the cell MUST abort

### Requirement: Lifecycle failure probes SHALL cover parent, worker and channel failures

The harness SHALL test worker death, worker hang, parent death while idle and
in-flight, output backpressure, stderr flooding, idle expiry and orderly
shutdown under registered deadlines and restart limits.

#### Scenario: Worker loss or hang degrades within deadline

- **WHEN** a ready worker dies or becomes non-responsive during a request
- **THEN** the request MUST complete through ONNX CPU or the existing un-reranked fallback within the registered deadline
- **AND** diagnostics MUST identify the route and failure
- **AND** no late worker response MUST be admitted

#### Scenario: Parent death leaves no orphan

- **WHEN** an external supervisor kills the parent while the worker is idle or in-flight
- **THEN** the worker and descendants MUST exit within the registered TERM/KILL bounds
- **AND** the supervisor MUST prove they were reaped or no longer exist

### Requirement: Primary latency SHALL be parent-observed and break-even cumulative

The primary request latency SHALL include serialisation, queueing, IPC,
inference and response validation. Break-even SHALL include worker startup,
model load and warm-up and compare cumulative persistent time with paired W1
request time.

#### Scenario: Break-even is calculated reproducibly

- **WHEN** a complete persistent lifetime is summarised
- **THEN** its first sustained cumulative crossover MUST be recorded
- **AND** all lifetime values, their median and a one-sided 95% upper confidence bound MUST be reported
- **AND** the upper confidence bound MUST be at most 150 requests on the frozen primary workload
- **AND** candidate-count/token-length-stratified break-even MUST be reported

### Requirement: Memory estimands SHALL use current RSS and declared windows

Each persistent lifetime SHALL serve at least 1,000 measured requests after
untimed warm-up. Current RSS SHALL be sampled at least once per second and every
ten requests. Requests 1–200 are burn-in; plateau is the 95th percentile over
requests 801–1000; growth is Theil-Sen slope over requests 201–1000 with a
seeded block-bootstrap one-sided 95% upper confidence bound.

#### Scenario: Memory instrumentation is capable

- **WHEN** current RSS cannot be sampled
- **THEN** plateau and growth gates MUST be `NOT_EVALUABLE`
- **AND** promotion MUST be blocked
- **AND** peak-only RSS MUST NOT be used as proof of plateau or reclamation

#### Scenario: Opt-in deployment budgets

- **GIVEN** the declared target is Apple Silicon macOS with at least 16 GiB physical memory
- **WHEN** a W3 lifetime completes
- **THEN** worker plateau RSS MUST be at most 750 MiB
- **AND** fallback-ready parent plus worker process-tree plateau RSS MUST be at most 1,250 MiB
- **AND** process-tree peak RSS MUST be at most 1,500 MiB
- **AND** every lifetime MUST pass independently

#### Scenario: Post-burn-in growth

- **WHEN** lifetime and pooled slopes are calculated
- **THEN** every one-sided 95% upper bound MUST be below 20 MiB per 1,000 requests
- **AND** worker RSS, parent RSS, process-tree RSS, MPS current allocation and MPS driver allocation MUST remain separate fields

### Requirement: Speed gates SHALL distinguish device and deployment comparisons

Persistent MPS SHALL be compared with persistent Torch CPU for the device-speed
gate and with ONNX CPU for a separately named deployment-value gate. Both use
parent-observed latency.

#### Scenario: Device-speed gate

- **WHEN** paired W3 and W4 measured rows are summarised
- **THEN** W3 median latency MUST be at most `0.8` times W4 median latency

#### Scenario: Production-deployment gate

- **WHEN** paired W3 and W1 measured rows are summarised
- **THEN** W3 median latency MUST be at most `0.8` times W1 median latency
- **AND** the result MUST NOT be described as a replication of Experiment 5 H2

### Requirement: Longevity SHALL include heterogeneous shapes and independent lifetimes

W3 and W4 SHALL each run at least three complete fresh worker lifetimes with
counterbalanced whole-lifetime order. The frozen parity workload SHALL be
supplemented by a hashed longevity schedule varying candidate count and token
length. Thermal, power and interference evidence SHALL be recorded.

#### Scenario: A lifetime is interrupted or invalidated

- **WHEN** a lifetime fails, is interrupted or breaches a registered interference condition
- **THEN** its partial rows MUST remain marked invalid
- **AND** a replacement lifetime MUST restart from request zero with a new PID
- **AND** no aggregate or memory slope MUST cross worker generations

### Requirement: Evidence SHALL satisfy TDR-014 and exact identity requirements

Every cited cell SHALL retain plan agreement, repo and lock identities, exact
model revision/file hashes, workload hashes, manifest, preflight, raw rows,
warm-up separation, atomic complete-lifetime checkpoint and completion status.

#### Scenario: Deterministic projection rerun

- **WHEN** the canonical correctness projection is generated twice from the same frozen raw rows
- **THEN** it MUST be byte-identical after excluded timing/process fields are removed
- **AND** fresh inference reruns MUST use the registered numerical tolerance rather than a byte-identity claim

### Requirement: This change SHALL NOT introduce a production worker

Experiment 5b SHALL use an experiment-owned prototype. Production modules,
runtime settings and backend selection SHALL remain unchanged.

#### Scenario: Positive experiment result

- **WHEN** every Experiment 5b gate passes
- **THEN** the result MAY recommend a production worker
- **AND** implementation MUST wait for a separate OpenSpec change and decision record
