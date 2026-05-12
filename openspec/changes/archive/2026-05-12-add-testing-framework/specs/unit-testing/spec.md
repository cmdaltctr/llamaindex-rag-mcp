## ADDED Requirements

### Requirement: sigmoid function edge cases

The `_sigmoid()` function SHALL be tested for boundary values to ensure
numerical stability across the full range of possible cross-encoder logits.

#### Scenario: sigmoid of zero returns 0.5

- **WHEN** `_sigmoid(0.0)` is called
- **THEN** the return value SHALL be exactly 0.5

#### Scenario: sigmoid of large positive returns near 1.0

- **WHEN** `_sigmoid(10.0)` is called
- **THEN** the return value SHALL be greater than 0.999
- **AND** SHALL NOT raise an overflow error

#### Scenario: sigmoid of large negative returns near 0.0

- **WHEN** `_sigmoid(-10.0)` is called
- **THEN** the return value SHALL be less than 0.001
- **AND** SHALL NOT raise an overflow error

#### Scenario: sigmoid is monotonic

- **GIVEN** two values `a > b`
- **WHEN** `_sigmoid(a)` and `_sigmoid(b)` are computed
- **THEN** `_sigmoid(a)` SHALL be greater than `_sigmoid(b)`

### Requirement: ONNX variant selection by platform

The `_select_onnx_variant()` function SHALL be tested to verify it returns the
correct model variant for each supported platform.

#### Scenario: ARM64 platform selects quantised variant

- **GIVEN** `platform.machine()` returns `"arm64"`
- **WHEN** `_select_onnx_variant()` is called
- **THEN** the return value SHALL be `"onnx/model_qint8_arm64.onnx"`

#### Scenario: x86_64 platform selects generic variant

- **GIVEN** `platform.machine()` returns `"x86_64"`
- **WHEN** `_select_onnx_variant()` is called
- **THEN** the return value SHALL be `"onnx/model.onnx"`

### Requirement: CrossEncoderReranker singleton behaviour

The `CrossEncoderReranker` class SHALL be tested to verify its singleton pattern
and graceful fallback when the model is unavailable.

#### Scenario: two instances reference the same object

- **WHEN** `CrossEncoderReranker()` is called twice
- **THEN** both instances SHALL be the same Python object (`a is b` returns True)

#### Scenario: rerank with empty list returns empty list

- **GIVEN** a `CrossEncoderReranker` instance
- **WHEN** `rerank("query", [], top_k=5)` is called
- **THEN** an empty list SHALL be returned

#### Scenario: rerank falls back when model not loaded

- **GIVEN** a `CrossEncoderReranker` instance where `_loaded` is `False`
- **WHEN** `rerank("query", results, top_k=3)` is called with 5 results
- **THEN** the first 3 results SHALL be returned with `_reranked` set to `False`

#### Scenario: rerank normalises scores to 0–1 range

- **GIVEN** a `CrossEncoderReranker` with a mocked ONNX session returning logits
- **WHEN** `rerank()` is called
- **THEN** all returned result scores SHALL be in the range (0.0, 1.0)

### Requirement: ingest_path validation logic

The `ingest_path()` function SHALL be tested for input validation without
requiring a running Ollama server.

#### Scenario: non-existent path returns error

- **WHEN** `ingest_path("/nonexistent/directory")` is called
- **THEN** a dict with `"status": "error"` SHALL be returned
- **AND** the message SHALL contain "not found"

#### Scenario: unsupported file extension returns error

- **GIVEN** a temporary file `test.xyz` exists on disk
- **WHEN** `ingest_path("/tmp/test.xyz")` is called
- **THEN** a dict with `"status": "error"` SHALL be returned
- **AND** the message SHALL mention unsupported extension

#### Scenario: empty directory returns success with zero counts

- **GIVEN** an empty directory exists on disk
- **WHEN** `ingest_path` is called with that directory path
- **THEN** a dict with `"status": "ok"`, `"files_indexed": 0`, and
  `"chunks_created": 0` SHALL be returned

### Requirement: list_documents handles empty state

The `list_documents()` function SHALL return an empty list when no collection
exists or no documents have been indexed.

#### Scenario: no collection exists yet

- **GIVEN** ChromaDB has no collection named `documents`
- **WHEN** `list_documents()` is called
- **THEN** an empty list `[]` SHALL be returned
