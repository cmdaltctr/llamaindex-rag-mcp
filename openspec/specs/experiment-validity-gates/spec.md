# experiment-validity-gates Specification

## Purpose
Sets the validity bar for experiments under ``experiments/``:
machine-checkable plans, runtime manifests recording what actually ran,
manipulated variables that are observed rather than assumed, paired
comparisons by default, execution controls for time and hardware
confounds, and pre-registered practical gates on primary effects.
Calibration decisions cite these gates; without them a PASS is an
opinion.

## Requirements
### Requirement: Experiment plans are machine-checkable

Every calibration experiment that can influence a production default or ADR SHALL define its manipulated factors, controlled variables, expected cell matrix, primary metric, practical-effect gate, and required runtime-manifest assertions in machine-readable form adjacent to the human protocol.

#### Scenario: Runner omits a declared cell
- **GIVEN** a protocol declares a cell in its machine-readable plan
- **AND** the runner's generated cell matrix omits that cell
- **WHEN** experiment contract tests run
- **THEN** the test MUST fail before any expensive model or corpus work begins

#### Scenario: Runner adds an undeclared cell
- **GIVEN** a runner generates a treatment combination not present in the plan
- **WHEN** contract tests run
- **THEN** the test MUST fail or the protocol MUST be amended before execution

### Requirement: Runtime manifests record effective execution

Every measured experiment SHALL emit a secret-free runtime manifest describing what actually executed, not only requested configuration. The manifest SHALL include repository/dependency provenance, corpus/query/qrel/index identity, effective embedding provider/model, vector-store backend/mode/score kind, sparse backend/cache namespace, reranker backend/model/device/execution provider/variant when observable, effective chunker/document reader including fallback state, and effective retrieval knobs relevant to the cell.

#### Scenario: Torch requested but CPU/MPS device differs
- **GIVEN** a cell manipulates the reranker execution device
- **WHEN** preflight observes the effective device
- **THEN** the manifest MUST record the effective device
- **AND** the cell MUST abort if it does not equal the declared treatment

#### Scenario: ONNX provider fallback
- **GIVEN** a performance cell declares CoreML as the manipulated execution provider
- **WHEN** the runtime uses CPUExecutionProvider instead
- **THEN** preflight MUST abort the cell
- **AND** no CoreML latency result may be reported

#### Scenario: Secret-bearing configuration
- **WHEN** a runtime manifest is serialised
- **THEN** API keys, tokens and credential material MUST NOT be present

### Requirement: Manipulated variables must be observed, not assumed

Before a measured cell begins, the experiment SHALL assert that every manipulated variable is effective and every controlled variable remains fixed at its declared value. A production fallback that changes a manipulated factor SHALL invalidate/abort the experimental cell even if that fallback is acceptable during ordinary operation.

#### Scenario: Parser experiment silently bypasses parser
- **GIVEN** parser backend is the manipulated variable
- **WHEN** the runner constructs an index without invoking the declared parser
- **THEN** preflight MUST fail before embeddings are computed

#### Scenario: Technical threshold experiment forces rerank
- **GIVEN** `HARD_TECHNICAL_THRESHOLD` is the manipulated variable
- **WHEN** the runner would call retrieval with explicit `rerank=True` or `rerank=False` instead of policy mode
- **THEN** preflight MUST fail because the policy factor is bypassed

### Requirement: Quality comparisons are paired by default

Unless the manipulated variable necessarily changes the corpus or query set, comparison cells SHALL use the same immutable corpus, exact query set, qrels and query ordering. Workload classes SHALL be blocked/stratified before treatment assignment; a new random query sample SHALL NOT be drawn independently for every treatment level.

#### Scenario: Threshold sweep uses fixed blocked samples
- **GIVEN** thresholds `{0.1, 0.2, 0.3, 0.5, 0.7}` are evaluated
- **WHEN** the experiment constructs technical/semantic workload blocks
- **THEN** every threshold MUST receive the same query membership within each block

### Requirement: Cell execution controls time and hardware confounds

Measured performance experiments SHALL separate warm-up from measured repetitions, record raw repetitions, and randomise or counterbalance cell order when multiple cells share a machine. Interrupted or hung cells SHALL be recorded as incomplete/invalid and SHALL NOT be converted into a numeric latency or quality failure.

#### Scenario: Interrupted cell
- **GIVEN** a cell stops before its declared measured repetitions finish
- **WHEN** results are summarised
- **THEN** the cell MUST be marked incomplete/invalid
- **AND** no imputed latency value may be used in treatment comparisons

### Requirement: Primary effects have pre-registered practical gates

A protocol SHALL name its primary metric and practical-effect threshold before execution. Where per-query paired samples exist, the result SHALL include a paired confidence interval or an explicitly justified equivalence/non-inferiority analysis. A default SHALL NOT be promoted solely from an unbounded point estimate whose uncertainty includes no effect unless the protocol pre-registers a different decision rule.

#### Scenario: Hybrid promotion point estimate without confidence
- **GIVEN** hybrid shows a positive mean Coverage@20 delta
- **BUT** the paired confidence interval includes zero
- **WHEN** the promotion rule requires statistical confidence
- **THEN** the experiment MUST NOT recommend default promotion

### Requirement: Evidence provenance is immutable enough to reproduce

Every expensive experiment SHALL record repository commit SHA, dependency-lock hash, protocol version, corpus identity, query-set identity, qrels identity and index identity. Changing any index-shaping input such as parser, chunking configuration, embedding provider/model or source corpus SHALL produce a distinct index identity.

#### Scenario: Parser changes
- **GIVEN** two cells differ only by PDF parser
- **WHEN** indexes are built
- **THEN** the two index identities MUST differ
- **AND** retrieval-only repetitions within one parser cell MAY reuse that immutable index read-only

