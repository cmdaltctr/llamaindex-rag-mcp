## Context

See `proposal.md` for motivation and sequencing. The relevant constraints are:

- `.github/workflows/ci.yml` runs behavioural tests, dependency-floor tests,
  optional-backend tests, lint, and coverage. It has no retrieval-quality metric
  gate.
- The macOS slow step can skip when Ollama is unavailable. A quality gate cannot
  depend on that conditional path.
- `_recall_mrr` exists only in
  `experiments/19-native-fts-vs-bm25-sparse-2026-08-29/summarise_eval.py`.
  Experiment directories are unpackaged, hyphenated, and not a stable import
  surface. Two directories already share the `19-` prefix.
- `LOCAL_BACKEND=ollama` in CI selects configuration only. It does not start an
  Ollama service or measure retrieval quality.
- Tier 1 must keep the `slow` marker so existing fast and floor-resolution jobs
  retain their current test selection.
- The new capability contract is
  `specs/retrieval-quality-regression-gate/spec.md`. Existing experiment-validity
  and dependency-floor capabilities keep their current requirements.

## Goals / Non-Goals

**Goals:**

- Detect material score, fusion, threshold, and ranking regressions before
  merge.
- Exercise a real embedding path nightly without making pull requests depend on
  Ollama.
- Keep the baseline, its provenance, and its accepted variation visible in the
  repository.
- Fail with enough evidence to distinguish a quality drop from stale fixtures
  or a changed model.

**Non-Goals:**

- Replace calibration experiments or claim model-quality coverage beyond the
  small corpus.
- Change production embedding defaults, reranker policy, threshold values, or
  reciprocal rank fusion constants.
- Create a general benchmark framework or reporting service.

## Decisions

### D1. Copy the metric into a test-owned helper

Create `tests/quality/metrics.py` from the `_recall_mrr` algorithm in Experiment
19. Keep a source-path provenance comment beside the copied function. Include
the source-matching helper it needs and unit tests for rank, miss, multi-source,
and empty-input cases.

The quality runner imports only from `tests/quality/`. This separates the CI
contract from experiment numbering and package layout. It also lets a future
experiment replace its summariser without changing CI.

**Alternative considered:** import the experiment module by file path. Rejected
because its directory is hyphenated, two experiments share prefix 19, and the
experiments tree is not a supported package.

### D2. Use 20 synthetic source files and 12 golden queries

Store 20 short UTF-8 documents under `tests/quality/corpus/`. Each document has
one distinct planted fact, a stable source identifier, and text written for this
repository. Store 12 queries and their expected source lists in
`tests/quality/golden_queries.json`.

The harness calculates deterministic hashes over normalised corpus and query
content. These hashes become the corpus and query-set identities in the
baseline. Any fixture edit therefore invalidates the existing baseline before a
metric comparison can hide the change.

The fixture set includes dense and sparse ranking conflicts, near-threshold
candidates, and cases whose order depends on fusion. These cases make the small
corpus sensitive to the regression classes named in the specification.

**Alternative considered:** reuse Experiment 9 or 19 data. Rejected because a
CI gate must remain licence-clean, self-contained, and independent of experiment
artefacts.

### D3. Tier 1 uses deterministic, pre-chunked retrieval inputs

Tier 1 uses a test-only embedding implementation based on stable standard-library
digests, such as BLAKE2b, with unit-normalised vectors. It must not use Python's
salted `hash()`. The fixture supplies controlled dense and sparse signals through
the existing dependency-injection surface, then exercises production ranking,
score conversion, fusion, and threshold handling.

The test consumes controlled chunks rather than production embedding output.
This makes expected ranks exact across machines. It also defines the limitation:
Tier 1 cannot observe embedding-model quality or changes to the text produced by
chunking.

Do not reuse a constant-vector mock. Identical vectors make every cosine score
equal and cannot establish a meaningful rank contract.

### D4. Tier 2 uses real Ollama ingestion with a pinned reference model

Tier 2 ingests the committed source files through the normal chunking and
retrieval path, then embeds them and the queries through Ollama. Pin
`qwen3-embedding:0.6b` as the test reference tag. This is a CI fixture and does
not change the application's embedding default.

Record the resolved model digest, Ollama version, runner operating system,
runner architecture, corpus hash, and query-set hash with each measurement. A
changed digest or tag fails before metric comparison, so model movement cannot
look like an unexplained retrieval regression.

Set each Tier 2 floor 0.02 to 0.03 below its measured value. Use repeated runs
when selecting the exact margin. Record the observations and final margin in the
implementation TDR.

**Alternative considered:** use the existing macOS slow step. Rejected because
that step can skip without Ollama and has a broader test purpose.

### D5. Keep one versioned baseline JSON beside the quality fixtures

Use `tests/quality/baseline.json` with this logical shape:

