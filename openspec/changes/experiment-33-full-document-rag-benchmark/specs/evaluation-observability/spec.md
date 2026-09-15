# evaluation-observability Specification

## ADDED Requirements

### Requirement: Experiment 33 emits structured stage traces

The benchmark harness SHALL emit secret-free structured JSONL records for major pipeline stages and query outcomes.

#### Scenario: A query fails during retrieval
- **WHEN** retrieval raises or degrades
- **THEN** the trace SHALL record the stage, elapsed time, error/degraded status, and query identity
- **AND** the query SHALL remain in the benchmark denominator

### Requirement: Observability does not alter production protocol channels

Experiment traces SHALL remain outside MCP stdout and SHALL NOT require production transport changes.

#### Scenario: The benchmark runs through MCP
- **WHEN** tracing is enabled
- **THEN** trace output SHALL NOT be written to the MCP protocol stdout channel

### Requirement: Trace identity is sufficient for reproducibility

Each measured run SHALL record benchmark revision, OMRG commit, effective settings, provider/model identities, dependency-lock identity, and relevant index identity.

#### Scenario: Two runs use different embedding models
- **WHEN** the embedding identities differ
- **THEN** the traces SHALL expose that difference
- **AND** the results SHALL NOT be treated as the same frozen baseline

### Requirement: RAGAS remains an evaluation-only dependency

RAGAS MAY be used for secondary context/answer metrics but SHALL NOT be required by the base OMRG install or normal retrieval path.

#### Scenario: RAGAS is unavailable
- **WHEN** the optional evaluation environment does not contain RAGAS
- **THEN** primary retrieval metrics SHALL remain runnable
- **AND** RAGAS metrics SHALL be reported as not measured

### Requirement: RAGAS configuration is frozen when used

The RAGAS version, metric set, judge/provider, judge model, and relevant embedding model SHALL be recorded before measured scoring.

#### Scenario: Judge configuration changes
- **WHEN** the RAGAS judge model or metric configuration changes
- **THEN** the resulting scores SHALL belong to a distinct evaluation revision

### Requirement: Local resource limits are explicit

The protocol SHALL define a Mac wall-time, memory-pressure, and paid-provider budget before measured execution.

#### Scenario: A smoke run exceeds the local envelope
- **WHEN** the approved subset cannot complete within the local budget
- **THEN** the measured run SHALL stop
- **AND** larger execution SHALL move to a later cloud-scale proposal rather than silently expanding local resource use