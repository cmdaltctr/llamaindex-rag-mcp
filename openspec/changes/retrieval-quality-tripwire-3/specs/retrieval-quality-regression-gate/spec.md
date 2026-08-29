## Purpose

Defines a small, blocking retrieval-quality gate that detects material ranking
regressions before merge while preserving the experiments process for broader
model evaluation.

## ADDED Requirements

### Requirement: Quality metrics are self-contained and traceable

The gate SHALL compute Recall@10 and MRR@10 with a committed helper under
`tests/quality/`. The helper SHALL carry a provenance comment naming
`experiments/19-native-fts-vs-bm25-sparse-2026-08-29/summarise_eval.py` as the
source of the copied `_recall_mrr` algorithm.

Continuous integration MUST NOT import code from `experiments/`. The committed
helper SHALL remain usable when experiment directories are absent, renamed, or
renumbered.

#### Scenario: Relevant source appears at rank two

- **GIVEN** two golden rows
- **AND** the first row places its expected source at rank two
- **AND** the second row has no expected source in its first ten results
- **WHEN** the helper computes Recall@10 and MRR@10
- **THEN** Recall@10 is `0.5`
- **AND** MRR@10 is `0.25`

#### Scenario: Experiment tree is unavailable

- **GIVEN** the quality helper and committed fixtures are present
- **AND** no `experiments/` path is importable
- **WHEN** either quality tier runs
- **THEN** metric calculation completes from test-owned code

### Requirement: The golden corpus and queries are fixed and licence-clean

The repository SHALL commit a deterministic synthetic corpus under
`tests/quality/`. It SHALL contain roughly 20 documents with planted, distinct
facts and stable source identifiers. Every corpus sentence SHALL be written for
this test and SHALL NOT contain scraped or third-party content.

The repository SHALL commit between 10 and 15 golden queries. Each query SHALL
map to one or more known correct source documents. The corpus, queries, and
source mappings SHALL be reviewable without running an embedding model.

#### Scenario: Golden data is inspected before execution

- **WHEN** a reviewer opens the committed corpus and query fixtures
- **THEN** each query names its expected source document or source set
- **AND** each expected source contains one distinct planted fact that answers
  the query

#### Scenario: Corpus content changes

- **WHEN** a document, query, or source mapping changes
- **THEN** the committed corpus or query identity changes
- **AND** the existing baseline MUST NOT be accepted without a new measurement

### Requirement: Tier 1 blocks pull requests with deterministic retrieval

Tier 1 SHALL run for every pull request with stable fake embeddings and no
Ollama service. It SHALL exercise production score conversion, reciprocal rank
fusion, threshold transformation, and ranking logic against the golden source
mappings.

Tier 1 tests SHALL carry the `slow` marker. Continuous integration SHALL invoke
them through a targeted command, so the existing `pytest -m "not slow"` path
remains unchanged.

Tier 1 documentation MUST state that fake embeddings cannot detect embedding
model quality or production chunk-text effects.

#### Scenario: Pull request changes ranking logic

- **GIVEN** a pull request changes a guarded score, fusion, threshold, or ranking
  calculation
- **WHEN** the change moves a correct source below the committed Tier 1 floor
- **THEN** the Tier 1 job fails the pull request
- **AND** the failure prints expected and actual Recall@10 and MRR@10

#### Scenario: Ollama is unavailable on a pull request runner

- **GIVEN** no process listens at the configured Ollama endpoint
- **WHEN** Tier 1 runs
- **THEN** the gate completes without a skip or network attempt

#### Scenario: The ordinary fast suite runs

- **WHEN** pytest selects `not slow`
- **THEN** Tier 1 is not collected for execution
- **AND** the existing fast job does not gain an Ollama or quality-corpus cost

### Requirement: Tier 2 measures the real embedding path on a schedule

Tier 2 SHALL ingest the committed corpus and run the golden queries with real
Ollama embeddings. The CI configuration SHALL pin one embedding model tag and
the baseline SHALL record that same tag.

Tier 2 SHALL run nightly and through `workflow_dispatch`. Its Recall@10 and MRR
floors SHALL each sit between 0.02 and 0.03 below their measured baseline. This
margin accounts for floating point variation and borderline rank changes across
CPU architectures.

