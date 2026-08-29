## Why

The repository measures Recall@10 and mean reciprocal rank (MRR) across 19
experiment directories, but continuous integration does not measure retrieval
quality. A change to chunking, score conversion, reciprocal rank fusion, or
threshold handling can therefore pass every current test while reducing recall.

The gap is visible in `.github/workflows/ci.yml`. Its jobs cover fast and slow
tests, dependency floors, optional backends, lint, and coverage. None compares
retrieval output with known correct sources. The slow macOS step can also skip
when Ollama is unavailable, so it cannot provide this gate.

**Sequencing context:** this is the third of three ordered changes, as shown by
the `-3` suffix. Implement it after `search-diagnostics-passthrough-1` and
`orphaned-source-visibility-2`. The ordering supports review and rollout only;
this change has no code dependency on either predecessor.

## What Changes

- Add a small retrieval-quality regression gate over a fixed synthetic corpus
  under `tests/`. The corpus will contain roughly 20 licence-clean documents
  with planted, distinct facts. It will not use scraped or third-party text.
- Add 10 to 15 golden queries. Each query will identify its correct source
  document or source set.
- Copy `_recall_mrr` from
  `experiments/19-native-fts-vs-bm25-sparse-2026-08-29/summarise_eval.py` into a
  committed test helper. A provenance comment will name that source. Continuous
  integration will not import from the hyphenated, unpackaged `experiments/`
  tree, whose numbering already contains two `19-` directories.
- Add a deterministic Tier 1 gate for pull requests. It will use stable fake
  embeddings and require no Ollama service. It will catch score-formula,
  reciprocal rank fusion, threshold-transform, and ranking-logic regressions.
  Its contract will state that fake embeddings cannot measure embedding-model
  quality or production chunk-text effects.
- Add a Tier 2 gate for nightly and manually dispatched runs. It will use real
  Ollama embeddings with a pinned model tag. Its quality floor will sit about
  two to three percentage points below the measured baseline because floating
  point results and borderline ranks can vary across CPU architectures.
- Commit baseline JSON containing measured Recall@10 and MRR, their floors, the
  model tag, and the measurement date. Gate failures will print expected and
  actual values.
- Add dedicated retrieval-quality CI execution. Tier 1 will run for pull
  requests through a targeted slow-marked test command. Tier 2 will run on a
  nightly schedule and through `workflow_dispatch`. Both tiers will fail the
  workflow without `continue-on-error` or failure suppression.
- State in test documentation and the capability contract that this is a small
  configuration and formula tripwire. Subtle model-quality drift remains part
  of the experiments process.
- Record the floor margin and cross-machine determinism policy in
  `docs/tdr/016-*.md` during implementation. Update `docs/tdr/README.md` in the
  same task.
- Treat this work as a CI gate. Do not add an `experiments/` directory.

The gate protects decisions established by the existing experiment process:

- `experiments/12-hybrid-default-promotion-2026-06-29/` promoted hybrid
  retrieval to the default.
- `experiments/10-reranker-technical-workload-calibration-2026-05-31/results.md`
  found a 19 to 27 percent technical-workload degradation, which led to the
  reranker default being disabled.
- `experiments/1-reranker-threshold-calibration-2026-05-12/` and
  `experiments/13-hard-technical-threshold-calibration-2026-06-29/` established
  the calibrated threshold treatment.

## Capabilities

### New Capabilities

- `retrieval-quality-regression-gate`: defines the fixed corpus, golden queries,
  Recall@10 and MRR measurement, two required gate tiers, baseline evidence,
  CI failure behaviour, and stated detection limits.

### Modified Capabilities

None. `experiment-validity-gates` governs calibration experiments, while this
change adds a small CI regression contract. `dependency-floor-integrity`
provides a structural precedent for a separate blocking job but owns a different
quality property.

## Impact

**Tests and test data**

- New quality helper, corpus, golden-query manifest, baseline JSON, and targeted
  test modules under `tests/`.
- Tier 1 tests carry the `slow` marker, so `pytest -m "not slow"` remains fast.

**Continuous integration**

- `.github/workflows/ci.yml` gains explicit quality-gate execution and the
  nightly/manual Tier 2 trigger path.
- The gate uses the existing Python and `uv` toolchain. It adds no core runtime
  dependency and no public API.

**Documentation**

- A new TDR records baseline margin selection and cross-machine handling.
- Test documentation explains what the gate detects and what still requires an
  experiment.

**Out of scope**

- Running the full experiment suite in continuous integration.
- Changing embedding models or recalibrating retrieval defaults.
- Changing the reranker policy.
- Building a benchmark dashboard.
