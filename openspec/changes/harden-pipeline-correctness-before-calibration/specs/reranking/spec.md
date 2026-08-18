## MODIFIED Requirements

### Requirement: Reranker diagnostics report the backend and execution path that actually ran

When reranker diagnostics are enabled, the system SHALL report the effective reranker backend, model, and the actual execution path needed to interpret a performance experiment. For ONNX this includes the active execution provider(s) and selected model variant/precision when observable. For Torch/SentenceTransformers this includes the effective device (for example `cpu` or `mps`) and precision when observable.

#### Scenario: Torch automatically selects MPS
- **GIVEN** the Torch reranker is requested on an Apple Silicon runtime where SentenceTransformers selects MPS
- **WHEN** diagnostics are requested
- **THEN** the effective backend SHALL be `torch`
- **AND** the effective device SHALL be `mps`

#### Scenario: Torch requested but optional extra is absent
- **GIVEN** Torch is requested but production fallback selects ONNX
- **WHEN** diagnostics are requested
- **THEN** the effective backend SHALL be `onnx`
- **AND** the fallback reason SHALL be available
- **AND** an experiment whose treatment is Torch MUST be able to abort rather than label the cell as Torch

#### Scenario: ONNX uses CPU provider
- **GIVEN** the ONNX reranker runs with `CPUExecutionProvider`
- **WHEN** diagnostics are requested
- **THEN** the execution provider SHALL be recorded explicitly

### Requirement: Backend parity experiments compare equivalent model semantics

A reranker backend/device comparison SHALL pin the same model ID, tokenizer/max-length behaviour, candidate pairs and score normalisation across cells. Device comparisons within the same backend SHALL require ranking/output equivalence within the pre-registered tolerance before speed can justify promotion.

#### Scenario: Torch CPU versus Torch MPS
- **GIVEN** identical fixed query-document pairs
- **WHEN** Torch CPU and Torch MPS cells run
- **THEN** ranking/output parity SHALL be evaluated separately from latency
- **AND** a latency win does not override a failed correctness/parity gate

#### Scenario: ONNX quantised versus Torch full precision
- **GIVEN** ONNX int8 and Torch fp32 differ in precision
- **WHEN** rankings differ on near-tied candidates
- **THEN** the result SHALL be attributed to backend/precision as a manipulated difference
- **AND** it SHALL NOT be described as an MPS device error without a Torch CPU/MPS control establishing that conclusion

### Requirement: Reranker threshold calibration is backend/model-specific evidence

A threshold transform calibrated for one reranker model/backend score distribution SHALL NOT automatically be treated as validated for a materially different model or score-generation path. Shared sigmoid normalisation is necessary for a common range but is not sufficient proof of distributional equivalence.

#### Scenario: Backend or model changes
- **GIVEN** a different reranker model or a backend/precision path whose score distribution materially differs from the calibration baseline
- **WHEN** a calibrated threshold is used
- **THEN** diagnostics/documentation SHALL identify the calibration lineage
- **AND** a follow-up calibration SHALL be required when the pre-registered distribution/parity gate fails