Tier 2 MUST fail when either metric falls below its floor. Ollama absence,
model-tag mismatch, fixture mismatch, or an invalid baseline MUST produce a
failure rather than a skip.

#### Scenario: Nightly quality remains above both floors

- **GIVEN** the pinned model tag and matching golden-data identity
- **WHEN** the nightly Tier 2 job measures Recall@10 and MRR
- **THEN** the job passes only when both metrics meet their committed floors

#### Scenario: Borderline rank varies across machines

- **GIVEN** repeated baseline measurements differ because a borderline source
  changes rank
- **WHEN** the Tier 2 floor is committed
- **THEN** it is set 0.02 to 0.03 below the recorded measured value
- **AND** the cross-machine evidence and selected margin are recorded in the
  implementation TDR

#### Scenario: Manual verification is requested

- **WHEN** a maintainer dispatches the CI workflow manually
- **THEN** Tier 2 runs with the same model tag, fixtures, metrics, and floors as
  the nightly job

### Requirement: Baseline evidence is committed and failure output is diagnostic

A committed JSON baseline SHALL record, for each tier, measured Recall@10,
measured MRR@10, the Recall@10 floor, the MRR@10 floor, and the measurement date.
It SHALL also record a schema version, corpus identity, query-set identity, and
the Tier 2 model tag.

The gate SHALL validate the baseline before comparison. A metric failure SHALL
print the metric name, measured baseline, required floor, and actual result.

#### Scenario: Recall falls below its floor

- **GIVEN** the baseline contains measured Recall@10 `1.0` and floor `0.97`
- **WHEN** a quality run produces Recall@10 `0.90`
- **THEN** the gate fails
- **AND** its output names `1.0`, `0.97`, and `0.90`

#### Scenario: Baseline identity does not match the fixtures

- **WHEN** the corpus or query-set identity differs from the baseline
- **THEN** the gate fails before comparing metrics
- **AND** the output requires an explicit baseline measurement

### Requirement: Quality CI jobs fail loudly and preserve existing fast paths

`.github/workflows/ci.yml` SHALL define dedicated retrieval-quality execution.
Tier 1 SHALL run in its own pull-request job. Tier 2 SHALL run in its own
nightly and manually dispatched job.

Both jobs SHALL set `continue-on-error` to false and SHALL NOT suppress command
failures. Scheduled execution SHALL NOT cause unrelated existing CI jobs to run
unless their existing trigger contract already requires it.

#### Scenario: A quality assertion fails

- **WHEN** either quality test command exits non-zero
- **THEN** its CI job fails
- **AND** no shell fallback or workflow setting converts the failure into success

#### Scenario: The nightly schedule fires

- **WHEN** the CI workflow starts from its nightly schedule
- **THEN** Tier 2 runs
- **AND** unrelated fast, floors, optional-backend, lint, and coverage jobs do
  not run solely because of that schedule

### Requirement: The gate states its detection boundary

The quality runner module documentation and CI job documentation SHALL state
that the gate detects configuration and formula regressions on a small corpus.
They SHALL also state that it does not detect subtle model-quality drift, which
remains the responsibility of the experiments process.

This change SHALL NOT add a new `experiments/` directory. Its corpus, queries,
metric helper, baseline, and quality tests SHALL live under `tests/`.

#### Scenario: A maintainer reads the gate documentation

- **WHEN** a maintainer inspects the quality runner or CI job
- **THEN** the documentation identifies the guarded regression classes
- **AND** it directs subtle model-quality evaluation to the experiments process

#### Scenario: The gate is implemented

- **WHEN** the change is ready for review
- **THEN** no experiment directory has been added for this CI gate
- **AND** all golden quality assets are under `tests/`

### Requirement: Floor and determinism decisions are recorded

Implementation SHALL add a TDR under `docs/tdr/` that records the measured
Tier 2 values, selected 0.02 to 0.03 floor margin, observed cross-machine
variation, and handling for a model tag or runtime that changes. The TDR index
SHALL link the record.

#### Scenario: The blocking floors are enabled

- **WHEN** Tier 2 becomes a blocking gate
- **THEN** the corresponding TDR and index entry are committed
- **AND** the TDR contains enough evidence to reproduce or revise the floor
