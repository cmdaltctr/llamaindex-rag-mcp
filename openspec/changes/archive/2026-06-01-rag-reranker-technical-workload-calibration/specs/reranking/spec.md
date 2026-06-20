## MODIFIED Requirements

### Requirement: Reranker candidate pool is configurable
The system SHALL keep reranker candidate-pool sizing configurable via `RERANK_MAX_FETCH` and `RERANK_FETCH_MULTIPLIER`. A realistic technical-workload calibration experiment SHALL evaluate whether the current defaults remain appropriate for technical documentation, especially when hybrid BM25/RRF retrieval is enabled.

#### Scenario: Technical workload calibration records reranker policy
- **GIVEN** a realistic technical-document benchmark with dense-only and hybrid retrieval modes
- **WHEN** reranker policies are evaluated
- **THEN** the experiment SHALL record the active `RERANK_ENABLED`, `RERANK_MAX_FETCH`, `RERANK_FETCH_MULTIPLIER`, reranker model, retrieval mode, and latency for each cell
- **THEN** the recommendation SHALL state whether reranking should remain default, become conditional, change pool size, or stay opt-in for technical workloads

### Requirement: Reranker can be evaluated independently from hybrid retrieval
The system SHALL support experiments that compare reranking on and off for both dense-only and hybrid retrieval without changing the underlying corpus or query set.

#### Scenario: Reranker on/off comparison
- **GIVEN** the same indexed corpus and query set
- **WHEN** dense-only and hybrid retrieval are each evaluated with reranking disabled and enabled
- **THEN** the experiment SHALL attribute quality changes separately to first-stage retrieval and reranker policy
- **THEN** the experiment SHALL fail loudly if completed cells cannot be distinguished by retrieval mode and reranker policy
