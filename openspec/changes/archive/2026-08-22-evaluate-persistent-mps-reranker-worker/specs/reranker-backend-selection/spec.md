## MODIFIED Requirements

### Requirement: all backends share one score range and public contract

Every reranker backend SHALL expose the same public behaviour: re-score
query-document pairs, return results sorted by descending relevance, truncate
to `top_k`, and set the reranked provenance flag. Every backend SHALL normalise
raw model outputs to the `(0, 1)` range via the registered transform.

Sharing a public range does not make different inference backends,
quantisations or model artefacts numerically or rank equivalent. Device routes
using the same backend, precision and model revision SHALL meet their declared
device-parity tolerance. ONNX-int8 and Torch-fp32 scores, rankings and threshold
decisions SHALL be treated as backend-specific until admissible calibration
evidence proves interchangeability.

#### Scenario: Every backend returns normalised scores

- **GIVEN** any registered reranker backend
- **WHEN** it re-scores a set of results successfully
- **THEN** every returned score SHALL be greater than 0.0 and less than or equal to 1.0

#### Scenario: Same Torch model agrees across CPU and MPS

- **GIVEN** a fixed query, candidates and Torch fp32 model revision
- **WHEN** Torch CPU and Torch MPS each re-score them under a registered device-parity protocol
- **THEN** ranking equality and score differences MUST satisfy that protocol's tolerance

#### Scenario: Different backend or quantisation disagrees

- **GIVEN** ONNX-int8 and Torch-fp32 routes using nominally the same model ID
- **WHEN** their rankings or scores differ
- **THEN** the difference MUST be reported as backend or quantisation divergence
- **AND** it MUST NOT by itself be reported as an MPS device defect

#### Scenario: Thresholds are backend calibrated

- **GIVEN** a threshold calibrated for one reranker backend and model artefact
- **WHEN** another backend, quantisation or model artefact is selected
- **THEN** the threshold MUST NOT be assumed equivalent without admissible calibration evidence
- **AND** runtime or experiment evidence MUST identify the backend and model artefact used

#### Scenario: Every backend degrades gracefully

- **GIVEN** any registered reranker backend whose model cannot be loaded
- **WHEN** a search is run with `rerank=True`
- **THEN** the system SHALL return un-reranked results truncated to `top_k`
- **AND** every result SHALL carry `"reranked": false`
- **AND** the system SHALL NOT raise
