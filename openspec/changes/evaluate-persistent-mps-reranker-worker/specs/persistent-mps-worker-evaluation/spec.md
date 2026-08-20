## Purpose

Defines an admissible Experiment 5b that evaluates whether a persistent optional Torch MPS worker can amortise startup cost without sacrificing correctness, bounded memory, failure recovery, or the Torch-free default path.

## ADDED Requirements

### Requirement: Experiment 5b SHALL preserve the prior verdict and fixed workload

Experiment 5b SHALL be a new experiment with its own protocol, plan, raw artefacts, and verdict. It SHALL reuse the immutable Experiment 5 query and candidate workload by recorded SHA-256 identity. It SHALL NOT alter Experiment 5 or describe its failed H3 gate as passed.

#### Scenario: Prior evidence remains immutable

- **WHEN** Experiment 5b is prepared or executed
- **THEN** the committed Experiment 5 protocol, gates, raw rows, and verdict MUST remain unchanged
- **AND** Experiment 5b MUST record the reused workload identity before measured work

### Requirement: The experiment SHALL compare persistent and non-persistent routes

The plan SHALL include ONNX CPU in-process, fresh-child Torch MPS, persistent-worker Torch MPS, and persistent-worker Torch CPU cells. Every Torch cell SHALL use the optional Torch extra, and the base process SHALL remain free of Torch imports.

#### Scenario: Cell matrix agrees with the runner

- **WHEN** the experiment starts
- **THEN** the runner cell matrix MUST match the machine-readable plan
- **AND** every cell MUST prove its effective backend, device, model, and process lifecycle before timing

### Requirement: The persistent worker SHALL have a bounded observable lifecycle

The experiment worker SHALL expose starting, ready, unhealthy, and stopped states. It SHALL accept requests only while ready, use request deadlines, exit when its parent channel closes, and reclaim its process memory after shutdown.

#### Scenario: Ready handshake proves the route

- **WHEN** a worker completes model loading
- **THEN** it MUST report the model, Torch version, effective device, and MPS availability
- **AND** a claimed MPS worker MUST fail preflight if CPU fallback is observed

#### Scenario: Worker loss degrades within a deadline

- **WHEN** the experiment terminates a ready worker during a request
- **THEN** the request MUST complete through ONNX CPU or the existing un-reranked fallback within the registered deadline
- **AND** diagnostics MUST identify the effective route and failure reason

#### Scenario: Shutdown reclaims memory

- **WHEN** the parent requests shutdown or closes the worker channel
- **THEN** the worker MUST finish or abort the in-flight request within the registered drain deadline
- **AND** no child process MUST remain after the deadline
- **AND** process RSS MUST return to the registered post-exit tolerance

### Requirement: The experiment SHALL measure amortisation and memory growth

Each persistent cell SHALL run at least three fresh worker lifetimes. Each lifetime SHALL serve at least 1,000 measured rerank requests after an untimed warm-up. The harness SHALL record cold start, request latency, throughput, current process RSS, MPS allocator memory, and periodic memory samples.

#### Scenario: Warm-up stays outside measured rows

- **WHEN** a worker lifetime begins
- **THEN** model load and warm-up requests MUST be recorded separately from measured requests
- **AND** aggregates MUST exclude warm-up rows

#### Scenario: Memory growth is observable

- **WHEN** a persistent worker serves the longevity workload
- **THEN** the harness MUST retain ordered RSS and MPS allocator samples
- **AND** the summary MUST report a post-burn-in growth slope per 1,000 requests
- **AND** peak-only memory values MUST NOT be presented as proof of a stable plateau

### Requirement: Promotion gates SHALL be fixed before measurement

The protocol SHALL register numeric gates before measured cells run. At minimum, the gates SHALL cover ranking parity, steady-state speed, startup break-even, absolute worker RSS, memory-growth slope, timeout fallback, and clean shutdown.

#### Scenario: Minimum promotion gates

- **WHEN** the protocol becomes runnable
- **THEN** ranking equality MUST be 100% with maximum score delta at most `1e-4`
- **AND** persistent MPS median latency MUST be at most `0.8` times ONNX CPU
- **AND** startup break-even MUST be at most 150 measured requests
- **AND** worker RSS MUST remain at or below 750 MiB
- **AND** post-burn-in growth MUST remain below 20 MiB per 1,000 requests
- **AND** fallback and shutdown lifecycle probes MUST pass

#### Scenario: Failed gate prevents promotion

- **WHEN** any correctness, resource, fallback, or lifecycle gate fails
- **THEN** ONNX CPU MUST remain the production default
- **AND** the persistent worker MUST remain experimental

### Requirement: Experiment evidence SHALL satisfy the validity framework

Every cited cell SHALL carry its plan agreement, runtime manifest, preflight result, raw per-request rows, warm-up separation, completion status, and atomic checkpoint. Invalid or incomplete cells SHALL never be aggregated as numeric observations.

#### Scenario: Interrupted worker lifetime

- **WHEN** a worker lifetime stops before its declared requests finish
- **THEN** the lifetime MUST be recorded as incomplete with a reason
- **AND** its partial measurements MUST NOT enter promotion aggregates

#### Scenario: Deterministic correctness rerun

- **WHEN** the correctness projection is generated twice from identical inputs
- **THEN** rankings and score projections MUST be byte-identical after timing and process identifiers are removed

### Requirement: This change SHALL NOT introduce a production worker

Experiment 5b SHALL use an experiment-owned worker prototype. Production modules, runtime settings, and default backend selection SHALL remain unchanged in this change.

#### Scenario: Positive experiment result

- **WHEN** every Experiment 5b gate passes
- **THEN** the result MAY recommend a production worker
- **AND** implementation MUST wait for a separate OpenSpec change and decision record
