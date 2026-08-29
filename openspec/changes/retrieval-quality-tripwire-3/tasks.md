## 1. Quality metric and fixed fixtures

- [x] 1.1 Create `tests/quality/metrics.py`. Copy `_recall_mrr` and its source
      matching behaviour from Experiment 19. Add a provenance comment with the
      exact source path.
- [x] 1.2 Add `tests/quality/test_metrics.py` with cases for rank one, rank two,
      misses, multiple expected sources, and empty input. Confirm a deliberate
      algorithm break makes the tests fail, then revert it.
- [x] 1.3 Ensure every quality module imports only test-owned helpers and
      supported `rag_mcp` modules. Add a guard that rejects imports from
      `experiments/`.
- [x] 1.4 Add 20 original source documents under `tests/quality/corpus/`. Give
      each document a stable identifier and one distinct planted fact.
- [x] 1.5 Add `tests/quality/golden_queries.json` with 12 queries. Map every
      query to its correct source document or source set.
- [x] 1.6 Add fixture validation for unique source identifiers, valid mappings,
      the required document and query counts, and deterministic corpus and query
      hashes.
- [x] 1.7 Add a quality-runner module docstring. State the guarded regression
      classes and the limits of this small corpus.

## 2. Tier 1 deterministic pull-request gate

- [x] 2.1 Implement a test-only deterministic embedder with stable BLAKE2b
      token hashing and unit-normalised vectors. Do not use Python's salted
      `hash()` or a constant-vector mock.
- [x] 2.2 Build controlled dense and sparse rows that exercise score conversion,
      reciprocal rank fusion, threshold transformation, and final ranking.
- [x] 2.3 Add `tests/quality/test_retrieval_quality_tier1.py`. Run the production
      retrieval path through injected settings and stores without Ollama.
- [x] 2.4 Mark all Tier 1 quality cases `slow`. Verify they are deselected by
      `pytest -m "not slow"` and run through a targeted command.
- [ ] 2.5 Make Tier 1 compare Recall@10 and MRR@10 with exact deterministic
      floors. Print measured baseline, floor, and actual values on failure.
- [x] 2.6 Perturb one controlled fusion or threshold input. Confirm Tier 1 fails
      for the intended metric, then restore the fixture.

## 3. Tier 2 Ollama gate and baseline measurement

- [x] 3.1 Add `tests/quality/test_retrieval_quality_tier2.py`. Ingest the fixed
      source files through normal chunking and retrieval with Ollama.
- [x] 3.2 Pin `qwen3-embedding:0.6b` as the Tier 2 reference tag. Keep production
      embedding defaults unchanged.
- [x] 3.3 Fail Tier 2 when Ollama is absent, the model tag or digest differs, a
      fixture identity differs, or baseline JSON is invalid. Do not skip these
      conditions.
- [x] 3.4 Record the resolved model digest, Ollama version, operating system,
      architecture, corpus hash, and query-set hash with each measurement.
- [ ] 3.5 Run at least three repeated Tier 2 measurements. Use a second
      available architecture when possible and preserve the per-query ranks.
- [ ] 3.6 Select each Tier 2 floor between 0.02 and 0.03 below its measured
      Recall@10 or MRR value. Use the larger margin when only one architecture
      is available.
- [ ] 3.7 Create `tests/quality/baseline.json` with schema version, fixture
      identities, both tiers' measurements and floors, the model tag, digest,
      and measurement dates.
- [x] 3.8 Add baseline-schema and identity tests. Confirm failures show the
      measured baseline, required floor, and actual result.

## 4. Blocking CI jobs

- [x] 4.1 Add a dedicated Tier 1 job to `.github/workflows/ci.yml`. Run the
      targeted slow-marked Tier 1 file on pull-request and push events.
- [x] 4.2 Add nightly cron `23 3 * * *` to the CI workflow. Preserve the current
      `workflow_dispatch`, push, and pull-request triggers.
- [x] 4.3 Add a dedicated Tier 2 `ubuntu-latest` job. Limit it to schedule and
      `workflow_dispatch` events.
- [x] 4.4 Install and start Ollama in Tier 2. Pull the pinned model tag and run
      only the targeted Tier 2 quality file.
- [x] 4.5 Set `continue-on-error: false` on both jobs. Use strict shell handling
      and remove every skip or failure-suppression path.
- [ ] 4.6 Add schedule exclusions to each existing non-quality job. Confirm a
      nightly event starts Tier 2 without starting unrelated CI jobs.
- [x] 4.7 Add CI comments with the same scope statement as the runner docstring.
      State that subtle model drift still requires experiments.
- [ ] 4.8 Inspect `tests/test_clean_base_tripwire.py`. Update pinned collection
      counts only when the new slow tests change its verified manifest.

## 5. Decision record and operator guidance

- [x] 5.1 Create
      `docs/tdr/016-retrieval-quality-floor-margin-and-determinism.md` from the
      repository template.
- [ ] 5.2 Record repeated metric values, machine details, the chosen margin,
      model tag and digest handling, baseline regeneration, and revisit triggers
      in TDR-016.
- [x] 5.3 Add TDR-016 to `docs/tdr/README.md` with its final status and date.
- [x] 5.4 Document the targeted Tier 1 and Tier 2 commands in
      `tests/TEST_README.md`. Include the gate's detection boundary.
- [x] 5.5 Confirm all corpus, query, metric, baseline, and runner assets live
      under `tests/`. Do not create an `experiments/` directory.

## 6. Final verification

- [ ] 6.1 Run `uv run pytest tests/quality/test_metrics.py
      tests/quality/test_retrieval_quality_tier1.py -m slow --tb=short -q`.
- [ ] 6.2 With the pinned Ollama model available, run `uv run pytest
      tests/quality/test_retrieval_quality_tier2.py -m slow --tb=short -q`.
- [ ] 6.3 Run the ordinary selector against the quality directory and confirm
      no slow quality case executes: `uv run pytest tests/quality -m "not slow"
      --collect-only -q`.
- [ ] 6.4 Validate the workflow syntax and event conditions. Confirm both
      quality jobs remain blocking and scheduled runs exclude unrelated jobs.
- [ ] 6.5 Run `openspec validate "retrieval-quality-tripwire-3" --type change
      --strict` and resolve every reported error.

## 7. Post-merge schedule verification

- [ ] 7.1 After the workflow exists on the default branch, run Tier 2 through
      `workflow_dispatch`. Record the run URL and confirm expected-versus-actual
      metrics appear in its output.
- [ ] 7.2 Confirm the next scheduled event starts Tier 2 only. If GitHub has
      disabled the schedule, re-enable it and record the recovery in TDR-016.