```json
{
  "schema_version": 1,
  "corpus_id": "<sha256>",
  "query_set_id": "<sha256>",
  "tier1": {
    "embedding_id": "deterministic-fake-v1",
    "measurement_date": "YYYY-MM-DD",
    "measured": {"recall@10": 1.0, "mrr@10": 1.0},
    "floor": {"recall@10": 1.0, "mrr@10": 1.0}
  },
  "tier2": {
    "model_tag": "qwen3-embedding:0.6b",
    "model_digest": "<digest>",
    "measurement_date": "YYYY-MM-DD",
    "measured": {"recall@10": 1.0, "mrr@10": 0.95},
    "floor": {"recall@10": 0.97, "mrr@10": 0.92}
  }
}
```

The values above illustrate the schema only. Implementation records measured
values. Tier 1 uses exact floors because it is deterministic. Tier 2 uses the
documented margin. Tests never rewrite this file automatically.

### D6. Tier 1 gets its own pull-request job

Add a dedicated Tier 1 job to `.github/workflows/ci.yml`. Run one targeted
slow-marked test module on `ubuntu-latest` for pull-request and push events. Do
not place it inside the current two-operating-system fast matrix.

This choice preserves `pytest -m "not slow"`, avoids running the same quality
corpus twice, and gives branch protection a clear failure name. The added setup
cost is smaller than adding a second command to both fast-job matrix cells.

**Alternative considered:** run Tier 1 inside the existing fast job. Rejected
because its mandatory `slow` marker conflicts with that job's selector. A
targeted second command would duplicate work across Linux and macOS and obscure
which quality contract failed.

### D7. Tier 2 gets a schedule-scoped job in the existing CI workflow

Add an off-hour nightly cron, `23 3 * * *`, to the existing CI workflow. The
existing `workflow_dispatch` trigger also starts Tier 2. Give Tier 2 its own
`ubuntu-latest` job with an event condition limited to `schedule` and
`workflow_dispatch`.

Add schedule exclusions to existing unrelated jobs. A nightly quality run must
not start the full test, floors, optional-backend, lint, and coverage matrix.
Preserve their current push, pull-request, and manual-dispatch behaviour.

Set `continue-on-error: false` explicitly on both quality jobs. Use shell strict
mode where a multi-line command is necessary. Do not add `|| echo`, skip-on-
missing-Ollama logic, or another failure suppressor.

**Alternative considered:** create a separate nightly workflow. It isolates the
schedule more cleanly, but the requested contract places the quality jobs in
`.github/workflows/ci.yml`. Event guards retain that location without spending
the whole CI matrix every night.

### D8. Document the gate boundary in executable and CI surfaces

The quality runner module docstring and the explanatory CI comments use the
same scope statement: the gate detects configuration and formula regressions on
a small corpus. It cannot detect subtle model-quality drift. The experiment
process remains the authority for that question.

### D9. Record calibration as TDR-016 during implementation

Create
`docs/tdr/016-retrieval-quality-floor-margin-and-determinism.md` and add it to
`docs/tdr/README.md`. The record includes repeated measurements, machine details,
the selected margin, model tag and digest handling, baseline regeneration steps,
and revisit triggers.

This work creates no experiment directory. The TDR records an implementation-
level CI decision, which matches the repository's TDR policy for build and
tooling choices.

## Risks / Trade-offs

- **The synthetic corpus can overstate confidence.** The scope statement and
  Tier 2 reduce misuse. Full experiment corpora remain the quality authority.
- **A mutable model tag can change behind the same name.** Record and compare the
  resolved digest. Require an explicit baseline update for any digest change.
- **A margin can be too strict across machines.** Measure repeated runs and
  select a 0.02 to 0.03 margin with evidence in TDR-016.
- **A margin can hide one small rank movement.** Keep per-query output so a
  passing aggregate still exposes changed ranks during review.
- **Adding a schedule to `ci.yml` can start unrelated jobs.** Add explicit
  schedule exclusions to every existing non-quality job.
- **GitHub can disable scheduled workflows after prolonged repository
  inactivity.** Keep `workflow_dispatch` as the recovery and verification path.

## Migration Plan

1. Add the test-owned metric helper and prove its copied behaviour with focused
   unit tests.
2. Commit the corpus, golden queries, identity calculation, and Tier 1 harness.
3. Measure Tier 1 and commit its exact baseline.
4. Add Tier 2, run repeated Ollama measurements, and choose the bounded floors.
5. Write TDR-016 with the measurement and cross-machine evidence.
6. Add both CI jobs, the nightly trigger, and schedule exclusions.
7. Run the targeted quality tests and strict OpenSpec validation.

Rollback removes the two jobs and the test-owned quality assets. No production
data, API, setting, or stored index needs migration.
